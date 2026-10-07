"""Tes menu Keamanan Generator Lisensi: login, penahan tebak-password, ganti
password, token sidik jari sekali-pakai, kunci otomatis.

Butuh private_key.py (di-gitignore, hanya ada di laptop pengembang) - tanpa itu
semua tes di sini di-skip.

Jalankan dari folder android-app-license-generator:
    python -m pytest tests -q
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app", "src", "main", "python"))
generator_app = pytest.importorskip("generator_app", reason="private_key.py tidak ada di checkout ini")

DEFAULT_USER = "r0corp"
DEFAULT_PASSWORD = "Arr@r0corp$"   # kredensial bawaan yang ditentukan pemilik app


@pytest.fixture
def client(tmp_path):
    generator_app._lock_epoch = 0
    generator_app._unlock_tokens.clear()
    app = generator_app.create_app(str(tmp_path))
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def clock(monkeypatch):
    """Jam palsu yang bisa dimajukan."""
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(generator_app.time, "time", lambda: state["now"])
    return state


def _login(client, username=DEFAULT_USER, password=DEFAULT_PASSWORD):
    return client.post("/login", data={"username": username, "password": password})


def _is_unlocked(client):
    return client.get("/").status_code == 200


def test_default_credentials_still_work(client):
    resp = _login(client)
    assert resp.status_code == 302
    assert _is_unlocked(client)


def test_wrong_password_rejected(client):
    resp = _login(client, password="salah")
    assert resp.status_code == 200
    assert b"salah" in resp.data
    assert not _is_unlocked(client)


def test_non_ascii_username_does_not_crash(client):
    assert _login(client, username="rócorp").status_code == 200


def test_five_wrong_passwords_block_even_the_right_one(client, clock):
    for _ in range(5):
        _login(client, password="salah")

    resp = _login(client)          # password BENAR, tapi sedang ditahan
    assert resp.status_code == 200
    assert b"Terlalu banyak" in resp.data
    assert not _is_unlocked(client)

    clock["now"] += 31             # lewat 30 detik
    assert _login(client).status_code == 302
    assert _is_unlocked(client)


def test_throttle_grows_with_each_extra_failure(client, clock):
    for _ in range(5):
        _login(client, password="salah")
    assert generator_app.login_wait_seconds() == 30

    clock["now"] += 31
    _login(client, password="salah")   # salah ke-6
    assert generator_app.login_wait_seconds() == 60

    clock["now"] += 61
    _login(client, password="salah")   # salah ke-7
    assert generator_app.login_wait_seconds() == 120


def test_successful_login_resets_failure_counter(client):
    for _ in range(4):
        _login(client, password="salah")
    _login(client)
    client.post("/lock")
    for _ in range(4):
        _login(client, password="salah")
    assert generator_app.login_wait_seconds() == 0   # belum 5 berturut-turut lagi


def test_change_password_flow(client):
    _login(client)

    assert b"Password lama salah" in client.post("/security/password", data={
        "old_password": "bukan", "new_password": "PasswordBaru1", "confirm_password": "PasswordBaru1"}).data
    assert b"minimal" in client.post("/security/password", data={
        "old_password": DEFAULT_PASSWORD, "new_password": "pendek", "confirm_password": "pendek"}).data
    assert b"tidak sama" in client.post("/security/password", data={
        "old_password": DEFAULT_PASSWORD, "new_password": "PasswordBaru1", "confirm_password": "Beda12345"}).data
    assert b"berhasil diganti" in client.post("/security/password", data={
        "old_password": DEFAULT_PASSWORD, "new_password": "PasswordBaru1", "confirm_password": "PasswordBaru1"}).data

    client.post("/lock")
    assert _login(client).status_code == 200                       # password lama tidak berlaku lagi
    assert _login(client, password="PasswordBaru1").status_code == 302
    assert _is_unlocked(client)


def test_new_password_is_stored_hashed_not_plain(client, tmp_path):
    _login(client)
    client.post("/security/password", data={
        "old_password": DEFAULT_PASSWORD, "new_password": "PasswordBaru1", "confirm_password": "PasswordBaru1"})
    raw = open(os.path.join(str(tmp_path), "data", "security.json"), encoding="utf-8").read()
    assert "PasswordBaru1" not in raw
    assert json.loads(raw)["password_hash"].count(":") == 1


def test_biometric_unlock_refuses_without_a_valid_token(client):
    """Celah lama: aplikasi lain di HP bisa buka 127.0.0.1:5001/biometric-unlock."""
    assert client.get("/biometric-unlock").status_code == 302
    assert not _is_unlocked(client)
    assert client.get("/biometric-unlock?token=tebakan").status_code == 302
    assert not _is_unlocked(client)


def test_biometric_token_is_single_use(client):
    token = generator_app.issue_unlock_token()
    client.get("/biometric-unlock?token=" + token)
    assert _is_unlocked(client)

    client.post("/lock")
    client.get("/biometric-unlock?token=" + token)                  # dipakai ulang
    assert not _is_unlocked(client)


def test_biometric_token_expires(client, clock):
    token = generator_app.issue_unlock_token()
    clock["now"] += generator_app.UNLOCK_TOKEN_TTL_SECONDS + 1
    client.get("/biometric-unlock?token=" + token)
    assert not _is_unlocked(client)


def test_biometric_can_be_disabled(client):
    _login(client)
    client.post("/security/settings", data={"lock_on_leave": "1", "idle_lock_minutes": "0"})  # biometrik tidak dicentang
    assert generator_app.issue_unlock_token() is None
    assert not generator_app.is_biometric_enabled()


def test_lock_all_invalidates_existing_sessions(client):
    _login(client)
    assert _is_unlocked(client)
    generator_app.lock_all()
    assert not _is_unlocked(client)


def test_idle_lock_after_configured_minutes(client, clock):
    _login(client)
    client.post("/security/settings", data={"biometric_enabled": "1", "idle_lock_minutes": "5"})

    clock["now"] += 4 * 60
    assert _is_unlocked(client)          # masih aktif, dan hitungan idle diperbarui
    clock["now"] += 4 * 60
    assert _is_unlocked(client)          # 4 menit sejak aktivitas terakhir
    clock["now"] += 6 * 60
    assert not _is_unlocked(client)      # 6 menit tanpa aktivitas -> terkunci


def test_invalid_idle_choice_falls_back_to_never(client):
    _login(client)
    client.post("/security/settings", data={"idle_lock_minutes": "7"})
    assert generator_app.load_security()["idle_lock_minutes"] == 0


def test_security_page_requires_login(client):
    assert client.get("/security").status_code == 302
    assert client.post("/security/settings", data={}).status_code == 302
    assert client.post("/security/password", data={}).status_code == 302


def test_lock_on_leave_default_is_off_and_toggle_persists(client):
    _login(client)
    assert generator_app.should_lock_on_leave() is False
    client.post("/security/settings", data={"biometric_enabled": "1", "lock_on_leave": "1", "idle_lock_minutes": "0"})
    assert generator_app.should_lock_on_leave() is True


def test_login_page_hides_fingerprint_button_when_disabled(client):
    assert b"'true' && window.AndroidAuth" not in client.get("/login").data
    assert b"true && window.AndroidAuth" in client.get("/login").data
    _login(client)
    client.post("/security/settings", data={"idle_lock_minutes": "0"})   # matikan biometrik
    client.post("/lock")
    assert b"false && window.AndroidAuth" in client.get("/login").data


# ---------------------------------------------------------------- dua bahasa

def _switch(client, code, next_path="/login"):
    return client.get(f"/set-language/{code}?next={next_path}")


def test_default_language_is_indonesian(client):
    page = client.get("/login").data
    assert b"Silakan masuk untuk melanjutkan." in page
    assert b'lang="id"' in page


def test_language_can_be_switched_without_logging_in(client):
    resp = _switch(client, "en")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/login")
    page = client.get("/login").data
    assert b"Please sign in to continue." in page
    assert b"Display Preferences" in page
    assert b'lang="en"' in page
    assert b"Silakan masuk" not in page


def test_login_page_has_both_flag_buttons(client):
    page = client.get("/login").data
    assert b"/set-language/id" in page and b"/set-language/en" in page


def test_unknown_language_code_is_ignored(client):
    _switch(client, "xx")
    assert generator_app.get_language() == "id"
    assert b"Silakan masuk" in client.get("/login").data


def test_next_parameter_only_allows_known_pages(client):
    resp = client.get("/set-language/en?next=https://evil.example/")
    assert resp.headers["Location"].endswith("/") and "evil" not in resp.headers["Location"]


def test_english_error_messages(client):
    _switch(client, "en")
    assert b"Wrong username or password." in _login(client, password="salah").data
    for _ in range(4):
        _login(client, password="salah")
    assert b"Too many wrong attempts" in _login(client).data


def test_language_survives_lock_and_restart(client, tmp_path):
    _switch(client, "en")
    _login(client)
    client.post("/lock")
    assert b"Please sign in" in client.get("/login").data

    generator_app._lock_epoch = 0
    again = generator_app.create_app(str(tmp_path)).test_client()     # "restart" app
    assert b"Please sign in" in again.get("/login").data


def test_main_page_and_license_labels_in_english(client):
    _switch(client, "en")
    _login(client)
    page = client.get("/buat").data
    assert b"Create Activation Code" in page
    assert b"One-time Purchase" in page and b"Yearly Rental" in page
    assert b"Beli Putus" not in page


def test_generated_result_and_whatsapp_message_follow_language(client):
    _switch(client, "en")
    _login(client)
    resp = client.post("/generate", data={
        "device_code": "TESTDEVICE0001", "customer_name": "Budi", "shop_name": "Kopi Budi",
        "phone": "081234567890", "license_choice": "weekly"})
    page = resp.data.decode()
    assert "was created" in page and "Weekly Rental" in page
    assert "Hello%20Budi" in page and "Activation%20Code%20for%20Kopi%20Budi" in page


def test_indonesian_whatsapp_message_unchanged(client):
    _login(client)
    page = client.post("/generate", data={
        "device_code": "TESTDEVICE0001", "customer_name": "Budi", "shop_name": "Kopi Budi",
        "phone": "081234567890", "license_choice": "buy"}).data.decode()
    assert "Halo%20Budi" in page and "berhasil dibuat" in page


def test_security_page_messages_in_english(client):
    _switch(client, "en")
    _login(client)
    assert b"Change Password" in client.get("/security").data
    resp = client.post("/security/password", data={
        "old_password": "bukan", "new_password": "PasswordBaru1", "confirm_password": "PasswordBaru1"})
    assert b"The current password is wrong." in resp.data
    resp = client.post("/security/settings", data={"biometric_enabled": "1", "idle_lock_minutes": "5"})
    assert b"Lock settings saved." in resp.data and b"5 minutes" in resp.data


def test_every_screen_text_has_an_english_translation():
    """Cegah teks yang lupa diterjemahkan: semua _('...') di template dan tr("...") di kode."""
    import re
    source = open(generator_app.__file__, encoding="utf-8").read()
    msgids = set(re.findall(r"_\('((?:[^'\\]|\\.)*)'", source))
    msgids |= set(re.findall(r'\btr(?:_plain)?\(\s*"((?:[^"\\]|\\.)*)"', source))
    msgids = {m.replace("\n", "\n") for m in msgids if m}
    # LICENSE_LABELS dipakai lewat _(variabel) - ikut diperiksa
    msgids |= set(generator_app.LICENSE_LABELS.values())
    # Pesan WhatsApp ditulis dua potongan string di kode (potongan pertama berakhir "\n\n");
    # terjemahan utuhnya dibuktikan di test_generated_result_and_whatsapp_message_follow_language.
    msgids = {m for m in msgids if not m.startswith("Halo %(name)s")}
    missing = sorted(m for m in msgids if m not in generator_app._EN)
    assert not missing, missing


# ---------------------------------------------------------------- ekspor riwayat (CSV)

def _seed_history(tmp_path_dir):
    data_dir = os.path.join(str(tmp_path_dir), "data")
    generator_app._save_record(data_dir, {
        "customer_name": "=HYPERLINK(\"http://x\")", "shop_name": "Warung \u00c9ka", "address": "Jl. Mawar", "phone": "0812",
        "license_type": "buy", "rental_period": None, "device_code": "K7QM2XPD4VR9WZ3T",
        "expiry_token": "PERMANENT", "activation_code": "ABC.DEF",
    })
    generator_app._save_record(data_dir, {
        "customer_name": "Sari", "shop_name": "Kedai Sari", "address": "", "phone": "",
        "license_type": "rent", "rental_period": "monthly", "device_code": "AAAABBBBCCCCDDDD",
        "expiry_token": "20261108", "activation_code": "XYZ.123",
    })


def test_export_requires_login(client):
    resp = client.get("/export.csv")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_export_csv_contains_all_history_safely(client, tmp_path):
    _seed_history(tmp_path)
    assert _login(client).status_code in (200, 302)
    resp = client.get("/export.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"] and ".csv" in resp.headers["Content-Disposition"]
    text = resp.get_data(as_text=True)
    assert text.startswith("\ufeff")
    assert "Kode aktivasi" in text and "ABC.DEF" in text and "XYZ.123" in text
    assert "Warung \u00c9ka" in text
    assert "Permanen" in text and "2026-11-08" in text and "Beli putus" in text and "Sewa" in text
    # rumus tidak boleh ikut dieksekusi saat dibuka di Excel
    assert "'=HYPERLINK" in text


def test_export_button_only_when_history_exists(client, tmp_path):
    _login(client)
    assert b"/export.csv" not in client.get("/").data
    _seed_history(tmp_path)
    assert b"/export.csv" in client.get("/").data


# ---------------------------------------------------------------- Dasbor Lisensi

def _insert(data_dir, shop, device, license_type, rental, token, price, created, phone="0812345678", customer="Budi"):
    import sqlite3

    conn = sqlite3.connect(os.path.join(data_dir, "licenses.db"))
    conn.execute(
        """INSERT INTO customers (customer_name, shop_name, address, phone, license_type, rental_period, device_code,
                                  expiry_token, activation_code, price, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (customer, shop, "", phone, license_type, rental, device, token, "X.Y", price, created),
    )
    conn.commit()
    conn.close()


def _token(days):
    from datetime import date, timedelta

    return (date.today() + timedelta(days=days)).strftime("%Y%m%d")


def _seed_dashboard(tmp_path):
    from datetime import date, timedelta

    data_dir = os.path.join(str(tmp_path), "data")
    today = date.today()
    this_month = today.strftime("%Y-%m-%d 10:00:00")
    last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d 10:00:00")
    _insert(data_dir, "Toko Permanen", "AAAA", "buy", None, "PERMANENT", 1490000, this_month)
    _insert(data_dir, "Warung Segera", "BBBB", "rent", "monthly", _token(5), 99000, this_month, phone="0811")
    _insert(data_dir, "Kedai Lewat", "CCCC", "rent", "monthly", _token(-10), 99000, last_month, phone="0822")
    _insert(data_dir, "Lama Sekali", "DDDD", "rent", "weekly", _token(-200), 19000, last_month)
    _insert(data_dir, "Sudah Perpanjang", "EEEE", "rent", "monthly", _token(-40), 99000, last_month)
    _insert(data_dir, "Sudah Perpanjang", "EEEE", "rent", "yearly", _token(300), 890000, this_month)
    _insert(data_dir, "Tanpa Harga", "FFFF", "rent", "weekly", _token(20), None, this_month)


def test_dashboard_requires_login(client):
    resp = client.get("/dasbor")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_dashboard_numbers(client, tmp_path):
    _seed_dashboard(tmp_path)
    _login(client)
    html = client.get("/dasbor").get_data(as_text=True)
    # 6 perangkat; aktif = permanen + Segera + Sudah Perpanjang + Tanpa Harga
    data = generator_app._dashboard_data(os.path.join(str(tmp_path), "data"))
    assert data["customers"] == 6
    assert data["active"] == 4
    assert [i["shop"] for i in data["expiring"]] == ["Warung Segera", "Tanpa Harga"]
    assert [i["shop"] for i in data["expired"]] == ["Kedai Lewat"]          # >90 hari dan yang sudah diperpanjang tidak masuk
    assert data["sales_total"] == 7
    assert data["rev_total"] == "Rp 2.696.000"
    assert data["rev_month"] == "Rp 2.479.000"      # 1.490.000 + 99.000 + 890.000
    assert data["rev_last"] == "Rp 217.000"          # 99.000 (Kedai Lewat) + 19.000 (Lama Sekali) + 99.000 (Sudah Perpanjang, lama)


def test_dashboard_page_has_whatsapp_reminders(client, tmp_path):
    _seed_dashboard(tmp_path)
    _login(client)
    html = client.get("/dasbor").get_data(as_text=True)
    assert "Warung Segera" in html and "Kedai Lewat" in html
    assert "wa.me/62811" in html and "wa.me/62822" in html
    assert "Lama Sekali" not in html
    assert "Dasbor Lisensi" in html
    # tombol di halaman utama
    assert b"/dasbor" in client.get("/").data


def test_dashboard_english(client, tmp_path):
    _seed_dashboard(tmp_path)
    _login(client)
    client.get("/set-language/en?next=/dasbor")
    html = client.get("/dasbor").get_data(as_text=True)
    assert "License Dashboard" in html and "Remind" in html
    assert "Hi%20Budi" in html          # pesan WhatsApp ikut bahasa


def test_price_saved_and_exported(client, tmp_path):
    _login(client)
    resp = client.post("/generate", data={
        "device_code": "ZZZZ1111ZZZZ1111", "customer_name": "Sari", "shop_name": "Kedai Sari", "phone": "0813",
        "license_choice": "monthly", "price": "Rp 99.000",
    })
    assert resp.status_code == 200
    text = client.get("/export.csv").get_data(as_text=True)
    assert "Harga (Rp)" in text and "99000" in text
    data = generator_app._dashboard_data(os.path.join(str(tmp_path), "data"))
    assert data["has_price"] and data["rev_total"] == "Rp 99.000"


def test_old_database_without_price_column_is_migrated(tmp_path):
    import sqlite3

    data_dir = os.path.join(str(tmp_path), "data")
    os.makedirs(data_dir)
    conn = sqlite3.connect(os.path.join(data_dir, "licenses.db"))
    conn.execute("""CREATE TABLE customers (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL, shop_name TEXT NOT NULL,
        address TEXT, phone TEXT, license_type TEXT NOT NULL, rental_period TEXT, device_code TEXT NOT NULL, expiry_token TEXT NOT NULL,
        activation_code TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("INSERT INTO customers (customer_name, shop_name, license_type, device_code, expiry_token, activation_code, created_at) "
                 "VALUES ('A','B','buy','D1','PERMANENT','X.Y','2026-01-01 00:00:00')")
    conn.commit()
    conn.close()
    generator_app._init_db(data_dir)
    data = generator_app._dashboard_data(data_dir)
    assert data["customers"] == 1 and not data["has_price"]
