"""Edisi GO / Cafe pada aplikasi pelanggan: menu per edisi, batas pengguna, server LAN (Cafe), bawaan awal.

Jalankan dari android-app-umkm:  python -m pytest tests -q
"""
import os
import re
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "python"))

import edition  # noqa: E402


@pytest.fixture(scope="module")
def env():
    work = tempfile.mkdtemp(prefix="edition_test_")
    data = os.path.join(work, "data")
    os.makedirs(os.path.join(data, "backups"))
    os.environ.update(SECRET_KEY="k" * 40, DATABASE_URL="sqlite:///" + os.path.join(data, "umkm.db").replace("\\", "/"),
                      BACKUP_FOLDER=os.path.join(data, "backups"), BASE_URL="http://127.0.0.1:1", CAFE_NAME="T",
                      ORULABS_PLATFORM="android")
    import licensing
    from app import create_app, db
    from app.models import ROLE_OWNER, User

    licensing.get_device_id = lambda: "K7QM2XPD4VR5WZ3T"
    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["TESTING"] = True
    shutil.copytree(os.path.join(app.root_path, "static"), os.path.join(data, "static"))
    app.static_folder = os.path.join(data, "static")
    with app.app_context():
        owner = User(username="owner", role=ROLE_OWNER)
        owner.set_password("ownerbaru1")
        db.session.add(owner)
        db.session.commit()
    licensing.install_activation_gate(app, data)
    yield {"app": app, "data": data, "db": db}
    edition.set_edition("go")
    shutil.rmtree(work, ignore_errors=True)


@pytest.fixture
def client(env):
    edition.set_edition("go")
    c = env["app"].test_client()
    c.post("/login", data={"username": "owner", "password": "ownerbaru1"})
    return c


def _tiles(client):
    return re.findall(r'href="([^"]+)" class="card card-hover menu-launcher-card', client.get("/").get_data(as_text=True))


def _set_tables(env, value):
    from app.blueprints.staff import get_settings

    with env["app"].app_context():
        get_settings().uses_tables = value
        env["db"].session.commit()


def test_go_hides_kitchen_and_users_tiles(env, client):
    _set_tables(env, False)
    tiles = _tiles(client)
    assert "/admin/users" not in tiles and not any("kitchen" in h for h in tiles) and not any("table" in h for h in tiles)
    assert len(tiles) == 6


def test_cafe_shows_kitchen_users_and_tables(env, client):
    edition.set_edition("cafe")
    _set_tables(env, True)
    tiles = _tiles(client)
    assert "/admin/users" in tiles and any("kitchen" in h for h in tiles) and any("table" in h for h in tiles)


def test_cafe_limits_active_users_to_three_but_go_does_not(env, client):
    from app.models import User

    def add(name):
        return client.post("/admin/users", data={"username": name, "password": "rahasia1", "role": "kasir"}, follow_redirects=True).get_data(as_text=True)

    edition.set_edition("cafe")
    assert "berhasil dibuat" in add("kasir_a")
    assert "berhasil dibuat" in add("kasir_b")                 # owner + 2 = 3
    assert "dibatasi 3 pengguna" in add("kasir_c")
    with env["app"].app_context():
        assert User.query.filter_by(is_active_user=True).count() == 3
    edition.set_edition("go")                                   # GO: akun lama tidak pernah diblokir
    assert "berhasil dibuat" in add("kasir_d")


def test_cafe_settings_show_lan_address_and_go_does_not(env, client, monkeypatch):
    monkeypatch.setattr(edition, "lan_ip", lambda: "192.168.1.20")
    edition.set_edition("cafe")
    html = client.get("/admin/settings").get_data(as_text=True)
    assert "Hubungkan Perangkat Lain" in html and "http://192.168.1.20:" in html and "data:image/png;base64," in html
    monkeypatch.setattr(edition, "lan_ip", lambda: None)
    assert "belum tersambung ke WiFi" in client.get("/admin/settings").get_data(as_text=True)
    edition.set_edition("go")
    assert "Hubungkan Perangkat Lain" not in client.get("/admin/settings").get_data(as_text=True)


def test_license_card_names_the_edition(env, client):
    edition.set_edition("cafe")
    assert "Oru POS Cafe" in client.get("/admin/settings").get_data(as_text=True)
    edition.set_edition("go")
    assert "Oru POS GO" in client.get("/admin/settings").get_data(as_text=True)


def test_local_network_guard():
    import umkm_app

    for ok in ("127.0.0.1", "192.168.1.5", "10.0.0.7", "172.16.4.2", "192.168.43.1", "169.254.1.1", "::1", "::ffff:192.168.1.9"):
        assert umkm_app._is_local_network(ok), ok
    for bad in ("8.8.8.8", "1.1.1.1", "52.95.110.1", "2001:4860:4860::8888", "", "bukan-ip"):
        assert not umkm_app._is_local_network(bad), bad


def test_edition_defaults_applied_once(env):
    import json

    import umkm_app
    from app.blueprints.staff import get_settings

    marker = os.path.join(env["data"], "edition_init.json")
    if os.path.exists(marker):
        os.remove(marker)
    _set_tables(env, False)
    umkm_app._apply_edition_defaults(env["app"], env["data"], "cafe")
    with env["app"].app_context():
        assert get_settings().uses_tables is True
    assert json.load(open(marker))["edition"] == "cafe"
    _set_tables(env, False)                                     # pemilik mematikan sendiri: tidak ditimpa lagi
    umkm_app._apply_edition_defaults(env["app"], env["data"], "cafe")
    with env["app"].app_context():
        assert get_settings().uses_tables is False


def test_unknown_edition_falls_back_to_go():
    assert edition.set_edition("premium") == "go" and edition.current() == "go"
    assert edition.set_edition("cafe") == "cafe"
    edition.set_edition("go")


def test_heartbeat_payload_carries_the_edition(tmp_path, monkeypatch):
    import licensing
    import monitor

    monkeypatch.setattr(licensing, "get_license_state", lambda d: {"mode": "trial", "days_left": 5, "expiry_text": None, "device_id": "K7QM2XPD4VR5WZ3T"})
    edition.set_edition("cafe")
    try:
        assert monitor.build_payload(str(tmp_path), version="1.0.9")["e"] == "cafe"
    finally:
        edition.set_edition("go")
    assert monitor.build_payload(str(tmp_path), version="1.0.9")["e"] == "go"
