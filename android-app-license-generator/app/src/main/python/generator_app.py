"""App INTERNAL buat penjual APK UMKM sendiri - generate Kode Aktivasi
dari HP, tanpa perlu bawa laptop tiap ada penjualan baru. Dikunci PIN
(scrypt, sama mekanismenya dengan PIN Mode Demo di app POS café) karena
app ini pegang private_key.py - siapa pun yang buka app ini (setelah PIN
terbuka) bisa bikin Kode Aktivasi buat HP mana pun.

Alur pakai:
  1. Pertama kali dibuka -> diminta buat PIN.
  2. Buka berikutnya -> diminta masukkan PIN itu (sesi "terbuka" cuma
     berlaku sampai app ditutup, sama seperti PIN Mode Demo).
  3. Isi form: Kode Perangkat (dari HP pembeli) + data pembeli + jenis
     lisensi (beli putus / sewa mingguan/bulanan/tahunan).
  4. Kode Aktivasi langsung muncul, siap disalin/dikirim ke pembeli.
  5. Semua yang pernah di-generate tersimpan di "Riwayat" (database
     lokal HP ini) - riwayat penjualan sekaligus.

_SIGN_SALT di bawah HARUS PERSIS SAMA dengan yang di
android-app-umkm/app/src/main/python/licensing.py - itu yang
memverifikasi kode yang dibuat di sini.
"""

import base64
import csv
import hashlib
import io
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import date, timedelta

from flask import (Response, Flask, g, has_request_context, redirect, render_template_string, request,
                   session, url_for)
from markupsafe import Markup, escape

from private_key import PRIVATE_KEY_D, PRIVATE_KEY_N
from rsa_math import sign
from ui_fonts import FONT_CSS

_SIGN_SALT = b"orulabs-apk-umkm-activation-v1"

RENTAL_DAYS = {"weekly": 7, "monthly": 30, "yearly": 365}
LICENSE_LABELS = {
    "buy": "Beli Putus",
    "weekly": "Sewa Mingguan",
    "monthly": "Sewa Bulanan",
    "yearly": "Sewa Tahunan",
}


# ============================================================
# Kripto - persis sama rumusnya dengan licensing.py, cuma di sini yang
# SIGN (di sana yang VERIFY).
# ============================================================

def _b32encode(data):
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _hash_to_int(device_id, expiry_token):
    digest = hashlib.sha256(_SIGN_SALT + device_id.encode() + b"|" + expiry_token.encode()).digest()
    return int.from_bytes(digest, "big")


def compute_expiry_token(license_type, rental_period):
    if license_type == "buy":
        return "PERMANENT"
    days = RENTAL_DAYS[rental_period]
    return (date.today() + timedelta(days=days)).strftime("%Y%m%d")


def generate_activation_code(device_id, expiry_token):
    message_int = _hash_to_int(device_id, expiry_token)
    signature_int = sign(message_int, (PRIVATE_KEY_N, PRIVATE_KEY_D))
    signature_bytes = signature_int.to_bytes((signature_int.bit_length() + 7) // 8, "big")
    return expiry_token + "." + _b32encode(signature_bytes)


# ============================================================
# Login (username + password TETAP, hardcode di kode - sama polanya
# dengan DEV_PIN_HASH Mode Demo di app/blueprints/staff.py). Sengaja
# BUKAN bikin-PIN-sendiri-saat-pertama-buka lagi - kalau HP ini hilang,
# yang nemu tidak boleh bisa langsung set kredensial sendiri.
# Password disimpan sebagai HASH scrypt (salt+hash sekaligus dalam satu
# string), bukan teks polos, walau toh sama-sama tertanam di source -
# supaya walau APK ini di-unzip, password aslinya tidak langsung
# kebaca.
# ============================================================

LOGIN_USERNAME = "r0corp"
LOGIN_PASSWORD_HASH = "1c3174c90633522db2f0bcf5f59d60da:0b6a78aa7bdef8e4a113b0cc81189ef2d9386349ab80bf0a079f14ffbb95041a"


def _check_hash(password, stored_hash):
    try:
        salt_hex, key_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
    except ValueError:
        return False
    actual = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return hmac.compare_digest(actual, expected)


def hash_password(password):
    """Hash scrypt baru (salt acak + hash dalam satu string "salt:hash")."""
    salt = os.urandom(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return salt.hex() + ":" + key.hex()


def verify_login(username, password, password_hash=None):
    """password_hash = hash yang disimpan lewat menu Keamanan; kalau belum
    pernah ganti password, dipakai LOGIN_PASSWORD_HASH bawaan di atas."""
    # Dibandingkan sebagai bytes: compare_digest(str, str) error kalau ada
    # karakter non-ASCII, dan itu tidak boleh jadi halaman error 500.
    if not hmac.compare_digest(username.encode("utf-8"), LOGIN_USERNAME.encode("utf-8")):
        return False
    return _check_hash(password, password_hash or LOGIN_PASSWORD_HASH)


# ============================================================
# Pengaturan keamanan (menu "Keamanan") - disimpan di security.json di
# folder data app: password pengganti, sidik jari on/off, kunci otomatis,
# dan penghitung salah-login (supaya tebak-tebak password diperlambat).
# ============================================================

_DATA_DIR = None
_security_lock = threading.Lock()
_lock_epoch = 0          # dinaikkan tiap lock_all() -> semua sesi lama otomatis tidak berlaku
_unlock_tokens = {}      # token sekali-pakai dari sidik jari native -> waktu kedaluwarsa

IDLE_CHOICES = (0, 1, 5, 15, 30)   # menit; 0 = tidak pernah
MIN_PASSWORD_LENGTH = 8
THROTTLE_AFTER = 5       # mulai ditahan sesudah sekian kali salah berturut-turut
THROTTLE_BASE_SECONDS = 30
THROTTLE_MAX_SECONDS = 900
UNLOCK_TOKEN_TTL_SECONDS = 30

_SECURITY_DEFAULTS = {
    "password_hash": None,
    "biometric_enabled": True,
    "idle_lock_minutes": 0,
    "lock_on_leave": False,
    "language": "id",
    "failed_count": 0,
    "locked_until": 0.0,
}


def _security_path():
    return os.path.join(_DATA_DIR, "security.json")


def load_security():
    settings = dict(_SECURITY_DEFAULTS)
    if _DATA_DIR is None:
        return settings
    try:
        with open(_security_path(), "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            settings.update({k: v for k, v in stored.items() if k in _SECURITY_DEFAULTS})
    except (OSError, ValueError):
        pass
    return settings


def save_security(settings):
    tmp = _security_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f)
    os.replace(tmp, _security_path())


def login_wait_seconds():
    with _security_lock:
        remaining = load_security()["locked_until"] - time.time()
    return max(0, int(remaining + 0.999))


def _register_login_failure():
    with _security_lock:
        settings = load_security()
        settings["failed_count"] += 1
        if settings["failed_count"] >= THROTTLE_AFTER:
            delay = min(THROTTLE_MAX_SECONDS,
                        THROTTLE_BASE_SECONDS * 2 ** (settings["failed_count"] - THROTTLE_AFTER))
            settings["locked_until"] = time.time() + delay
        save_security(settings)


def _register_login_success():
    with _security_lock:
        settings = load_security()
        if settings["failed_count"] or settings["locked_until"]:
            settings["failed_count"] = 0
            settings["locked_until"] = 0.0
            save_security(settings)


def lock_all():
    """Kunci SEMUA sesi sekarang juga (dipanggil MainActivity saat app
    ditinggalkan, kalau opsi "kunci saat keluar" aktif)."""
    global _lock_epoch
    _lock_epoch += 1
    _unlock_tokens.clear()


def current_language():
    return get_language()


def should_lock_on_leave():
    return bool(load_security()["lock_on_leave"])


def is_biometric_enabled():
    return bool(load_security()["biometric_enabled"])


def issue_unlock_token():
    """Dipanggil NATIVE Android (MainActivity) SESUDAH BiometricPrompt
    berhasil - token sekali-pakai ini satu-satunya cara /biometric-unlock
    mau membuka kunci. Aplikasi lain di HP yang menjangkau 127.0.0.1 tidak
    bisa memanggil fungsi ini (Python-nya hidup di dalam proses app ini),
    jadi tidak bisa membuka kunci tanpa sidik jari."""
    if not is_biometric_enabled():
        return None
    now = time.time()
    for token, expires in list(_unlock_tokens.items()):
        if expires < now:
            _unlock_tokens.pop(token, None)
    token = secrets.token_urlsafe(24)
    _unlock_tokens[token] = now + UNLOCK_TOKEN_TTL_SECONDS
    return token


def _consume_unlock_token(token):
    expires = _unlock_tokens.pop(token, None) if token else None
    return expires is not None and expires >= time.time()


# ============================================================
# Dua bahasa (Indonesia / Inggris). Teks Indonesia di kode/template adalah
# "kunci"-nya; kamus _EN di bawah berisi padanan Inggrisnya. Teks yang tidak
# ada di kamus tampil apa adanya (Indonesia). Pilihan bahasa disimpan di
# security.json (app ini dipakai satu orang) supaya halaman login pun ikut.
# ============================================================

LANGS = ("id", "en")

_EN = {
    # login
    "Masuk": "Sign in",
    "Login": "Login",
    "Silakan masuk untuk melanjutkan.": "Please sign in to continue.",
    "Tampilkan password": "Show password",
    "Masuk pakai Sidik Jari": "Sign in with Fingerprint",
    "Preferensi Tampilan": "Display Preferences",
    "Terlalu banyak percobaan salah. Coba lagi %(wait)s detik lagi.":
        "Too many wrong attempts. Try again in %(wait)s seconds.",
    "Username atau password salah.": "Wrong username or password.",
    " Login ditahan %(wait)s detik.": " Sign-in is paused for %(wait)s seconds.",
    "Login sedang ditahan %(wait)s detik karena terlalu banyak percobaan salah.":
        "Sign-in is paused for %(wait)s seconds because of too many wrong attempts.",
    # halaman utama
    "Buat Kode Aktivasi": "Create Activation Code",
    "Kode untuk <b>%(shop)s</b> (%(label)s) berhasil dibuat.":
        "Code for <b>%(shop)s</b> (%(label)s) was created.",
    "Kode Aktivasi": "Activation Code",
    "Salin Kode Aktivasi": "Copy Activation Code",
    "Kirim lewat WhatsApp": "Send via WhatsApp",
    "+ Buat Kode Baru": "+ Create New Code",
    "Kode Perangkat (dari HP pembeli)": "Device Code (from the buyer's phone)",
    "Nama Customer": "Customer Name",
    "Nama Toko/Kedai/Cafe": "Shop / Cafe Name",
    "Alamat Toko": "Shop Address",
    "No HP": "Phone Number",
    "08xx atau 62xx": "08xx or 62xx",
    "Jenis Lisensi": "License Type",
    "Beli Putus": "One-time Purchase",
    "Sewa Mingguan": "Weekly Rental",
    "Sewa Bulanan": "Monthly Rental",
    "Sewa Tahunan": "Yearly Rental",
    "Riwayat (%(n)s terakhir)": "History (last %(n)s)",
    "Toko": "Shop",
    "Jenis": "Type",
    "Tgl": "Date",
    "s/d": "until",
    "Salin": "Copy",
    "Belum ada riwayat.": "No history yet.",
    "Ekspor Riwayat (CSV)": "Export History (CSV)",
    "Dasbor Lisensi": "License Dashboard",
    "Pembuat Kode Aktivasi": "Activation Code Generator",
    "Menu": "Menu",
    "Buat Kode": "Create Code",
    "Riwayat": "History",
    "Ekspor CSV": "Export CSV",
    "Pantau Aplikasi": "App Monitor",
    "Kirim lewat WhatsApp (pilih kontak)": "Send via WhatsApp (choose contact)",
    "Kirim ke nomor pelanggan": "Send to a customer's number",
    "Ketuk satu nama: WhatsApp terbuka ke nomor itu dengan kode sudah terisi. Tekan Kirim di WhatsApp.": "Tap a name: WhatsApp opens to that number with the code filled in. Press Send in WhatsApp.",
    "Siaran ke pelanggan": "Broadcast to customers",
    "Siaran aktif:": "Active broadcast:",
    "Belum ada siaran aktif. Pesan tampil sebagai banner di bagian atas layar pemilik toko, sekali per siaran, dan hanya pada pelanggan yang status aktifnya menyala.": "No active broadcast. The message appears as a banner at the top of the shop owner's screen, once per broadcast, and only for customers who have the active status switch on.",
    "Pesan (maks. %(n)s karakter, teks biasa)": "Message (max %(n)s characters, plain text)",
    "Tampil selama": "Show for",
    "%(n)s hari": "%(n)s days",
    "Kirim siaran": "Send broadcast",
    "Hapus siaran": "Delete broadcast",
    "Siaran tidak valid (maksimal %(n)s karakter).": "Invalid broadcast (max %(n)s characters).",
    "Siaran terkirim. Muncul di aplikasi pelanggan saat mereka berikutnya terhubung.": "Broadcast sent. It appears in customers' apps the next time they connect.",
    "Siaran dihapus.": "Broadcast deleted.",
    "Gagal mengirim siaran. Periksa internet dan token.": "Could not send the broadcast. Check the internet connection and token.",
    "Hubungkan ke server Pantau (lihat monitor-server/README.md) untuk melihat pelanggan yang sedang memakai aplikasi.": "Connect to the Monitor server (see monitor-server/README.md) to see which customers are using the app.",
    "Alamat server Pantau": "Monitor server address",
    "Token admin": "Admin token",
    "Simpan": "Save",
    "Online sekarang": "Online now",
    "Aktif 24 jam terakhir": "Active in the last 24 hours",
    "Perangkat melapor": "Devices reporting",
    "Belum update (terbaru %(ver)s)": "Not updated (latest %(ver)s)",
    "Perangkat": "Devices",
    "Percobaan (belum membeli)": "Trial (not purchased)",
    "Tidak ada di riwayat penjualan": "Not in sales history",
    "Online": "Online",
    "perlu update": "needs update",
    "Belum ada perangkat yang melapor. Aplikasi mengirim status saat dibuka dan ada internet.": "No device has reported yet. The app sends its status when opened with internet access.",
    "Muat ulang": "Reload",
    "Putuskan sambungan": "Disconnect",
    "Putuskan sambungan ke server Pantau?": "Disconnect from the Monitor server?",
    "Token admin ditolak server. Putuskan sambungan lalu isi ulang tokennya.": "The server rejected the admin token. Disconnect and enter the token again.",
    "Tidak bisa terhubung ke server Pantau (%(why)s). Periksa internet HP ini lalu muat ulang.": "Cannot reach the Monitor server (%(why)s). Check this phone's internet connection and reload.",
    "Alamat harus diawali https:// dan token wajib diisi.": "The address must start with https:// and the token is required.",
    "baru saja": "just now",
    "%(n)s menit lalu": "%(n)s min ago",
    "%(n)s jam lalu": "%(n)s h ago",
    "%(n)s hari lalu": "%(n)s d ago",
    "Percobaan": "Trial",
    "Beli putus": "One-time purchase",
    "Sewa": "Rental",
    "Sewa habis": "Rental ended",
    "Pelanggan (perangkat)": "Customers (devices)",
    "Aktif sekarang": "Active now",
    "Sewa berakhir dalam 30 hari": "Rentals ending within 30 days",
    "Sewa sudah berakhir": "Rentals expired",
    "Pendapatan": "Revenue",
    "Bulan ini (%(n)s penjualan)": "This month (%(n)s sales)",
    "Bulan lalu": "Last month",
    "Total": "Total",
    "Total penjualan kode": "Total codes sold",
    "Isi kolom Harga saat membuat kode, supaya pendapatan terhitung di sini.": "Fill in the Price field when creating a code so revenue is counted here.",
    "Segera berakhir (30 hari)": "Ending soon (30 days)",
    "sisa %(n)s hari": "%(n)s days left",
    "Ingatkan": "Remind",
    "Tidak ada sewa yang akan berakhir dalam 30 hari.": "No rentals ending within 30 days.",
    "Sudah berakhir (90 hari terakhir)": "Expired (last 90 days)",
    "berakhir %(until)s": "ended %(until)s",
    "Tawarkan": "Offer renewal",
    "Tidak ada.": "None.",
    "Rincian paket (status terakhir tiap perangkat)": "Plans (latest status per device)",
    "Kembali": "Back",
    "Harga (Rp, boleh dikosongkan)": "Price (Rp, optional)",
    "mis. 99000": "e.g. 99000",
    "Halo %(name)s, paket sewa Oru POS GO untuk %(shop)s berakhir tanggal %(until)s. Kalau mau diperpanjang, kabari ya. Data toko tetap aman.":
        "Hi %(name)s, your Oru POS GO rental for %(shop)s ends on %(until)s. Let me know if you would like to renew. Your store data stays safe.",
    "Halo %(name)s, paket sewa Oru POS GO untuk %(shop)s sudah berakhir tanggal %(until)s. Mau diperpanjang? Data toko Anda tetap aman dan akan tampil kembali setelah diaktifkan.":
        "Hi %(name)s, your Oru POS GO rental for %(shop)s ended on %(until)s. Would you like to renew? Your store data is safe and will be back once reactivated.",
    "Keamanan": "Security",
    "Kunci App": "Lock App",
    "Kode Perangkat, Nama Customer, dan Nama Toko wajib diisi.":
        "Device Code, Customer Name and Shop Name are required.",
    "Halo %(name)s, ini Kode Aktivasi Oru POS GO untuk %(shop)s:\n\n%(code)s\n\nBuka Oru POS GO, lalu tempel kode ini di kolom Kode Aktivasi.":
        "Hello %(name)s, here is your Oru POS GO Activation Code for %(shop)s:\n\n%(code)s\n\nOpen Oru POS GO, then paste this code into the Activation Code field.",
    # keamanan
    "Ganti Password": "Change Password",
    "Password lama": "Current password",
    "Password baru (minimal %(n)s karakter)": "New password (at least %(n)s characters)",
    "Ulangi password baru": "Repeat new password",
    "Simpan Password Baru": "Save New Password",
    "Username tetap <b>%(user)s</b>. Kalau password baru ini sampai lupa, satu-satunya jalan adalah menghapus data aplikasi lewat Setelan Android (Info aplikasi &rarr; Penyimpanan &rarr; Hapus data) - password kembali ke bawaan, tapi <b>riwayat pelanggan ikut hilang</b>. Catat password baru di tempat aman.":
        "The username stays <b>%(user)s</b>. If you forget the new password, the only way out is to clear the app data in Android Settings (App info &rarr; Storage &rarr; Clear data) - the password goes back to the default, but <b>the customer history is lost too</b>. Keep the new password somewhere safe.",
    "Kunci Aplikasi": "App Lock",
    "Boleh masuk pakai sidik jari": "Allow fingerprint sign-in",
    "Kunci otomatis saat aplikasi ditutup / pindah ke aplikasi lain":
        "Lock automatically when the app is closed / switched away",
    "Kunci otomatis kalau tidak dipakai selama": "Lock automatically after being idle for",
    "Tidak pernah": "Never",
    "%(n)s menit": "%(n)s minutes",
    "Simpan Pengaturan Kunci": "Save Lock Settings",
    "Perlindungan tebak password": "Password guessing protection",
    "Salah password %(a)s kali berturut-turut: login ditahan %(b)s detik, lalu makin lama untuk tiap salah berikutnya (maksimal %(c)s menit). Berhasil masuk mereset hitungannya.":
        "After %(a)s wrong passwords in a row, sign-in is paused for %(b)s seconds, then longer for each further mistake (up to %(c)s minutes). A successful sign-in resets the count.",
    "&larr; Kembali": "&larr; Back",
    "Password lama salah.": "The current password is wrong.",
    "Password baru minimal %(n)s karakter.": "The new password must be at least %(n)s characters.",
    "Password baru dan ulangannya tidak sama.": "The new password and its repeat do not match.",
    "Password baru harus berbeda dari password lama.": "The new password must differ from the current one.",
    "Password berhasil diganti. Pakai password baru saat login berikutnya.":
        "Password changed. Use the new password next time you sign in.",
    "Pengaturan kunci disimpan.": "Lock settings saved.",
}

_FLAG_ID = ('<svg viewBox="0 0 3 2" xmlns="http://www.w3.org/2000/svg"><rect width="3" height="1" fill="#e70011"/>'
            '<rect width="3" height="1" y="1" fill="#fff"/></svg>')
_FLAG_EN = ('<svg viewBox="0 0 60 30" xmlns="http://www.w3.org/2000/svg"><rect width="60" height="30" fill="#00247d"/>'
            '<path d="M0,0 L60,30 M60,0 L0,30" stroke="#fff" stroke-width="6"/>'
            '<path d="M0,0 L60,30 M60,0 L0,30" stroke="#cf142b" stroke-width="2"/>'
            '<path d="M30,0 V30 M0,15 H60" stroke="#fff" stroke-width="10"/>'
            '<path d="M30,0 V30 M0,15 H60" stroke="#cf142b" stroke-width="6"/></svg>')


def get_language():
    cached = g.get("_oru_lang") if has_request_context() else None
    if cached:
        return cached
    lang = load_security().get("language", "id")
    if lang not in LANGS:
        lang = "id"
    if has_request_context():
        g._oru_lang = lang
    return lang


def _translate(text, kwargs):
    base = _EN.get(text, text) if get_language() == "en" else text
    return base % kwargs if kwargs else base


def tr(text, **kwargs):
    """Terjemahan untuk template/pesan di layar (nilai yang disisipkan di-escape)."""
    return Markup(_translate(text, {k: escape(v) for k, v in kwargs.items()}))


def tr_plain(text, **kwargs):
    """Terjemahan teks biasa (mis. pesan WhatsApp) - tanpa escape HTML."""
    return _translate(text, kwargs)


def lang_switch(next_path):
    """Tombol bendera ID / EN (seperti "Preferensi Tampilan" di aplikasi POS GO)."""
    current = get_language()
    links = []
    for code, title, flag in (("id", "Bahasa Indonesia", _FLAG_ID), ("en", "English", _FLAG_EN)):
        href = url_for("set_language", code=code, next=next_path)
        links.append(
            '<a href="%s" class="lang-flag-btn%s" title="%s">%s</a>'
            % (escape(href), " active" if current == code else "", title, flag)
        )
    return Markup('<div class="lang-row">' + "".join(links) + "</div>")


_NAV_SCRIPT = """<script>
  (function () {
    var lang = document.documentElement.lang === "en" ? "en-US" : "id-ID";
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    function tick() {
      var d = new Date();
      var date = d.toLocaleDateString(lang, {weekday: "long", day: "2-digit", month: "long", year: "numeric"}).toUpperCase();
      var el = document.getElementById("navDate"), clk = document.getElementById("navClock");
      if (el) el.textContent = date;
      if (clk) clk.textContent = pad(d.getHours()) + "." + pad(d.getMinutes()) + "." + pad(d.getSeconds());
    }
    tick(); setInterval(tick, 1000);
  })();
</script>"""


def navbar(next_path):
    """Navbar atas seperti POS GO: logo + nama aplikasi di kiri, bendera bahasa di kanan, tanggal & jam di bawah."""
    return Markup(
        '<div class="app-nav"><div class="nav-top">'
        '<a class="nav-brand" href="%s"><img src="%s" alt=""><span>Oru Go License</span></a>%s</div>'
        '<div class="nav-clock"><span id="navDate"></span><b id="navClock"></b></div></div>%s'
        % (escape(url_for("index")), _LOGO_URI, lang_switch(next_path), Markup(_NAV_SCRIPT))
    )


# ============================================================
# Database riwayat (sqlite3 polos - datanya kecil & sederhana, tidak
# perlu ORM).
# ============================================================

def _db_path(data_dir):
    return os.path.join(data_dir, "licenses.db")


def _init_db(data_dir):
    conn = sqlite3.connect(_db_path(data_dir))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            shop_name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            license_type TEXT NOT NULL,
            rental_period TEXT,
            device_code TEXT NOT NULL,
            expiry_token TEXT NOT NULL,
            activation_code TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # kolom harga (opsional) ditambahkan belakangan - database lama dimigrasi di sini
    columns = {row[1] for row in conn.execute("PRAGMA table_info(customers)")}
    if "price" not in columns:
        conn.execute("ALTER TABLE customers ADD COLUMN price INTEGER")
    conn.commit()
    conn.close()


def _save_record(data_dir, fields):
    conn = sqlite3.connect(_db_path(data_dir))
    conn.execute(
        """INSERT INTO customers
           (customer_name, shop_name, address, phone, license_type, rental_period,
            device_code, expiry_token, activation_code, price, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
        (
            fields["customer_name"], fields["shop_name"], fields["address"], fields["phone"],
            fields["license_type"], fields["rental_period"], fields["device_code"],
            fields["expiry_token"], fields["activation_code"], fields.get("price"),
        ),
    )
    conn.commit()
    conn.close()


def _list_records(data_dir, limit=30):
    conn = sqlite3.connect(_db_path(data_dir))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM customers ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def _csv_cell(value):
    """Cegah 'CSV injection': teks yang diawali = + - @ dianggap rumus oleh Excel/Sheets."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _export_csv(data_dir):
    """Seluruh riwayat (bukan hanya yang tampil di layar) sebagai teks CSV, UTF-8 dengan BOM
    supaya Excel membaca huruf Indonesia dengan benar."""
    conn = sqlite3.connect(_db_path(data_dir))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    conn.close()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Tanggal", "Nama customer", "Nama toko", "Alamat", "Telepon", "Jenis lisensi",
                     "Masa sewa", "Berlaku sampai", "Harga (Rp)", "Kode perangkat", "Kode aktivasi"])
    for r in rows:
        token = r["expiry_token"]
        until = "Permanen" if token == "PERMANENT" else "%s-%s-%s" % (token[0:4], token[4:6], token[6:8])
        writer.writerow([_csv_cell(v) for v in (
            r["created_at"], r["customer_name"], r["shop_name"], r["address"], r["phone"],
            "Beli putus" if r["license_type"] == "buy" else "Sewa",
            r["rental_period"] or "", until, r["price"] if r["price"] is not None else "",
            r["device_code"], r["activation_code"],
        )])
    return "\ufeff" + out.getvalue()


def _parse_price(text):
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    return int(digits) if digits else None


def _rupiah(value):
    return "Rp " + "{:,}".format(int(value or 0)).replace(",", ".")


def _expiry_date(token):
    return date(int(token[0:4]), int(token[4:6]), int(token[6:8]))


def _dashboard_data(data_dir, today=None):
    """Ringkasan untuk Dasbor Lisensi. Status tiap perangkat diambil dari catatan TERAKHIR
    perangkat itu (perpanjangan membuat catatan baru untuk Kode Perangkat yang sama)."""
    today = today or date.today()
    conn = sqlite3.connect(_db_path(data_dir))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    conn.close()

    latest = {}
    for r in rows:
        latest[r["device_code"]] = r  # urutan naik: yang terakhir menang

    expiring, expired, labels = [], [], {}
    active = 0
    for r in latest.values():
        label = LICENSE_LABELS["buy"] if r["license_type"] == "buy" else LICENSE_LABELS[r["rental_period"]]
        labels[label] = labels.get(label, 0) + 1
        if r["expiry_token"] == "PERMANENT":
            active += 1
            continue
        until = _expiry_date(r["expiry_token"])
        days = (until - today).days
        item = {"shop": r["shop_name"], "customer": r["customer_name"], "phone": r["phone"], "label": tr(label),
                "days": days, "until": until.strftime("%d-%m-%Y"), "date": until}
        if days < 0:
            if days >= -90:
                expired.append(item)
        else:
            active += 1
            if days <= 30:
                expiring.append(item)
    expiring.sort(key=lambda i: i["days"])
    expired.sort(key=lambda i: -i["days"])

    for i in expiring:
        i["wa"] = _whatsapp_link(i["phone"], tr_plain(
            "Halo %(name)s, paket sewa Oru POS GO untuk %(shop)s berakhir tanggal %(until)s. "
            "Kalau mau diperpanjang, kabari ya. Data toko tetap aman.",
            name=i["customer"], shop=i["shop"], until=i["until"]))
    for i in expired:
        i["wa"] = _whatsapp_link(i["phone"], tr_plain(
            "Halo %(name)s, paket sewa Oru POS GO untuk %(shop)s sudah berakhir tanggal %(until)s. "
            "Mau diperpanjang? Data toko Anda tetap aman dan akan tampil kembali setelah diaktifkan.",
            name=i["customer"], shop=i["shop"], until=i["until"]))

    month_key = today.strftime("%Y-%m")
    last_key = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    rev = {"month": 0, "last": 0, "total": 0}
    sales_month = 0
    has_price = False
    for r in rows:
        if r["created_at"][:7] == month_key:
            sales_month += 1
        if r["price"] is None:
            continue
        has_price = True
        rev["total"] += r["price"]
        if r["created_at"][:7] == month_key:
            rev["month"] += r["price"]
        elif r["created_at"][:7] == last_key:
            rev["last"] += r["price"]

    return {
        "customers": len(latest), "active": active, "expiring": expiring, "expired": expired,
        "by_label": sorted(labels.items(), key=lambda kv: -kv[1]),
        "has_price": has_price, "rev_month": _rupiah(rev["month"]), "rev_last": _rupiah(rev["last"]),
        "rev_total": _rupiah(rev["total"]), "sales_month": sales_month, "sales_total": len(rows),
    }


# ============================================================
# Pantau Aplikasi: perangkat GO yang melapor status ke server Pantau (monitor-server/)
# ============================================================

ONLINE_SECONDS = 600


def _monitor_file(data_dir):
    return os.path.join(data_dir, "monitor.json")


def _load_monitor(data_dir):
    try:
        with open(_monitor_file(data_dir), encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("url") and cfg.get("token"):
            return cfg
    except (OSError, ValueError):
        pass
    return None


def _save_monitor(data_dir, url, token):
    with open(_monitor_file(data_dir), "w", encoding="utf-8") as f:
        json.dump({"url": url, "token": token}, f)


def _valid_monitor_url(url):
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if not parsed.netloc:
        return False
    local = parsed.hostname in ("127.0.0.1", "localhost")
    return parsed.scheme == "https" or (parsed.scheme == "http" and local)


def _fetch_devices(cfg, timeout=15):
    """(daftar_perangkat, siaran_aktif, pesan_error). Gagal terhubung = daftar kosong + pesan, tidak melempar."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        cfg["url"].rstrip("/") + "/v1/devices", headers={"Authorization": "Bearer " + cfg["token"], "User-Agent": "OruGoLicense"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("devices", []), data.get("broadcast"), None
    except urllib.error.HTTPError as exc:
        return [], None, "token" if exc.code == 401 else "http %s" % exc.code
    except Exception as exc:
        reason = getattr(exc, "reason", None) or exc          # URLError membungkus alasan aslinya
        return [], None, "%s: %s" % (type(reason).__name__, str(reason)[:90])


BROADCAST_MAX_CHARS = 280
BROADCAST_DAYS = (3, 7, 14, 30)


def _send_broadcast(cfg, text, days, timeout=8):
    """Pasang (atau hapus bila text kosong) siaran untuk semua pelanggan. True bila server menerima."""
    import urllib.request

    body = json.dumps({"text": text, "days": days}).encode("utf-8")
    request = urllib.request.Request(
        cfg["url"].rstrip("/") + "/v1/broadcast", data=body, method="PUT",
        headers={"Authorization": "Bearer " + cfg["token"], "Content-Type": "application/json", "User-Agent": "OruGoLicense"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def _version_tuple(text):
    parts = []
    for piece in str(text).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _ago(seconds):
    if seconds < 90:
        return tr_plain("baru saja")
    if seconds < 3600:
        return tr_plain("%(n)s menit lalu", n=seconds // 60)
    if seconds < 86400:
        return tr_plain("%(n)s jam lalu", n=seconds // 3600)
    return tr_plain("%(n)s hari lalu", n=seconds // 86400)


MODE_LABELS = {"trial": "Percobaan", "permanent": "Beli putus", "rental": "Sewa", "expired": "Sewa habis", "unknown": "?"}


def _monitor_view(data_dir, devices, now=None):
    """Gabungkan perangkat yang melapor dengan riwayat penjualan (lewat Kode Perangkat)."""
    now = now or int(time.time())
    conn = sqlite3.connect(_db_path(data_dir))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    conn.close()
    known = {}
    for r in rows:
        known[r["device_code"]] = r  # catatan terakhir menang

    latest = max((_version_tuple(d["version"]) for d in devices), default=())
    items = []
    for d in devices:
        age = max(0, now - int(d["last_seen"]))
        rec = known.get(d["device"])
        until = d["expiry"]
        items.append({
            "device": d["device"], "short": d["device"][:4] + "..." + d["device"][-4:],
            "shop": rec["shop_name"] if rec else None, "customer": rec["customer_name"] if rec else None,
            "phone": rec["phone"] if rec else None,
            "trial": d["mode"] == "trial", "online": age < ONLINE_SECONDS, "age": age, "ago": _ago(age),
            "version": d["version"], "outdated": bool(latest) and _version_tuple(d["version"]) < latest,
            "mode": tr_plain(MODE_LABELS.get(d["mode"], "?")), "platform": d["platform"],
            "until": ("%s-%s-%s" % (until[0:4], until[4:6], until[6:8])) if until else "",
        })
    items.sort(key=lambda i: i["age"])
    return {
        "rows": items, "total": len(items), "online": sum(1 for i in items if i["online"]),
        "today": sum(1 for i in items if i["age"] < 86400), "outdated": sum(1 for i in items if i["outdated"]),
        "latest": ".".join(str(n) for n in latest), "unregistered": sum(1 for i in items if not i["shop"]),
    }



def _whatsapp_link(phone, message, allow_pick=False):
    """Tautan WhatsApp berisi pesan. Tanpa nomor HP: None, atau (allow_pick) tautan tanpa penerima
    sehingga WhatsApp membuka daftar kontak untuk dipilih penjual."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        if allow_pick:
            from urllib.parse import quote
            return f"https://wa.me/?text={quote(message)}"
        return None
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    from urllib.parse import quote
    return f"https://wa.me/{digits}?text={quote(message)}"


def _wa_contacts(data_dir, message, limit=30):
    """Daftar pelanggan (satu baris per nomor HP, riwayat terbaru dulu) beserta tautan WhatsApp berisi `message`.
    Dipakai di halaman hasil kode: ketuk satu nama untuk membuka WhatsApp ke nomor itu dengan pesan terisi."""
    seen, contacts = set(), []
    for r in _list_records(data_dir, limit=300):          # urut terbaru dulu
        link = _whatsapp_link(r["phone"], message)
        if not link or link in seen:
            continue
        seen.add(link)
        contacts.append({"shop": r["shop_name"], "customer": r["customer_name"], "phone": r["phone"], "link": link,
                         "rental": r["license_type"] != "buy"})
        if len(contacts) >= limit:
            break
    return contacts


# ============================================================
# Halaman (semua inline - app kecil, tidak perlu folder templates/)
# ============================================================

_BASE_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0;
         margin: 0; padding: 20px 16px 40px; min-height: 100vh; }
  .card { max-width: 520px; margin: 24px auto; background: #1e293b; border-radius: 16px; padding: 24px; }
  h1 { font-family: 'Poppins', 'Inter', sans-serif; font-size: 1.25rem; margin: 0 0 16px; }
  h2 { font-size: 1rem; margin: 24px 0 10px; color: #94a3b8; }
  label { display: block; font-size: 0.85rem; color: #cbd5e1; margin: 12px 0 6px; font-weight: 600; }
  input[type=text], input[type=password], input[type=tel], select, textarea {
    width: 100%; background: #0f172a; border: 1px solid #334155; color: #e2e8f0;
    border-radius: 10px; padding: 12px; font-size: 0.95rem;
  }
  .radio-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
  .radio-row label { display: flex; align-items: center; gap: 6px; background: #0f172a;
    border: 1px solid #334155; border-radius: 10px; padding: 8px 12px; font-weight: 500;
    margin: 0; flex: 1 1 auto; }
  button, .btn { background: #f97316; color: #fff; border: none; border-radius: 10px; padding: 12px 16px;
           font-weight: 600; font-size: 0.95rem; width: 100%; margin-top: 18px; display: block;
           text-align: center; text-decoration: none; }
  .btn-secondary { background: #334155; }
  .error { background: #7f1d1d; color: #fecaca; border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; font-size: 0.85rem; }
  .result-code { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 12px;
    font-family: monospace; font-size: 0.8rem; word-break: break-all; margin: 10px 0; max-height: 160px; overflow-y: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid #334155; }
  th { color: #94a3b8; font-weight: 600; }
  .row-actions { display: flex; gap: 6px; }
  .row-actions button { width: auto; margin: 0; padding: 6px 10px; font-size: 0.75rem; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.7rem; background: #334155; }
"""

_LOGIN_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0;
         margin: 0; padding: 0; min-height: 100vh; }
  .login-page-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: 100vh; padding: 32px 16px; }
  .login-card { max-width: 330px; width: 100%; background: #1e293b; border-radius: 28px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.45); padding: 32px 26px 26px; text-align: center; }
  .login-logo-wrap { position: relative; width: 74px; height: 74px; margin: 0 auto 16px; }
  .login-logo-circle { width: 74px; height: 74px; border-radius: 50%; background: #0f172a;
    display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
  .login-sep { height: 1px; background: #334155; margin: 18px 4px 14px; }
  .login-logo-circle img { width: 60px; height: 60px; object-fit: contain; }
  .login-dot { position: absolute; border-radius: 50%; }
  .login-dot-1 { width: 14px; height: 14px; background: #f97316; top: -5px; right: -5px; }
  .login-dot-2 { width: 9px; height: 9px; background: #38bdf8; bottom: 5px; left: -10px; }
  .login-dot-3 { width: 6px; height: 6px; background: #f97316; bottom: -5px; right: 14px; opacity: 0.55; }
  .login-title { font-family: 'Poppins', 'Inter', sans-serif; font-weight: 700; font-size: 1.1rem; color: #e2e8f0; margin: 0 0 3px; }
  .login-subtitle { color: #94a3b8; font-size: 0.78rem; margin: 0 0 22px; line-height: 1.5; }
  .login-error { background: #7f1d1d; color: #fecaca; border-radius: 10px; padding: 10px 14px;
    margin-bottom: 14px; font-size: 0.8rem; text-align: left; }
  .login-form { text-align: left; }
  .login-field { margin-bottom: 12px; }
  .login-input-wrap { position: relative; }
  .login-input { width: 100%; border: none; background: #0f172a; border-radius: 999px;
    padding: 10px 16px; font-size: 0.85rem; color: #e2e8f0; }
  .login-input-wrap .login-input { padding-right: 42px; }
  .login-input:focus { outline: none; box-shadow: 0 0 0 3px rgba(240,120,40,0.25); }
  .login-input::placeholder { color: #64748b; }
  .login-eye-btn { position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
    box-shadow: 0 2px 6px rgba(240,120,40,0.28);
    width: 28px; height: 28px; border: none; background: transparent; color: #94a3b8;
    border-radius: 999px; display: flex; align-items: center; justify-content: center; padding: 0; }
  .login-eye-btn:active { background: #334155; }
  .login-submit-btn { width: 100%; border: none; background: #f97316; color: #fff; font-weight: 700;
    letter-spacing: 0.5px; text-transform: uppercase; font-size: 0.8rem; padding: 12px; border-radius: 999px;
    margin-top: 6px; box-shadow: 0 10px 22px rgba(240,120,40,0.35); display: flex; align-items: center;
    justify-content: center; gap: 8px; }
  .login-bio-btn { width: 100%; border: none; background: #334155; color: #e2e8f0; font-weight: 600;
    font-size: 0.85rem; padding: 12px; border-radius: 999px; margin-top: 12px; }
  .login-credit { margin-top: 18px; text-align: center; font-size: 0.78rem; color: #64748b; }
"""

_NAV_CSS = """
  .app-nav { max-width: 520px; margin: 0 auto; background: #1e293b; border-radius: 20px; padding: 12px 16px 10px;
    border-bottom: 3px solid #0e7490; box-shadow: 0 4px 14px rgba(0,0,0,0.25); }
  .nav-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .nav-brand { display: flex; align-items: center; gap: 10px; color: #f1f5f9; text-decoration: none; min-width: 0;
    font-family: 'Poppins', 'Inter', sans-serif; font-weight: 700; font-size: 1.05rem; }
  .nav-brand img { width: 38px; height: 38px; border-radius: 50%; background: #0f172a; padding: 5px; flex: 0 0 auto; }
  .nav-brand span { white-space: nowrap; }
  .app-nav .lang-row { margin: 0; gap: 8px; flex: 0 0 auto; }
  .app-nav .lang-flag-btn { width: 32px; height: 32px; }
  .nav-clock { display: flex; justify-content: center; align-items: baseline; gap: 8px; margin-top: 8px;
    font-size: 0.68rem; letter-spacing: 0.8px; color: #94a3b8; font-weight: 700; }
  .nav-clock b { color: #f97316; font-size: 1.05rem; letter-spacing: 0.5px; font-family: 'Poppins', 'Inter', sans-serif; }
  .app-nav + .card { margin-top: 14px; }
  @media (max-width: 360px) { .nav-clock { flex-direction: column; align-items: center; gap: 2px; } }
"""

_LANG_CSS = """
  .lang-row { display: flex; justify-content: center; gap: 10px; margin-top: 18px; }
  .lang-flag-btn { width: 36px; height: 36px; border-radius: 50%; background: #0f172a; border: 2px solid transparent;
    display: flex; align-items: center; justify-content: center; opacity: 0.55; padding: 0; text-decoration: none;
    box-shadow: 0 2px 6px rgba(240,120,40,0.28); }
  .lang-flag-btn svg { width: 22px; height: 15px; border-radius: 2px; display: block; }
  .lang-flag-btn.active { opacity: 1; border-color: #f97316; }
  .login-divider { display: flex; align-items: center; gap: 10px; margin: 18px 0 12px; color: #64748b;
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; }
  .login-divider + .lang-row { margin-top: 0; }
  .login-divider::before, .login-divider::after { content: ""; flex: 1; height: 1px; background: #334155; }
"""
# CSS di sini string tetap dari kode sendiri (bukan input pengguna); Markup supaya
# tanda kutip di dalamnya (content: "") tidak di-escape Jinja jadi &#34;.
_BASE_STYLE = Markup(FONT_CSS + _BASE_STYLE + _LANG_CSS + _NAV_CSS)
_LOGIN_STYLE = Markup(FONT_CSS + _LOGIN_STYLE + _LANG_CSS)

_LOGIN_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ _('Masuk') }} - Oru Go License</title><style>{{ style }}</style></head><body>
<div class="login-page-wrap">
  <div class="login-card">
    <div class="login-logo-wrap">
      <span class="login-dot login-dot-1"></span>
      <span class="login-dot login-dot-2"></span>
      <span class="login-dot login-dot-3"></span>
      <div class="login-logo-circle">
        <img src="data:image/png;base64,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" alt="Oru Go License">
      </div>
    </div>
    <h3 class="login-title">Oru Go License</h3>
    <p class="login-subtitle">{{ _('Silakan masuk untuk melanjutkan.') }}</p>

    {% if error %}<div class="login-error">{{ error }}</div>{% endif %}

    <form method="post" class="login-form">
      <div class="login-field">
        <input type="text" name="username" class="login-input" autocapitalize="off" autocorrect="off" spellcheck="false" autofocus required placeholder="Username">
      </div>
      <div class="login-field login-input-wrap">
        <input type="password" id="loginPassword" name="password" class="login-input" required placeholder="Password">
        <button type="button" id="togglePasswordBtn" class="login-eye-btn" aria-label="{{ _('Tampilkan password') }}">
          <svg id="eyeOpen" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z"/><circle cx="12" cy="12" r="3"/></svg>
          <svg id="eyeClosed" style="display:none" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a21.8 21.8 0 0 1 5.06-5.94M9.9 4.24A10.94 10.94 0 0 1 12 4c7 0 11 7 11 7a21.8 21.8 0 0 1-2.16 3.19M14.12 14.12a3 3 0 1 1-4.24-4.24"/><path d="M1 1l22 22"/></svg>
        </button>
      </div>
      <div class="login-sep"></div>
      <button type="submit" class="login-submit-btn">
        <svg viewBox="0 0 16 16" width="15" height="15" fill="currentColor"><path fill-rule="evenodd" d="M6 3.5a.5.5 0 0 1 .5-.5h8a.5.5 0 0 1 .5.5v9a.5.5 0 0 1-.5.5h-8a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 0-1 0v2A1.5 1.5 0 0 0 6.5 14h8a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 14.5 2h-8A1.5 1.5 0 0 0 5 3.5v2a.5.5 0 0 0 1 0v-2z"/><path fill-rule="evenodd" d="M11.854 8.354a.5.5 0 0 0 0-.708l-3-3a.5.5 0 1 0-.708.708L10.293 7.5H1.5a.5.5 0 0 0 0 1h8.793l-2.147 2.146a.5.5 0 0 0 .708.708l3-3z"/></svg>
        {{ _('Login') }}
      </button>
    </form>

    <button type="button" id="bioBtn" class="login-bio-btn" style="display:none;" onclick="AndroidAuth.authenticate()">{{ _('Masuk pakai Sidik Jari') }}</button>

    <div class="login-divider"><span>{{ _('Preferensi Tampilan') }}</span></div>
    {{ lang_switch('/login') }}
  </div>
  <p class="login-credit">Orulabs &copy; 2026. All rights reserved.</p>
</div>
<script>
  if ({{ 'true' if bio_enabled else 'false' }} && window.AndroidAuth && AndroidAuth.isBiometricAvailable && AndroidAuth.isBiometricAvailable()) {
    document.getElementById('bioBtn').style.display = 'block';
  }
  (function () {
    var btn = document.getElementById("togglePasswordBtn");
    var input = document.getElementById("loginPassword");
    var openIcon = document.getElementById("eyeOpen");
    var closedIcon = document.getElementById("eyeClosed");
    if (!btn || !input) return;
    btn.addEventListener("click", function () {
      var showing = input.type === "text";
      input.type = showing ? "password" : "text";
      openIcon.style.display = showing ? "block" : "none";
      closedIcon.style.display = showing ? "none" : "block";
    });
  })();
</script>
</body></html>
"""

_SECURITY_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ _('Keamanan') }} - Oru Go License</title><style>{{ style }}</style></head><body>
  {{ navbar('/security') }}
  <div class="card">
    <h1>{{ _('Keamanan') }}</h1>

    {% if message %}
      <div class="error" style="{{ 'background:#14532d; color:#bbf7d0;' if message_ok else '' }}">{{ message }}</div>
    {% endif %}

    <h2>{{ _('Ganti Password') }}</h2>
    <form method="post" action="{{ url_for('security_password') }}">
      <label>{{ _('Password lama') }}</label>
      <input type="password" name="old_password" autocomplete="current-password" required>
      <label>{{ _('Password baru (minimal %(n)s karakter)', n=min_length) }}</label>
      <input type="password" name="new_password" autocomplete="new-password" required>
      <label>{{ _('Ulangi password baru') }}</label>
      <input type="password" name="confirm_password" autocomplete="new-password" required>
      <button type="submit">{{ _('Simpan Password Baru') }}</button>
    </form>
    <p style="color:#64748b; font-size:0.8rem;">
      {{ _('Username tetap <b>%(user)s</b>. Kalau password baru ini sampai lupa, satu-satunya jalan adalah menghapus data aplikasi lewat Setelan Android (Info aplikasi &rarr; Penyimpanan &rarr; Hapus data) - password kembali ke bawaan, tapi <b>riwayat pelanggan ikut hilang</b>. Catat password baru di tempat aman.', user=username) }}
    </p>

    <h2>{{ _('Kunci Aplikasi') }}</h2>
    <form method="post" action="{{ url_for('security_settings') }}">
      <label style="display:flex; align-items:center; gap:10px; font-weight:500;">
        <input type="checkbox" name="biometric_enabled" value="1" {{ 'checked' if settings.biometric_enabled else '' }} style="width:auto;">
        {{ _('Boleh masuk pakai sidik jari') }}
      </label>
      <label style="display:flex; align-items:center; gap:10px; font-weight:500;">
        <input type="checkbox" name="lock_on_leave" value="1" {{ 'checked' if settings.lock_on_leave else '' }} style="width:auto;">
        {{ _('Kunci otomatis saat aplikasi ditutup / pindah ke aplikasi lain') }}
      </label>
      <label>{{ _('Kunci otomatis kalau tidak dipakai selama') }}</label>
      <select name="idle_lock_minutes">
        {% for minutes in idle_choices %}
          <option value="{{ minutes }}" {{ 'selected' if settings.idle_lock_minutes == minutes else '' }}>
            {{ _('Tidak pernah') if minutes == 0 else _('%(n)s menit', n=minutes) }}
          </option>
        {% endfor %}
      </select>
      <button type="submit">{{ _('Simpan Pengaturan Kunci') }}</button>
    </form>

    <h2>{{ _('Perlindungan tebak password') }}</h2>
    <p style="color:#94a3b8; font-size:0.85rem; margin:0;">
      {{ _('Salah password %(a)s kali berturut-turut: login ditahan %(b)s detik, lalu makin lama untuk tiap salah berikutnya (maksimal %(c)s menit). Berhasil masuk mereset hitungannya.', a=throttle_after, b=throttle_base, c=throttle_max // 60) }}
    </p>

    <a class="btn btn-secondary" href="{{ url_for('index') }}">{{ _('&larr; Kembali') }}</a>
  </div>
</body></html>
"""


_DASH_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oru Go License</title><style>{{ style }}
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 6px 0 4px; }
  .stat { background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 12px; }
  .stat b { display: block; font-size: 1.35rem; font-family: 'Poppins', 'Inter', sans-serif; color: #f1f5f9; }
  .stat span { font-size: 0.78rem; color: #94a3b8; }
  .stat.warn b { color: #fb923c; }
  .stat.bad b { color: #f87171; }
  .item { display: flex; justify-content: space-between; align-items: center; gap: 10px;
          padding: 10px 0; border-top: 1px solid #334155; }
  .item .who { min-width: 0; flex: 1 1 auto; }
  .item .who div { font-weight: 600; word-break: break-word; }
  .item .btn { flex: 0 0 auto; width: auto; display: inline-block; margin: 0; padding: 8px 12px; font-size: 0.8rem; text-decoration: none; }
  .muted { color: #64748b; font-size: 0.85rem; }
</style></head><body>
  {{ navbar('/dasbor') }}
  <div class="card">
    <h1>{{ _('Dasbor Lisensi') }}</h1>

    <div class="stats">
      <div class="stat"><b>{{ d.customers }}</b><span>{{ _('Pelanggan (perangkat)') }}</span></div>
      <div class="stat"><b>{{ d.active }}</b><span>{{ _('Aktif sekarang') }}</span></div>
      <div class="stat warn"><b>{{ d.expiring|length }}</b><span>{{ _('Sewa berakhir dalam 30 hari') }}</span></div>
      <div class="stat bad"><b>{{ d.expired|length }}</b><span>{{ _('Sewa sudah berakhir') }}</span></div>
    </div>

    <h2>{{ _('Pendapatan') }}</h2>
    {% if d.has_price %}
      <div class="stats">
        <div class="stat"><b>{{ d.rev_month }}</b><span>{{ _('Bulan ini (%(n)s penjualan)', n=d.sales_month) }}</span></div>
        <div class="stat"><b>{{ d.rev_last }}</b><span>{{ _('Bulan lalu') }}</span></div>
        <div class="stat"><b>{{ d.rev_total }}</b><span>{{ _('Total') }}</span></div>
        <div class="stat"><b>{{ d.sales_total }}</b><span>{{ _('Total penjualan kode') }}</span></div>
      </div>
    {% else %}
      <p class="muted">{{ _('Isi kolom Harga saat membuat kode, supaya pendapatan terhitung di sini.') }}</p>
    {% endif %}

    <h2>{{ _('Segera berakhir (30 hari)') }}</h2>
    {% for r in d.expiring %}
      <div class="item">
        <div class="who"><div>{{ r.shop }}</div><span class="muted">{{ r.customer }} &middot; {{ r.label }} &middot; {{ _('sisa %(n)s hari', n=r.days) }} ({{ r.until }})</span></div>
        {% if r.wa %}<a class="btn" href="{{ r.wa }}">{{ _('Ingatkan') }}</a>{% endif %}
      </div>
    {% else %}
      <p class="muted">{{ _('Tidak ada sewa yang akan berakhir dalam 30 hari.') }}</p>
    {% endfor %}

    <h2>{{ _('Sudah berakhir (90 hari terakhir)') }}</h2>
    {% for r in d.expired %}
      <div class="item">
        <div class="who"><div>{{ r.shop }}</div><span class="muted">{{ r.customer }} &middot; {{ r.label }} &middot; {{ _('berakhir %(until)s', until=r.until) }}</span></div>
        {% if r.wa %}<a class="btn" href="{{ r.wa }}">{{ _('Tawarkan') }}</a>{% endif %}
      </div>
    {% else %}
      <p class="muted">{{ _('Tidak ada.') }}</p>
    {% endfor %}

    <h2>{{ _('Rincian paket (status terakhir tiap perangkat)') }}</h2>
    {% for label, n in d.by_label %}
      <div class="item"><div class="who"><div>{{ _(label) }}</div></div><b>{{ n }}</b></div>
    {% else %}
      <p class="muted">{{ _('Belum ada riwayat.') }}</p>
    {% endfor %}

    <a class="btn btn-secondary" href="{{ url_for('index') }}">{{ _('Kembali') }}</a>
  </div>
</body></html>
"""


_MONITOR_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oru Go License</title><style>{{ style }}
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 6px 0 4px; }
  .stat { background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 12px; }
  .stat b { display: block; font-size: 1.35rem; font-family: 'Poppins', 'Inter', sans-serif; color: #f1f5f9; }
  .stat span { font-size: 0.78rem; color: #94a3b8; }
  .stat.ok b { color: #4ade80; }
  .stat.warn b { color: #fb923c; }
  .item { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; padding: 10px 0; border-top: 1px solid #334155; }
  .item .who { min-width: 0; flex: 1 1 auto; }
  .item .who div { font-weight: 600; word-break: break-word; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: #475569; margin-right: 6px; }
  .dot.on { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
  .muted { color: #64748b; font-size: 0.82rem; }
  .tag { display: inline-block; font-size: 0.7rem; padding: 2px 8px; border-radius: 999px; background: #334155; color: #cbd5e1; margin-left: 4px; }
  .tag.warn { background: #7c2d12; color: #fed7aa; }
  .item .btn { flex: 0 0 auto; width: auto; display: inline-block; margin: 0; padding: 8px 12px; font-size: 0.8rem; text-decoration: none; }
</style></head><body>
  {{ navbar('/pantau') }}
  <div class="card">
    <h1>{{ _('Pantau Aplikasi') }}</h1>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}

    {% if not configured %}
      <p class="muted">{{ _('Hubungkan ke server Pantau (lihat monitor-server/README.md) untuk melihat pelanggan yang sedang memakai aplikasi.') }}</p>
      <form method="post" action="{{ url_for('monitor_save') }}">
        <label>{{ _('Alamat server Pantau') }}</label>
        <input type="text" name="url" placeholder="https://orugo-monitor.xxx.workers.dev" autocapitalize="off" autocorrect="off" spellcheck="false" required>
        <label>{{ _('Token admin') }}</label>
        <input type="password" name="token" required>
        <button type="submit">{{ _('Simpan') }}</button>
      </form>
    {% else %}
      <div class="stats">
        <div class="stat ok"><b>{{ v.online }}</b><span>{{ _('Online sekarang') }}</span></div>
        <div class="stat"><b>{{ v.today }}</b><span>{{ _('Aktif 24 jam terakhir') }}</span></div>
        <div class="stat"><b>{{ v.total }}</b><span>{{ _('Perangkat melapor') }}</span></div>
        <div class="stat warn"><b>{{ v.outdated }}</b><span>{{ _('Belum update (terbaru %(ver)s)', ver=v.latest or '-') }}</span></div>
      </div>

      <h2>{{ _('Perangkat') }}</h2>
      {% for i in v.rows %}
        <div class="item">
          <div class="who">
            <div><span class="dot {{ 'on' if i.online else '' }}"></span>{{ i.shop or (_('Percobaan (belum membeli)') if i.trial else _('Tidak ada di riwayat penjualan')) }}</div>
            <span class="muted">
              {% if i.shop %}{{ i.customer }} &middot; {% else %}{{ i.short }} &middot; {% endif %}
              {{ _('Online') if i.online else i.ago }} &middot; v{{ i.version }}{% if i.platform == 'ios' %} (iPhone){% endif %}
            </span>
            <div style="margin-top:4px;">
              <span class="tag">{{ i.mode }}{% if i.until %} {{ i.until }}{% endif %}</span>
              {% if i.outdated %}<span class="tag warn">{{ _('perlu update') }}</span>{% endif %}
            </div>
          </div>
        </div>
      {% else %}
        <p class="muted">{{ _('Belum ada perangkat yang melapor. Aplikasi mengirim status saat dibuka dan ada internet.') }}</p>
      {% endfor %}

      <h2>{{ _('Siaran ke pelanggan') }}</h2>
      {% if notice %}<div class="error"{% if notice[0] == 'ok' %} style="background:#14532d; color:#bbf7d0;"{% endif %}>{{ notice[1] }}</div>{% endif %}
      {% if broadcast %}
        <p class="muted">{{ _('Siaran aktif:') }} <b style="color:#e2e8f0;">{{ broadcast.text }}</b></p>
      {% else %}
        <p class="muted">{{ _('Belum ada siaran aktif. Pesan tampil sebagai banner di bagian atas layar pemilik toko, sekali per siaran, dan hanya pada pelanggan yang status aktifnya menyala.') }}</p>
      {% endif %}
      <form method="post" action="{{ url_for('monitor_broadcast') }}">
        <label>{{ _('Pesan (maks. %(n)s karakter, teks biasa)', n=max_chars) }}</label>
        <textarea name="text" rows="3" maxlength="{{ max_chars }}" style="box-sizing:border-box; font-family:inherit; resize:vertical;"></textarea>
        <label>{{ _('Tampil selama') }}</label>
        <select name="days">{% for n in day_choices %}<option value="{{ n }}"{% if n == 7 %} selected{% endif %}>{{ _('%(n)s hari', n=n) }}</option>{% endfor %}</select>
        <button type="submit">{{ _('Kirim siaran') }}</button>
      </form>
      {% if broadcast %}
        <form method="post" action="{{ url_for('monitor_broadcast') }}"><input type="hidden" name="text" value=""><button type="submit" class="btn-secondary">{{ _('Hapus siaran') }}</button></form>
      {% endif %}

      <a class="btn btn-secondary" href="{{ url_for('monitor_page') }}">{{ _('Muat ulang') }}</a>
      <form method="post" action="{{ url_for('monitor_clear') }}" onsubmit='return confirm({{ _('Putuskan sambungan ke server Pantau?')|tojson }})'>
        <button type="submit" class="btn-secondary">{{ _('Putuskan sambungan') }}</button>
      </form>
    {% endif %}

    <a class="btn btn-secondary" href="{{ url_for('index') }}">{{ _('Kembali') }}</a>
  </div>
</body></html>
"""


_LOGO_URI = re.search(r"data:image/png;base64,[A-Za-z0-9+/=]+", _LOGIN_PAGE).group(0)

_ICONS = {
    "plus": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    "chart": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "pulse": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "download": '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
}


def _icon(name):
    return Markup('<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" stroke-width="2" '
                  'stroke-linecap="round" stroke-linejoin="round">%s</svg>' % _ICONS[name])


_TILE_STYLE = """
  .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .brand img { width: 44px; height: 44px; border-radius: 50%; background: #0f172a; padding: 6px; box-sizing: border-box; }
  .brand h1 { margin: 0; font-size: 1.25rem; }
  .brand span { display: block; font-size: 0.78rem; color: #94a3b8; font-weight: 500; }
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 0 0 4px; }
  .stat { background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 12px; }
  .stat b { display: block; font-size: 1.35rem; font-family: 'Poppins', 'Inter', sans-serif; color: #f1f5f9; }
  .stat span { font-size: 0.78rem; color: #94a3b8; }
  .stat.warn b { color: #fb923c; }
  .stat.bad b { color: #f87171; }
  .home-stats { max-width: 520px; margin: 14px auto 0; }
  .home-stats .stat { background: #1e293b; }
  .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 8px; }
  .tile, .tile:visited { display: flex; flex-direction: column; align-items: center; justify-content: flex-start; gap: 10px;
    background: #0f172a; border: 1px solid #334155; border-top: 3px solid #f97316; border-radius: 18px;
    padding: 16px 4px 12px; color: #f1f5f9; text-decoration: none; font-size: 0.8rem; font-weight: 600;
    text-align: center; width: 100%; margin: 0; min-height: 128px; box-sizing: border-box; line-height: 1.25; }
  .tile:active { transform: scale(0.97); }
  .tile .ico { width: 52px; height: 52px; border-radius: 50%; background: #f97316; display: flex;
    align-items: center; justify-content: center; }
  .tiles form { margin: 0; display: contents; }
"""

_TILE_SET = """
{% macro tile(href, icon, label) %}
  <a class="tile" href="{{ href }}"><span class="ico">{{ icon }}</span>{{ label }}</a>
{% endmacro %}
"""

_HOME_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oru Go License</title><style>{{ style }}""" + _TILE_STYLE + """</style></head><body>
  {{ navbar('/') }}
""" + _TILE_SET + """
  <div class="stats home-stats">
    <div class="stat"><b>{{ d.customers }}</b><span>{{ _('Pelanggan (perangkat)') }}</span></div>
    <div class="stat"><b>{{ d.active }}</b><span>{{ _('Aktif sekarang') }}</span></div>
    <div class="stat warn"><b>{{ d.expiring|length }}</b><span>{{ _('Sewa berakhir dalam 30 hari') }}</span></div>
    <div class="stat bad"><b>{{ d.expired|length }}</b><span>{{ _('Sewa sudah berakhir') }}</span></div>
  </div>

  <div class="card">
    <h2 style="margin-top:0;">{{ _('Menu') }}</h2>
    <div class="tiles">
      {{ tile(url_for('create_page'), icons.plus, _('Buat Kode')) }}
      {{ tile(url_for('history_page'), icons.list, _('Riwayat')) }}
      {{ tile(url_for('dashboard'), icons.chart, _('Dasbor Lisensi')) }}
      {{ tile(url_for('monitor_page'), icons.pulse, _('Pantau Aplikasi')) }}
      {% if has_records %}{{ tile(url_for('export_csv'), icons.download, _('Ekspor CSV')) }}{% endif %}
      {{ tile(url_for('security_page'), icons.shield, _('Keamanan')) }}
      <form method="post" action="{{ url_for('lock') }}"><button type="submit" class="tile"><span class="ico">{{ icons.lock }}</span>{{ _('Kunci App') }}</button></form>
    </div>
  </div>
</body></html>
"""

_CREATE_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oru Go License</title><style>{{ style }}
  .muted { color: #64748b; font-size: 0.85rem; }
  .contact { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 10px 12px; margin-top: 8px;
    background: #0f172a; border: 1px solid #334155; border-radius: 12px; color: #f1f5f9; text-decoration: none; }
  .contact .who { min-width: 0; display: flex; flex-direction: column; gap: 2px; word-break: break-word; }
  .contact .tag { flex: 0 0 auto; font-size: 0.7rem; padding: 2px 8px; border-radius: 999px; background: #334155; color: #cbd5e1; }
</style></head><body>
  {{ navbar('/buat') }}
  <div class="card">
    <h1>{{ _('Buat Kode Aktivasi') }}</h1>

    {% if result %}
      <div class="error" style="background:#14532d; color:#bbf7d0;">
        {{ _('Kode untuk <b>%(shop)s</b> (%(label)s) berhasil dibuat.', shop=result.shop_name, label=result.license_label) }}
      </div>
      <label>{{ _('Kode Aktivasi') }}</label>
      <div class="result-code" id="resultCode">{{ result.activation_code }}</div>
      <button type="button" onclick="copyText('resultCode')">{{ _('Salin Kode Aktivasi') }}</button>
      {% if result.wa_link %}
        <a class="btn btn-secondary" href="{{ result.wa_link }}">{{ _('Kirim lewat WhatsApp') if not result.wa_pick else _('Kirim lewat WhatsApp (pilih kontak)') }}</a>
      {% endif %}
      {% if result.contacts %}
        <h2>{{ _('Kirim ke nomor pelanggan') }}</h2>
        <p class="muted">{{ _('Ketuk satu nama: WhatsApp terbuka ke nomor itu dengan kode sudah terisi. Tekan Kirim di WhatsApp.') }}</p>
        {% for c in result.contacts %}
          <a class="contact" href="{{ c.link }}">
            <span class="who"><b>{{ c.shop }}</b><span class="muted">{{ c.customer }} &middot; {{ c.phone }}</span></span>
            <span class="tag">{{ _('Sewa') if c.rental else _('Beli putus') }}</span>
          </a>
        {% endfor %}
      {% endif %}
      <a class="btn btn-secondary" href="{{ url_for('create_page') }}">{{ _('+ Buat Kode Baru') }}</a>
    {% else %}
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
      <form method="post" action="{{ url_for('generate') }}">
        <label>{{ _('Kode Perangkat (dari HP pembeli)') }}</label>
        <input type="text" name="device_code" autocapitalize="off" autocorrect="off" spellcheck="false" required>

        <label>{{ _('Nama Customer') }}</label>
        <input type="text" name="customer_name" required>

        <label>{{ _('Nama Toko/Kedai/Cafe') }}</label>
        <input type="text" name="shop_name" required>

        <label>{{ _('Alamat Toko') }}</label>
        <input type="text" name="address">

        <label>{{ _('No HP') }}</label>
        <input type="tel" name="phone" placeholder="{{ _('08xx atau 62xx') }}">

        <label>{{ _('Harga (Rp, boleh dikosongkan)') }}</label>
        <input type="text" name="price" inputmode="numeric" placeholder="{{ _('mis. 99000') }}">

        <label>{{ _('Jenis Lisensi') }}</label>
        <div class="radio-row">
          <label><input type="radio" name="license_choice" value="buy" checked> {{ _('Beli Putus') }}</label>
          <label><input type="radio" name="license_choice" value="weekly"> {{ _('Sewa Mingguan') }}</label>
          <label><input type="radio" name="license_choice" value="monthly"> {{ _('Sewa Bulanan') }}</label>
          <label><input type="radio" name="license_choice" value="yearly"> {{ _('Sewa Tahunan') }}</label>
        </div>

        <button type="submit">{{ _('Buat Kode Aktivasi') }}</button>
      </form>
    {% endif %}

    <a class="btn btn-secondary" href="{{ url_for('index') }}">{{ _('Kembali') }}</a>
  </div>
  <script>
    function copyText(id) {
      var text = document.getElementById(id).innerText;
      copyValue(text);
    }
    function copyValue(text) {
      if (navigator.clipboard) { navigator.clipboard.writeText(text).catch(function () {}); }
    }
  </script>
</body></html>
"""

_HISTORY_PAGE = """
<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oru Go License</title><style>{{ style }}</style></head><body>
  {{ navbar('/riwayat') }}
  <div class="card">
    <h1>{{ _('Riwayat (%(n)s terakhir)', n=records|length) }}</h1>
    {% if records %}
      <table>
        <tr><th>{{ _('Toko') }}</th><th>{{ _('Jenis') }}</th><th>{{ _('Tgl') }}</th><th></th></tr>
        {% for r in records %}
          <tr>
            <td>{{ r.shop_name }}<br><span class="badge">{{ r.customer_name }}</span></td>
            <td>{{ _(license_labels['buy'] if r.license_type == 'buy' else license_labels[r.rental_period]) }}
                {% if r.expiry_token != 'PERMANENT' %}<br><span class="badge">{{ _('s/d') }} {{ r.expiry_token[0:4] }}-{{ r.expiry_token[4:6] }}-{{ r.expiry_token[6:8] }}</span>{% endif %}
            </td>
            <td>{{ r.created_at[:10] }}</td>
            <td class="row-actions">
              <button type="button" onclick="copyValue({{ r.activation_code|tojson }})">{{ _('Salin') }}</button>
            </td>
          </tr>
        {% endfor %}
      </table>
      <a class="btn btn-secondary" href="{{ url_for('export_csv') }}">{{ _('Ekspor Riwayat (CSV)') }}</a>
    {% else %}
      <p style="color:#64748b; font-size:0.85rem;">{{ _('Belum ada riwayat.') }}</p>
    {% endif %}

    <a class="btn btn-secondary" href="{{ url_for('index') }}">{{ _('Kembali') }}</a>
  </div>
  <script>
    function copyValue(text) {
      if (navigator.clipboard) { navigator.clipboard.writeText(text).catch(function () {}); }
    }
  </script>
</body></html>
"""


def create_app(files_dir):
    global _DATA_DIR
    data_dir = os.path.join(files_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    _DATA_DIR = data_dir
    _init_db(data_dir)

    app = Flask(__name__)
    app.jinja_env.globals.update(_=tr, lang_switch=lang_switch, navbar=navbar)

    @app.context_processor
    def _inject_language():
        return {"lang": get_language()}

    secret_key_file = os.path.join(data_dir, "secret_key.txt")
    if os.path.exists(secret_key_file):
        with open(secret_key_file, "r") as f:
            app.secret_key = f.read().strip()
    else:
        app.secret_key = secrets.token_hex(32)
        with open(secret_key_file, "w") as f:
            f.write(app.secret_key)

    def _unlock_session():
        session["unlocked"] = True
        session["epoch"] = _lock_epoch
        session["last_seen"] = time.time()

    @app.before_request
    def _require_unlock():
        if request.endpoint in ("login", "biometric_unlock", "set_language", "static"):
            return None
        if not session.get("unlocked") or session.get("epoch") != _lock_epoch:
            session.clear()
            return redirect(url_for("login"))
        idle_minutes = load_security()["idle_lock_minutes"]
        now = time.time()
        if idle_minutes and now - session.get("last_seen", now) > idle_minutes * 60:
            session.clear()
            return redirect(url_for("login"))
        session["last_seen"] = now
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        settings = load_security()
        wait = login_wait_seconds()

        if request.method == "POST":
            if wait > 0:
                error = tr("Terlalu banyak percobaan salah. Coba lagi %(wait)s detik lagi.", wait=wait)
            elif verify_login(request.form.get("username", ""), request.form.get("password", ""),
                              settings["password_hash"]):
                _register_login_success()
                _unlock_session()
                return redirect(url_for("index"))
            else:
                _register_login_failure()
                wait = login_wait_seconds()
                error = tr("Username atau password salah.")
                if wait > 0:
                    error += tr(" Login ditahan %(wait)s detik.", wait=wait)
        elif wait > 0:
            error = tr("Login sedang ditahan %(wait)s detik karena terlalu banyak percobaan salah.", wait=wait)

        return render_template_string(
            _LOGIN_PAGE, style=_LOGIN_STYLE, error=error,
            bio_enabled=bool(settings["biometric_enabled"]),
        )

    @app.route("/biometric-unlock")
    def biometric_unlock():
        # Sidik jari diverifikasi di sisi Android NATIVE (BiometricPrompt di
        # MainActivity), lalu MainActivity MINTA token sekali-pakai ke
        # Python (issue_unlock_token) dan baru membuka URL ini membawa
        # token itu. Tanpa token yang sah, endpoint ini menolak - jadi
        # aplikasi lain di HP yang menjangkau 127.0.0.1 tidak bisa
        # melewati login.
        if _consume_unlock_token(request.args.get("token", "")):
            _unlock_session()
            return redirect(url_for("index"))
        return redirect(url_for("login"))

    @app.route("/set-language/<code>")
    def set_language(code):
        if code in LANGS:
            with _security_lock:
                settings = load_security()
                settings["language"] = code
                save_security(settings)
        target = request.args.get("next", "/")
        if target not in ("/", "/login", "/security", "/dasbor", "/pantau", "/buat", "/riwayat"):
            target = "/"
        return redirect(target)

    @app.route("/lock", methods=["POST"])
    def lock():
        session.clear()
        return redirect(url_for("login"))

    def _render_security(message=None, message_ok=False):
        return render_template_string(
            _SECURITY_PAGE, style=_BASE_STYLE, settings=load_security(), message=message,
            message_ok=message_ok, idle_choices=IDLE_CHOICES, min_length=MIN_PASSWORD_LENGTH,
            username=LOGIN_USERNAME, throttle_after=THROTTLE_AFTER,
            throttle_base=THROTTLE_BASE_SECONDS, throttle_max=THROTTLE_MAX_SECONDS,
        )

    @app.route("/security")
    def security_page():
        return _render_security()

    @app.route("/security/password", methods=["POST"])
    def security_password():
        wait = login_wait_seconds()
        if wait > 0:
            return _render_security(tr("Terlalu banyak percobaan salah. Coba lagi %(wait)s detik lagi.", wait=wait))

        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        settings = load_security()

        if not verify_login(LOGIN_USERNAME, old_password, settings["password_hash"]):
            _register_login_failure()
            return _render_security(tr("Password lama salah."))
        if len(new_password) < MIN_PASSWORD_LENGTH:
            return _render_security(tr("Password baru minimal %(n)s karakter.", n=MIN_PASSWORD_LENGTH))
        if new_password != confirm_password:
            return _render_security(tr("Password baru dan ulangannya tidak sama."))
        if new_password == old_password:
            return _render_security(tr("Password baru harus berbeda dari password lama."))

        with _security_lock:
            settings = load_security()
            settings["password_hash"] = hash_password(new_password)
            save_security(settings)
        _register_login_success()
        return _render_security(tr("Password berhasil diganti. Pakai password baru saat login berikutnya."), True)

    @app.route("/security/settings", methods=["POST"])
    def security_settings():
        try:
            idle_minutes = int(request.form.get("idle_lock_minutes", "0"))
        except ValueError:
            idle_minutes = 0
        if idle_minutes not in IDLE_CHOICES:
            idle_minutes = 0

        with _security_lock:
            settings = load_security()
            settings["biometric_enabled"] = request.form.get("biometric_enabled") == "1"
            settings["lock_on_leave"] = request.form.get("lock_on_leave") == "1"
            settings["idle_lock_minutes"] = idle_minutes
            save_security(settings)
        return _render_security(tr("Pengaturan kunci disimpan."), True)

    @app.route("/")
    def index():
        return render_template_string(
            _HOME_PAGE, style=_BASE_STYLE, d=_dashboard_data(data_dir), logo=_LOGO_URI,
            icons={name: _icon(name) for name in _ICONS}, has_records=bool(_list_records(data_dir, limit=1)),
        )

    @app.route("/buat")
    def create_page():
        return render_template_string(_CREATE_PAGE, style=_BASE_STYLE, result=None, error=None)

    @app.route("/riwayat")
    def history_page():
        return render_template_string(
            _HISTORY_PAGE, style=_BASE_STYLE, records=_list_records(data_dir), license_labels=LICENSE_LABELS,
        )

    @app.route("/dasbor")
    def dashboard():
        return render_template_string(
            _DASH_PAGE, style=_BASE_STYLE, d=_dashboard_data(data_dir),
        )

    @app.route("/pantau")
    def monitor_page():
        cfg = _load_monitor(data_dir)
        error = None
        view = None
        current_broadcast = None
        if cfg:
            devices, current_broadcast, problem = _fetch_devices(cfg)
            if problem == "token":
                error = tr("Token admin ditolak server. Putuskan sambungan lalu isi ulang tokennya.")
            elif problem:
                error = tr("Tidak bisa terhubung ke server Pantau (%(why)s). Periksa internet HP ini lalu muat ulang.", why=problem)
            view = _monitor_view(data_dir, devices)
        notice = session.pop("monitor_notice", None)
        return render_template_string(
            _MONITOR_PAGE, style=_BASE_STYLE, configured=bool(cfg), v=view, error=error,
            broadcast=current_broadcast if cfg else None, notice=notice,
            max_chars=BROADCAST_MAX_CHARS, day_choices=BROADCAST_DAYS,
        )

    @app.route("/pantau/simpan", methods=["POST"])
    def monitor_save():
        url = request.form.get("url", "").strip()
        token = request.form.get("token", "").strip()
        if not _valid_monitor_url(url) or not token:
            return render_template_string(
                _MONITOR_PAGE, style=_BASE_STYLE, configured=False, v=None,
                error=tr("Alamat harus diawali https:// dan token wajib diisi."),
            )
        _save_monitor(data_dir, url, token)
        return redirect(url_for("monitor_page"))

    @app.route("/pantau/siaran", methods=["POST"])
    def monitor_broadcast():
        cfg = _load_monitor(data_dir)
        if not cfg:
            return redirect(url_for("monitor_page"))
        text = request.form.get("text", "").strip()
        try:
            days = int(request.form.get("days", "7"))
        except ValueError:
            days = 7
        if days not in BROADCAST_DAYS or len(text) > BROADCAST_MAX_CHARS:
            session["monitor_notice"] = ("err", tr("Siaran tidak valid (maksimal %(n)s karakter).", n=BROADCAST_MAX_CHARS))
        elif _send_broadcast(cfg, text, days):
            session["monitor_notice"] = ("ok", tr("Siaran terkirim. Muncul di aplikasi pelanggan saat mereka berikutnya terhubung.") if text else tr("Siaran dihapus."))
        else:
            session["monitor_notice"] = ("err", tr("Gagal mengirim siaran. Periksa internet dan token."))
        return redirect(url_for("monitor_page"))

    @app.route("/pantau/putus", methods=["POST"])
    def monitor_clear():
        try:
            os.remove(_monitor_file(data_dir))
        except OSError:
            pass
        return redirect(url_for("monitor_page"))

    @app.route("/export.csv")
    def export_csv():
        filename = "riwayat-%s.csv" % date.today().strftime("%Y%m%d")
        return Response(
            _export_csv(data_dir),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="%s"' % filename},
        )

    @app.route("/generate", methods=["POST"])
    def generate():
        device_code = request.form.get("device_code", "").strip().upper()
        customer_name = request.form.get("customer_name", "").strip()
        shop_name = request.form.get("shop_name", "").strip()
        address = request.form.get("address", "").strip()
        phone = request.form.get("phone", "").strip()
        license_choice = request.form.get("license_choice", "buy")

        if not device_code or not customer_name or not shop_name:
            return render_template_string(
                _CREATE_PAGE, style=_BASE_STYLE, result=None,
                error=tr("Kode Perangkat, Nama Customer, dan Nama Toko wajib diisi."),
            )

        license_type = "buy" if license_choice == "buy" else "rent"
        rental_period = None if license_type == "buy" else license_choice

        expiry_token = compute_expiry_token(license_type, rental_period)
        activation_code = generate_activation_code(device_code, expiry_token)

        _save_record(data_dir, {
            "customer_name": customer_name, "shop_name": shop_name, "address": address,
            "phone": phone, "license_type": license_type, "rental_period": rental_period,
            "device_code": device_code, "expiry_token": expiry_token, "activation_code": activation_code,
            "price": _parse_price(request.form.get("price")),
        })

        wa_message = tr_plain(
            "Halo %(name)s, ini Kode Aktivasi Oru POS GO untuk %(shop)s:\n\n%(code)s\n\n"
            "Buka Oru POS GO, lalu tempel kode ini di kolom Kode Aktivasi.",
            name=customer_name, shop=shop_name, code=activation_code,
        )
        result = {
            "shop_name": shop_name,
            "license_label": tr(LICENSE_LABELS[license_choice]),
            "activation_code": activation_code,
            "wa_link": _whatsapp_link(phone, wa_message, allow_pick=True),
            "wa_pick": not any(ch.isdigit() for ch in phone),
            "contacts": _wa_contacts(data_dir, wa_message),
        }

        return render_template_string(_CREATE_PAGE, style=_BASE_STYLE, result=result, error=None)

    return app


def run(port, files_dir):
    app = create_app(files_dir)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
