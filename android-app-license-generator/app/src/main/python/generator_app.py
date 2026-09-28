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
import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import date, timedelta

from flask import Flask, g, redirect, render_template_string, request, session, url_for

from private_key import PRIVATE_KEY_D, PRIVATE_KEY_N
from rsa_math import sign

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


def verify_login(username, password):
    if not hmac.compare_digest(username, LOGIN_USERNAME):
        return False
    try:
        salt_hex, key_hex = LOGIN_PASSWORD_HASH.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
    except ValueError:
        return False
    actual = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return hmac.compare_digest(actual, expected)


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
    conn.commit()
    conn.close()


def _save_record(data_dir, fields):
    conn = sqlite3.connect(_db_path(data_dir))
    conn.execute(
        """INSERT INTO customers
           (customer_name, shop_name, address, phone, license_type, rental_period,
            device_code, expiry_token, activation_code, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))""",
        (
            fields["customer_name"], fields["shop_name"], fields["address"], fields["phone"],
            fields["license_type"], fields["rental_period"], fields["device_code"],
            fields["expiry_token"], fields["activation_code"],
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


def _whatsapp_link(phone, message):
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    from urllib.parse import quote
    return f"https://wa.me/{digits}?text={quote(message)}"


# ============================================================
# Halaman (semua inline - app kecil, tidak perlu folder templates/)
# ============================================================

_BASE_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0;
         margin: 0; padding: 20px 16px 40px; min-height: 100vh; }
  .card { max-width: 520px; margin: 24px auto; background: #1e293b; border-radius: 16px; padding: 24px; }
  h1 { font-size: 1.25rem; margin: 0 0 16px; }
  h2 { font-size: 1rem; margin: 24px 0 10px; color: #94a3b8; }
  label { display: block; font-size: 0.85rem; color: #cbd5e1; margin: 12px 0 6px; font-weight: 600; }
  input[type=text], input[type=password], input[type=tel], select {
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

_LOGIN_PAGE = """
<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Masuk</title><style>{{ style }}</style></head><body>
  <div class="card">
    <h1>Generator Lisensi</h1>
    <p style="color:#94a3b8; font-size:0.85rem;">App ini bisa bikin Kode Aktivasi buat HP mana pun - login dulu supaya kalau HP ini hilang, tidak sembarang orang bisa langsung pakai.</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="post">
      <label>Username</label>
      <input type="text" name="username" autocapitalize="off" autocorrect="off" spellcheck="false" autofocus required>
      <label>Password</label>
      <input type="password" name="password" required>
      <button type="submit">Masuk</button>
    </form>
    <button type="button" id="bioBtn" class="btn-secondary" style="display:none;" onclick="AndroidAuth.authenticate()">Masuk pakai Sidik Jari</button>
  </div>
  <script>
    if (window.AndroidAuth && AndroidAuth.isBiometricAvailable && AndroidAuth.isBiometricAvailable()) {
      document.getElementById('bioBtn').style.display = 'block';
    }
  </script>
</body></html>
"""

_MAIN_PAGE = """
<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Generator Lisensi</title><style>{{ style }}</style></head><body>
  <div class="card">
    <h1>Generator Kode Aktivasi</h1>

    {% if result %}
      <div class="error" style="background:#14532d; color:#bbf7d0;">
        Kode buat <b>{{ result.shop_name }}</b> ({{ result.license_label }}) berhasil dibuat.
      </div>
      <label>Kode Aktivasi</label>
      <div class="result-code" id="resultCode">{{ result.activation_code }}</div>
      <button type="button" onclick="copyText('resultCode')">Salin Kode Aktivasi</button>
      {% if result.wa_link %}
        <a class="btn btn-secondary" href="{{ result.wa_link }}" target="_blank">Kirim lewat WhatsApp</a>
      {% endif %}
      <a class="btn btn-secondary" href="{{ url_for('index') }}">+ Buat Kode Baru</a>
    {% else %}
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
      <form method="post" action="{{ url_for('generate') }}">
        <label>Kode Perangkat (dari HP pembeli)</label>
        <input type="text" name="device_code" autocapitalize="off" autocorrect="off" spellcheck="false" required>

        <label>Nama Customer</label>
        <input type="text" name="customer_name" required>

        <label>Nama Toko/Kedai/Cafe</label>
        <input type="text" name="shop_name" required>

        <label>Alamat Toko</label>
        <input type="text" name="address">

        <label>No HP</label>
        <input type="tel" name="phone" placeholder="08xx atau 62xx">

        <label>Jenis Lisensi</label>
        <div class="radio-row">
          <label><input type="radio" name="license_choice" value="buy" checked> Beli Putus</label>
          <label><input type="radio" name="license_choice" value="weekly"> Sewa Mingguan</label>
          <label><input type="radio" name="license_choice" value="monthly"> Sewa Bulanan</label>
          <label><input type="radio" name="license_choice" value="yearly"> Sewa Tahunan</label>
        </div>

        <button type="submit">Generate Kode Aktivasi</button>
      </form>
    {% endif %}

    <h2>Riwayat ({{ records|length }} terakhir)</h2>
    {% if records %}
      <table>
        <tr><th>Toko</th><th>Jenis</th><th>Tgl</th><th></th></tr>
        {% for r in records %}
          <tr>
            <td>{{ r.shop_name }}<br><span class="badge">{{ r.customer_name }}</span></td>
            <td>{{ license_labels['buy'] if r.license_type == 'buy' else license_labels[r.rental_period] }}
                {% if r.expiry_token != 'PERMANENT' %}<br><span class="badge">s/d {{ r.expiry_token[0:4] }}-{{ r.expiry_token[4:6] }}-{{ r.expiry_token[6:8] }}</span>{% endif %}
            </td>
            <td>{{ r.created_at[:10] }}</td>
            <td class="row-actions">
              <button type="button" onclick="copyValue({{ r.activation_code|tojson }})">Salin</button>
            </td>
          </tr>
        {% endfor %}
      </table>
    {% else %}
      <p style="color:#64748b; font-size:0.85rem;">Belum ada riwayat.</p>
    {% endif %}

    <form method="post" action="{{ url_for('lock') }}"><button type="submit" class="btn-secondary">Kunci App</button></form>
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


def run(port, files_dir):
    data_dir = os.path.join(files_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    _init_db(data_dir)

    app = Flask(__name__)

    secret_key_file = os.path.join(data_dir, "secret_key.txt")
    if os.path.exists(secret_key_file):
        with open(secret_key_file, "r") as f:
            app.secret_key = f.read().strip()
    else:
        app.secret_key = secrets.token_hex(32)
        with open(secret_key_file, "w") as f:
            f.write(app.secret_key)

    @app.before_request
    def _require_unlock():
        if request.endpoint in ("login", "biometric_unlock", "static"):
            return None
        if not session.get("unlocked"):
            return redirect(url_for("login"))
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            if verify_login(request.form.get("username", ""), request.form.get("password", "")):
                session["unlocked"] = True
                return redirect(url_for("index"))
            error = "Username atau password salah."

        return render_template_string(_LOGIN_PAGE, style=_BASE_STYLE, error=error)

    @app.route("/biometric-unlock")
    def biometric_unlock():
        # Sidik jari diverifikasi di sisi Android NATIVE (lihat
        # MainActivity.AuthBridge/BiometricPrompt) SEBELUM WebView
        # diarahkan ke sini - endpoint ini sendiri cuma penanda "sudah
        # lolos" ke sesi Flask, tidak mengecek apa-apa lagi. Aman karena
        # cuma bisa diakses dari 127.0.0.1 (HP itu sendiri), bukan dari
        # jaringan luar.
        session["unlocked"] = True
        return redirect(url_for("index"))

    @app.route("/lock", methods=["POST"])
    def lock():
        session.pop("unlocked", None)
        return redirect(url_for("login"))

    @app.route("/")
    def index():
        return render_template_string(
            _MAIN_PAGE, style=_BASE_STYLE, result=None, error=None,
            records=_list_records(data_dir), license_labels=LICENSE_LABELS,
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
                _MAIN_PAGE, style=_BASE_STYLE, result=None,
                error="Kode Perangkat, Nama Customer, dan Nama Toko wajib diisi.",
                records=_list_records(data_dir), license_labels=LICENSE_LABELS,
            )

        license_type = "buy" if license_choice == "buy" else "rent"
        rental_period = None if license_type == "buy" else license_choice

        expiry_token = compute_expiry_token(license_type, rental_period)
        activation_code = generate_activation_code(device_code, expiry_token)

        _save_record(data_dir, {
            "customer_name": customer_name, "shop_name": shop_name, "address": address,
            "phone": phone, "license_type": license_type, "rental_period": rental_period,
            "device_code": device_code, "expiry_token": expiry_token, "activation_code": activation_code,
        })

        wa_message = f"Halo {customer_name}, ini Kode Aktivasi APK UMKM untuk {shop_name}:\n\n{activation_code}\n\nTempel ke kolom Kode Aktivasi di aplikasi."
        result = {
            "shop_name": shop_name,
            "license_label": LICENSE_LABELS[license_choice],
            "activation_code": activation_code,
            "wa_link": _whatsapp_link(phone, wa_message),
        }

        return render_template_string(
            _MAIN_PAGE, style=_BASE_STYLE, result=result, error=None,
            records=_list_records(data_dir), license_labels=LICENSE_LABELS,
        )

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
