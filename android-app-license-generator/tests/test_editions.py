"""Edisi GO / Cafe di aplikasi lisensi: kode terikat edisi (diverifikasi dengan licensing.py asli aplikasi pelanggan),
dua kotak pembuat kode, filter riwayat, dasbor per edisi, dan kolom Edisi di CSV."""

import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "app", "src", "main", "python"))
generator_app = pytest.importorskip("generator_app", reason="private_key.py tidak ada di checkout ini")
sys.path.insert(0, os.path.join(HERE, "..", "..", "android-app-umkm", "app", "src", "main", "python"))
licensing = pytest.importorskip("licensing")
edition = pytest.importorskip("edition")

DEVICE = "K7QM2XPD4VR5WZ3T"


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


def test_codes_are_bound_to_the_edition():
    go = generator_app.generate_activation_code(DEVICE, "PERMANENT", "go")
    cafe = generator_app.generate_activation_code(DEVICE, "PERMANENT", "cafe")
    assert go != cafe
    assert licensing.verify_activation_code(DEVICE, go, "go") == "PERMANENT"
    assert licensing.verify_activation_code(DEVICE, cafe, "cafe") == "PERMANENT"
    assert licensing.verify_activation_code(DEVICE, go, "cafe") is None            # kode GO tidak bisa mengaktifkan Cafe
    assert licensing.verify_activation_code(DEVICE, cafe, "go") is None            # dan sebaliknya
    assert licensing.other_edition_of(DEVICE, cafe) == "cafe" if edition.current() == "go" else True


def test_default_edition_keeps_old_go_codes_valid():
    # rumus GO tidak berubah: kode yang dibuat tanpa menyebut edisi tetap sah di edisi GO
    legacy_style = generator_app.generate_activation_code(DEVICE, "20991231")
    edition.set_edition("go")
    assert licensing.verify_activation_code(DEVICE, legacy_style) == "20991231"
    edition.set_edition("cafe")
    try:
        assert licensing.verify_activation_code(DEVICE, legacy_style) is None
        assert licensing.other_edition_of(DEVICE, legacy_style) == "go"
    finally:
        edition.set_edition("go")


def test_rental_expiry_is_part_of_the_signed_message_for_both_editions():
    code = generator_app.generate_activation_code(DEVICE, "20991231", "cafe")
    tampered = "20991230" + code[8:]
    assert licensing.verify_activation_code(DEVICE, tampered, "cafe") is None


def test_home_has_separate_go_and_cafe_tiles(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/buat?edisi=go"' in html and 'href="/buat?edisi=cafe"' in html
    assert "Kode GO" in html and "Kode Cafe" in html


def test_create_page_shows_edition_and_generate_binds_the_code(client):
    page = client.get("/buat?edisi=cafe").get_data(as_text=True)
    assert "Oru POS Cafe" in page and 'name="edition" value="cafe"' in page
    assert 'name="edition" value="go"' in client.get("/buat").get_data(as_text=True)            # bawaan GO
    assert 'name="edition" value="go"' in client.get("/buat?edisi=aneh").get_data(as_text=True)

    html = client.post("/generate", data={"device_code": DEVICE, "customer_name": "Dewi", "shop_name": "Kopi Dewi",
                                          "license_choice": "buy", "edition": "cafe", "phone": "081533330003"}).get_data(as_text=True)
    code = html.split('id="resultCode">')[1].split("<")[0]
    assert licensing.verify_activation_code(DEVICE, code, "cafe") == "PERMANENT"
    assert licensing.verify_activation_code(DEVICE, code, "go") is None
    assert "Oru%20POS%20Cafe" in html                                                          # pesan WhatsApp menyebut edisinya

    go_html = client.post("/generate", data={"device_code": "BBBBBBBBBBBBBBBB", "customer_name": "Sari", "shop_name": "Warung Sari",
                                             "license_choice": "buy"}).get_data(as_text=True)    # tanpa field edition = GO
    go_code = go_html.split('id="resultCode">')[1].split("<")[0]
    assert licensing.verify_activation_code("BBBBBBBBBBBBBBBB", go_code, "go") == "PERMANENT"


def test_history_filter_dashboard_and_csv_know_the_edition(client):
    def make(device, shop, edition_code):
        client.post("/generate", data={"device_code": device, "customer_name": "X", "shop_name": shop, "license_choice": "monthly",
                                       "edition": edition_code})
    make("AAAAAAAAAAAAAAAA", "Warung A", "go")
    make("BBBBBBBBBBBBBBBB", "Kafe B", "cafe")
    make("CCCCCCCCCCCCCCCC", "Kafe C", "cafe")
    all_html = client.get("/riwayat").get_data(as_text=True)
    assert "Warung A" in all_html and "Kafe B" in all_html
    cafe_html = client.get("/riwayat?edisi=cafe").get_data(as_text=True)
    assert "Kafe B" in cafe_html and "Kafe C" in cafe_html and "Warung A" not in cafe_html
    go_html = client.get("/riwayat?edisi=go").get_data(as_text=True)
    assert "Warung A" in go_html and "Kafe B" not in go_html
    dash = client.get("/dasbor").get_data(as_text=True)
    assert "Per edisi" in dash and "Oru POS Cafe" in dash
    data = generator_app._dashboard_data(client.data_dir)
    assert dict(data["by_edition"]) == {"Oru POS GO": 1, "Oru POS Cafe": 2}
    csv_text = client.get("/export.csv").get_data(as_text=True)
    assert "Edisi" in csv_text.splitlines()[0] and "Oru POS Cafe" in csv_text


def test_old_database_without_edition_column_is_migrated(tmp_path):
    import sqlite3
    data = tmp_path / "data"
    data.mkdir()
    conn = sqlite3.connect(str(data / "licenses.db"))
    conn.execute("""CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL, shop_name TEXT NOT NULL,
        address TEXT, phone TEXT, license_type TEXT NOT NULL, rental_period TEXT, device_code TEXT NOT NULL, expiry_token TEXT NOT NULL,
        activation_code TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO customers (customer_name, shop_name, license_type, device_code, expiry_token, activation_code, created_at)"
                 " VALUES ('Lama', 'Toko Lama', 'buy', 'AAAAAAAAAAAAAAAA', 'PERMANENT', 'x', '2026-01-01 00:00:00')")
    conn.commit()
    conn.close()
    generator_app._init_db(str(data))
    rows = generator_app._list_records(str(data))
    assert rows[0]["edition"] == "go"
