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


# ---- jual cepat (GO): Bayar Tunai/QRIS langsung dari layar pesanan ----

@pytest.fixture
def menu_item(env):
    from app.models import Category, MenuItem

    with env["app"].app_context():
        cat = Category.query.first()
        if cat is None:
            cat = Category(name="Minuman")
            env["db"].session.add(cat)
            env["db"].session.commit()
        item = MenuItem.query.filter_by(name="Es Teh Tes").first()
        if item is None:
            item = MenuItem(name="Es Teh Tes", price=5000, category_id=cat.id, is_available=True)
            env["db"].session.add(item)
            env["db"].session.commit()
        return item.id


def _order_form(menu_id, qty=2, **extra):
    data = {"order_type": "takeaway", "qty_%d" % menu_id: str(qty)}
    data.update(extra)
    return data


def _latest_order(env):
    from app.models import Order

    with env["app"].app_context():
        o = Order.query.order_by(Order.id.desc()).first()
        return dict(id=o.id, is_paid=o.is_paid, method=o.payment_method, cash=o.cash_received, change=o.change_amount, total=o.total)


def test_quick_sale_cash_pays_the_new_order_and_computes_change(env, client, menu_item):
    r = client.post("/orders/new", data=_order_form(menu_item, 2, pay_now="cash", cash_received="20.000"))
    o = _latest_order(env)
    assert r.status_code == 302 and "/receipt" in r.headers["Location"] and "just_paid=1" in r.headers["Location"]
    assert o["is_paid"] and o["method"] == "cash" and o["total"] == 10000 and o["cash"] == 20000 and o["change"] == 10000


def test_quick_sale_qris_needs_no_cash_amount(env, client, menu_item):
    client.post("/orders/new", data=_order_form(menu_item, 1, pay_now="qris"))
    o = _latest_order(env)
    assert o["is_paid"] and o["method"] == "qris" and o["cash"] is None and o["change"] is None


def test_quick_sale_with_too_little_cash_keeps_the_order_unpaid_and_goes_to_cashier(env, client, menu_item):
    r = client.post("/orders/new", data=_order_form(menu_item, 2, pay_now="cash", cash_received="5000"))
    o = _latest_order(env)
    assert not o["is_paid"] and r.headers["Location"].endswith("/cashier")


def test_normal_order_without_pay_now_stays_unpaid(env, client, menu_item):
    client.post("/orders/new", data=_order_form(menu_item, 1))
    assert not _latest_order(env)["is_paid"]


def test_cafe_edition_ignores_pay_now(env, client, menu_item):
    edition.set_edition("cafe")
    client.post("/orders/new", data=_order_form(menu_item, 1, pay_now="qris"))
    assert not _latest_order(env)["is_paid"]


def test_invalid_pay_now_value_is_ignored(env, client, menu_item):
    client.post("/orders/new", data=_order_form(menu_item, 1, pay_now="bitcoin"))
    assert not _latest_order(env)["is_paid"]


def test_order_page_shows_the_pay_button_only_for_go(env, client):
    html = client.get("/orders/new").get_data(as_text=True)
    assert 'id="quickPayBtn"' in html and 'id="quickPayModal"' in html
    edition.set_edition("cafe")
    html = client.get("/orders/new").get_data(as_text=True)
    assert 'id="quickPayBtn"' not in html and 'name="pay_now"' not in html


def test_go_update_turns_tables_off_once_even_when_tables_exist_and_owner_can_turn_them_on_again(env, tmp_path):
    """GO = edisi tanpa meja: sekali saja dimatikan (data meja tidak dihapus); setelah itu pilihan pemilik dihormati."""
    import umkm_app
    from app.blueprints.staff import get_settings
    from app.models import Table

    with env["app"].app_context():
        env["db"].session.add(Table(code="UJI-A1", label="A1", floor=1))
        env["db"].session.commit()
    _set_tables(env, True)
    d = tmp_path / "go"
    d.mkdir()
    umkm_app._apply_edition_defaults(env["app"], str(d), "go")
    with env["app"].app_context():
        assert get_settings().uses_tables is False
        assert Table.query.count() == 1                                    # data meja utuh
    assert os.path.exists(os.path.join(str(d), "go_tables_off.json"))

    _set_tables(env, True)                                                 # pemilik menyalakan lagi
    umkm_app._apply_edition_defaults(env["app"], str(d), "go")             # jalan berikutnya: tidak ditimpa
    with env["app"].app_context():
        assert get_settings().uses_tables is True
        Table.query.delete()
        env["db"].session.commit()


def test_go_settings_hide_tables_and_wifi_sections_when_off(env, client):
    _set_tables(env, False)
    html = client.get("/admin/settings").get_data(as_text=True)
    assert "Info WiFi" not in html and 'name="wifi_name"' not in html
    assert not any("table" in h for h in _tiles(client))


def test_logo_follows_the_edition_on_login_navbar_and_activation_page(env, client, monkeypatch):
    """Logo edisi tampil di login, navbar, dan layar aktivasi (masa percobaan maupun sesudah aktif)."""
    import licensing

    for mode in ("trial", "permanent"):
        monkeypatch.setattr(licensing, "get_license_state",
                            lambda d, m=mode: {"mode": m, "days_left": 5, "expiry_text": None, "device_id": "K7QM2XPD4VR5WZ3T"})
        edition.set_edition("go")
        assert "img/go-logo.png" in client.get("/").get_data(as_text=True)
        edition.set_edition("cafe")
        html = client.get("/").get_data(as_text=True)
        assert "img/cafe-logo.png" in html and "img/go-logo.png" not in html and "orulabs-logo.png" not in html
    edition.set_edition("cafe")
    anon = env["app"].test_client()
    assert "img/cafe-logo.png" in anon.get("/login").get_data(as_text=True)
    edition.set_edition("go")
    assert "img/go-logo.png" in anon.get("/login").get_data(as_text=True)


def test_customer_uploaded_logo_still_wins_over_the_edition_logo(env, client):
    from app.blueprints.staff import get_settings

    with env["app"].app_context():
        s = get_settings()
        s.logo_square, s.logo_wide = "logo-toko.png", "logo-toko.png"
        env["db"].session.commit()
    try:
        edition.set_edition("cafe")
        html = client.get("/").get_data(as_text=True)
        assert "uploads/branding/logo-toko.png" in html and "img/cafe-logo.png" not in html
        assert "uploads/branding/logo-toko.png" in env["app"].test_client().get("/login").get_data(as_text=True)
    finally:
        with env["app"].app_context():
            s = get_settings()
            s.logo_square, s.logo_wide = None, None
            env["db"].session.commit()
        edition.set_edition("go")


def test_logo_files_exist_for_every_edition():
    root = os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "python", "app", "static")
    for code in edition.EDITIONS:
        assert os.path.exists(os.path.join(root, edition.info(code)["logo"])), code


def test_blocked_activation_page_can_still_load_its_logo_and_styles(env, client, monkeypatch):
    import licensing

    monkeypatch.setattr(licensing, "is_activated", lambda d: False)
    assert client.get("/static/img/orulabs-logo.png").status_code == 200
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/admin/settings").status_code == 302                       # halaman POS tetap diblokir
    assert client.get("/static/uploads/branding/apa-saja.png").status_code == 302  # unggahan toko tetap diblokir


def test_activation_page_names_the_edition(env, monkeypatch):
    import licensing

    monkeypatch.setattr(licensing, "is_activated", lambda d: False)
    anon = env["app"].test_client()
    edition.set_edition("cafe")
    html = anon.get("/__activation").get_data(as_text=True)
    assert "Oru POS Cafe" in html and "Oru POS GO" not in html
    edition.set_edition("go")
    assert "Oru POS GO" in anon.get("/__activation").get_data(as_text=True)

