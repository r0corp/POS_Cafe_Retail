"""Tes halaman Pantau Aplikasi: simpan/putus sambungan, gabung dengan riwayat pelanggan,
online / perlu update, dan kegagalan server (token salah, tidak terhubung).

Memakai server HTTP palsu di thread latar sebagai pengganti Worker.
Jalankan dari folder android-app-license-generator:
    python -m pytest tests -q
"""

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "python"))
generator_app = pytest.importorskip("generator_app", reason="private_key.py tidak ada di checkout ini")

TOKEN = "rahasia-admin"
DEVICE_A = "K7QM2XPD4VR5WZ3T"
DEVICE_B = "BBBBBBBBBBBBBBBB"
DEVICE_C = "CCCCCCCCCCCCCCCC"


class _Stub:
    def __init__(self):
        self.devices = []
        self.broadcast = None
        self.puts = []
        self.put_status = 200
        self.status = 200
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    self.send_response(401)
                    self.end_headers()
                    return
                self.send_response(stub.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "devices": stub.devices, "broadcast": stub.broadcast}).encode())

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                stub.puts.append((self.path, body, self.headers.get("Authorization")))
                self.send_response(stub.put_status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def stub():
    s = _Stub()
    yield s
    s.close()


@pytest.fixture
def client(tmp_path):
    generator_app._lock_epoch = 0
    generator_app._unlock_tokens.clear()
    app = generator_app.create_app(str(tmp_path))
    app.config["TESTING"] = True
    c = app.test_client()
    c.post("/login", data={"username": "r0corp", "password": "Arr@r0corp$"})
    c.data_dir = str(tmp_path / "data")
    return c


def _device(code, seen_ago, version="1.0.6", mode="trial", expiry="", platform="android"):
    return {"device": code, "version": version, "mode": mode, "expiry": expiry, "platform": platform,
            "lang": "id", "first_seen": 1, "last_seen": int(time.time()) - seen_ago}


def _connect(client, stub, token=TOKEN):
    return client.post("/pantau/simpan", data={"url": stub.url, "token": token}, follow_redirects=True)


def test_page_asks_for_connection_first(client):
    html = client.get("/pantau").get_data(as_text=True)
    assert "Alamat server Pantau" in html
    assert "Online sekarang" not in html


def test_rejects_bad_address_and_missing_token(client):
    for data in ({"url": "ftp://x.y", "token": "t"}, {"url": "http://contoh.com", "token": "t"},
                 {"url": "https://x.workers.dev", "token": ""}):
        html = client.post("/pantau/simpan", data=data).get_data(as_text=True)
        assert "Alamat harus diawali https://" in html
    assert not os.path.exists(os.path.join(client.data_dir, "monitor.json"))


def test_connected_page_joins_customers_and_counts(client, stub):
    client.post("/generate", data={"device_code": DEVICE_A, "customer_name": "Budi", "shop_name": "Kedai Budi",
                                   "phone": "08123456789", "license_choice": "buy"})
    stub.devices = [
        _device(DEVICE_A, 30, version="1.0.7", mode="permanent"),                    # online, terdaftar
        _device(DEVICE_B, 3 * 3600, version="1.0.6"),                                  # aktif hari ini, belum update, trial
        _device(DEVICE_C, 5 * 86400, version="1.0.6", mode="rental", expiry="20261108", platform="ios"),
    ]
    html = _connect(client, stub).get_data(as_text=True)
    assert "Kedai Budi" in html and "Budi" in html
    assert "Percobaan (belum membeli)" in html and "Tidak ada di riwayat penjualan" in html
    assert "(iPhone)" in html
    assert "2026-11-08" in html
    assert "terbaru 1.0.7" in html.replace("(", "").replace(")", "") or "1.0.7" in html

    view = generator_app._monitor_view(client.data_dir, stub.devices)
    assert (view["total"], view["online"], view["today"], view["outdated"]) == (3, 1, 2, 2)
    assert view["latest"] == "1.0.7" and view["unregistered"] == 2
    assert [i["device"] for i in view["rows"]] == [DEVICE_A, DEVICE_B, DEVICE_C]   # terbaru dulu


def test_version_comparison_is_numeric_not_textual():
    assert generator_app._version_tuple("1.0.10") > generator_app._version_tuple("1.0.9")
    assert generator_app._version_tuple("1.0.7-beta") == (1, 0, 7)


def test_wrong_token_shows_error_and_disconnect_works(client, stub):
    html = _connect(client, stub, token="salah").get_data(as_text=True)
    assert "Token admin ditolak" in html
    client.post("/pantau/putus")
    assert "Alamat server Pantau" in client.get("/pantau").get_data(as_text=True)


def test_unreachable_server_does_not_crash(client, stub):
    _connect(client, stub)
    stub.close()
    resp = client.get("/pantau")
    assert resp.status_code == 200
    assert "Tidak bisa terhubung ke server Pantau (" in resp.get_data(as_text=True)


def test_empty_list_message(client, stub):
    html = _connect(client, stub).get_data(as_text=True)
    assert "Belum ada perangkat yang melapor" in html


def test_english_translation_and_language_switch_returns_here(client, stub):
    _connect(client, stub)
    resp = client.get("/set-language/en?next=/pantau")
    assert resp.headers["Location"].endswith("/pantau")
    html = client.get("/pantau").get_data(as_text=True)
    assert "App Monitor" in html and "Online now" in html


def test_page_requires_unlock(tmp_path):
    generator_app._lock_epoch = 0
    app = generator_app.create_app(str(tmp_path))
    c = app.test_client()
    for path in ("/pantau",):
        assert c.get(path).status_code == 302
    assert c.post("/pantau/simpan", data={"url": "https://a.b", "token": "t"}).status_code == 302


def test_broadcast_is_sent_with_token_and_days(client, stub):
    _connect(client, stub)
    html = client.post("/pantau/siaran", data={"text": "  Update 1.0.7 tersedia  ", "days": "14"},
                       follow_redirects=True).get_data(as_text=True)
    assert stub.puts == [("/v1/broadcast", {"text": "Update 1.0.7 tersedia", "days": 14}, "Bearer " + TOKEN)]
    assert "Siaran terkirim" in html
    assert "Siaran terkirim" not in client.get("/pantau").get_data(as_text=True)      # pemberitahuan hanya sekali


def test_current_broadcast_shown_and_can_be_deleted(client, stub):
    stub.broadcast = {"id": "a1", "text": "Promo perpanjangan <b>x</b>"}
    html = _connect(client, stub).get_data(as_text=True)
    assert "Promo perpanjangan &lt;b&gt;x&lt;/b&gt;" in html and "Hapus siaran" in html
    client.post("/pantau/siaran", data={"text": "", "days": "7"})
    assert stub.puts[-1][1]["text"] == ""
    assert "Siaran dihapus" in client.get("/pantau").get_data(as_text=True)


def test_broadcast_validation_and_failure(client, stub):
    _connect(client, stub)
    html = client.post("/pantau/siaran", data={"text": "x" * 281, "days": "7"}, follow_redirects=True).get_data(as_text=True)
    assert "Siaran tidak valid" in html
    html = client.post("/pantau/siaran", data={"text": "ok", "days": "999"}, follow_redirects=True).get_data(as_text=True)
    assert "Siaran tidak valid" in html
    assert stub.puts == []
    stub.put_status = 401
    html = client.post("/pantau/siaran", data={"text": "ok", "days": "7"}, follow_redirects=True).get_data(as_text=True)
    assert "Gagal mengirim siaran" in html


def test_broadcast_without_connection_and_without_unlock(client, tmp_path, stub):
    assert client.post("/pantau/siaran", data={"text": "x", "days": "7"}).status_code == 302
    assert stub.puts == []
    generator_app._lock_epoch = 0
    c = generator_app.create_app(str(tmp_path / "lain")).test_client()
    assert c.post("/pantau/siaran", data={"text": "x"}).status_code == 302
    assert "/login" in c.post("/pantau/siaran", data={"text": "x"}).headers["Location"]


def test_home_is_a_tile_menu_linking_to_every_feature(client):
    html = client.get("/").get_data(as_text=True)
    for href in ("/buat", "/riwayat", "/dasbor", "/pantau", "/security"):
        assert 'href="%s"' % href in html
    assert 'action="/lock"' in html
    assert "/export.csv" not in html                          # belum ada riwayat
    assert "<form method=\"post\" action=\"/generate\"" not in html   # formulir pindah ke /buat


def test_create_and_history_pages_work(client):
    assert 'action="/generate"' in client.get("/buat").get_data(as_text=True)
    client.post("/generate", data={"device_code": DEVICE_A, "customer_name": "Budi", "shop_name": "Kedai Budi",
                                   "license_choice": "buy"})
    assert "Kedai Budi" in client.get("/riwayat").get_data(as_text=True)
    assert "/export.csv" in client.get("/").get_data(as_text=True)
    assert client.get("/set-language/en?next=/riwayat").headers["Location"].endswith("/riwayat")
    assert client.get("/set-language/en?next=/buat").headers["Location"].endswith("/buat")
    home = client.get("/").get_data(as_text=True)
    assert "Create Code" in home and "History" in home
