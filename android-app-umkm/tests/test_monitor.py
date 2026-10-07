"""Tes pengirim status aktif GO (monitor.py) terhadap server HTTP tiruan lokal.

Jalankan dari android-app-umkm:  python -m pytest tests -q
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "python"))
import licensing  # noqa: E402
import monitor  # noqa: E402

DEVICE = "K7QM2XPD4VR5WZ3T"


@pytest.fixture
def server():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            received.append((self.path, json.loads(self.rfile.read(length)), dict(self.headers)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_port, received
    srv.shutdown()


def _state(monkeypatch, **kw):
    state = {"mode": "trial", "days_left": 5, "expiry_text": None, "device_id": DEVICE}
    state.update(kw)
    monkeypatch.setattr(licensing, "get_license_state", lambda data_dir: state)


def test_payload_has_only_status_fields(tmp_path, monkeypatch, server):
    url, received = server
    _state(monkeypatch)
    assert monitor.send_once(str(tmp_path), endpoint=url, version="1.0.6") is True
    path, body, headers = received[0]
    assert path == "/v1/hb"
    assert body == {"d": DEVICE, "v": "1.0.6", "m": "trial", "x": "", "p": "android", "l": "id"}


@pytest.mark.parametrize("state,expected_mode,expected_expiry", [
    ({"mode": "permanent"}, "permanent", ""),
    ({"mode": "rental", "expiry_text": "2099-12-31"}, "rental", "20991231"),
    ({"mode": "rental", "expiry_text": "2020-01-02"}, "expired", "20200102"),
])
def test_modes(tmp_path, monkeypatch, state, expected_mode, expected_expiry):
    _state(monkeypatch, **state)
    payload = monitor.build_payload(str(tmp_path), version="1")
    assert payload["m"] == expected_mode and payload["x"] == expected_expiry


def test_ios_platform_and_version_from_env(tmp_path, monkeypatch):
    _state(monkeypatch)
    monkeypatch.setenv("ORULABS_MOBILE_OS", "ios")
    monkeypatch.setenv("ORULABS_APP_VERSION", "1.0.5")
    payload = monitor.build_payload(str(tmp_path))
    assert payload["p"] == "ios" and payload["v"] == "1.0.5"


def test_toggle_default_on_and_persisted(tmp_path):
    assert monitor.is_enabled(str(tmp_path)) is True
    monitor.set_enabled(str(tmp_path), False)
    assert monitor.is_enabled(str(tmp_path)) is False
    monitor.set_enabled(str(tmp_path), True)
    assert monitor.is_enabled(str(tmp_path)) is True


def test_nothing_sent_when_disabled_or_no_endpoint(tmp_path, monkeypatch, server):
    url, received = server
    _state(monkeypatch)
    monitor.set_enabled(str(tmp_path), False)
    assert monitor.send_once(str(tmp_path), endpoint=url) is False
    monitor.set_enabled(str(tmp_path), True)
    assert monitor.send_once(str(tmp_path), endpoint="") is False
    assert received == []


def test_offline_never_raises(tmp_path, monkeypatch):
    _state(monkeypatch)
    assert monitor.send_once(str(tmp_path), endpoint="http://127.0.0.1:9") is False


def test_start_does_nothing_without_endpoint():
    assert monitor.start("x", endpoint="") is None


def test_state_hidden_until_endpoint_is_set(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "ENDPOINT", "")
    assert monitor.state(str(tmp_path))["available"] is False
    monkeypatch.setattr(monitor, "ENDPOINT", "https://x.workers.dev")
    assert monitor.state(str(tmp_path))["available"] is True
