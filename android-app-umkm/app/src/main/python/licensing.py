"""Skema aktivasi offline APK UMKM - 1 Kode Aktivasi cuma jalan di 1 HP,
tanpa server pusat mana pun buat ngecek pembelian (arsitektur produk
ini memang harus fully offline - lihat android-app-umkm/README kalau
ada, atau tanya user).

Alur:
  1. HP belum aktivasi -> semua halaman dialihkan ke "/__activation",
     nampilin "Kode Perangkat" (diturunkan dari ANDROID_ID).
  2. Pembeli kirim Kode Perangkat itu ke penjual (WA/dst).
  3. Penjual generate "Kode Aktivasi" - baik lewat
     licensing_tool/generate_activation_code.py di laptop, ATAU lewat
     APK Generator Lisensi terpisah (private key TIDAK PERNAH ikut ke
     APK UMKM ini) - dikirim balik ke pembeli.
  4. Pembeli tempel Kode Aktivasi -> diverifikasi pakai PUBLIC key di
     bawah -> kalau cocok, tersimpan permanen di
     data_dir/activation.json dan APK langsung bisa dipakai seterusnya
     (termasuk offline, tidak perlu internet lagi sama sekali).

Kenapa aman walau APK ini di-unzip & source-nya dibaca semua orang:
yang ditanam di sini CUMA public key (PUBLIC_KEY_N/E) - itu memang
tidak rahasia. Signature RSA cuma bisa dibuat pakai private key yang
cuma disimpan di perangkat penjual (licensing_tool/private_key.json /
APK Generator Lisensi, sengaja TIDAK ikut di folder ini/APK ini sama
sekali), jadi orang yang bongkar APK paling jauh cuma bisa baca CARA
verifikasinya, tidak bisa bikin Kode Aktivasi baru buat HP lain.

Format kode ada 2, supaya kode yang sudah terlanjur dikirim ke pembeli
SEBELUM fitur sewa/kedaluwarsa ini ada tetap sah (tidak perlu aktivasi
ulang):
  - Lama (tanpa titik): signature murni atas device_id saja -> selalu
    dianggap PERMANENT (beli putus).
  - Baru: "<expiry_token>.<signature>" - expiry_token "PERMANENT" (beli
    putus) atau tanggal "YYYYMMDD" (sewa, kedaluwarsa tanggal itu).

_SIGN_SALT di bawah HARUS PERSIS SAMA dengan yang dipakai buat generate
kode (generate_activation_code.py / APK Generator Lisensi) - itu
salinan-salinan terpisah (skrip/app generate tidak pernah ikut ke
dalam APK ini), jangan diubah salah satu doang.
"""

import base64
import hashlib
import json
import os
from datetime import date

from flask import redirect, render_template_string, request

# ============================================================
# PUBLIC KEY - hasil dari licensing_tool/generate_keypair.py.
# Ini BUKAN rahasia, aman ditaruh di sini / di git.
# ============================================================
# Digenerate lewat android-app-umkm/licensing_tool/generate_keypair.py
# (2026-09-27) - kalau perlu ganti kunci total, jalankan lagi lalu
# tempel nilai baru di sini (kode aktivasi yang sudah dikirim ke
# pembeli lama otomatis tidak valid lagi setelah diganti).
PUBLIC_KEY_N = 14035061336674848131669469889930453435334821366163409335798876667676928902309041117165803211519832896841349923047206814470911024762265590445206418057588976021572946051655229599654468377388776575786720933766026024999358023606652761321822314691877596123970768918118227308316624185419058603616547658586269511612103919070982022026767658252454277106507230792483649881996611043697675541429192492077215553086234767781914142949021433228679500557027927369205410082491116739735814490235991660074279453315686480753289173167930784136104468078248418898271081445480362001839200923377201954259629589299003710178723773169476845270961
PUBLIC_KEY_E = 65537

_DEVICE_ID_SALT = b"orulabs-apk-umkm-device-id-v1"
_SIGN_SALT = b"orulabs-apk-umkm-activation-v1"

_device_id_cache = {}
_activation_ok_cache = {"ok": False}


def _b32encode(data):
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _b32decode(text):
    text = text.strip().upper().replace("-", "").replace(" ", "")
    padding = "=" * ((8 - len(text) % 8) % 8)
    return base64.b32decode(text + padding)


def get_device_id():
    """ID unik per HP, diturunkan dari ANDROID_ID (bukan dipakai
    mentah - di-hash+garam supaya tidak gampang ditebak/dipalsukan
    perangkat lain)."""

    if "id" in _device_id_cache:
        return _device_id_cache["id"]

    from com.chaquo.python import Python
    from android.provider import Settings

    context = Python.getPlatform().getApplication()
    android_id = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID)

    digest = hashlib.sha256(_DEVICE_ID_SALT + android_id.encode()).digest()[:10]
    device_id = _b32encode(digest)
    _device_id_cache["id"] = device_id
    return device_id


def _hash_to_int_legacy(device_id):
    """Format kode LAMA (sebelum ada sewa/kedaluwarsa) - cuma device_id,
    tidak ada expiry_token sama sekali. Jangan diubah - kode yang sudah
    beredar pakai persamaan ini persis."""
    digest = hashlib.sha256(_SIGN_SALT + device_id.encode()).digest()
    return int.from_bytes(digest, "big")


def _hash_to_int(device_id, expiry_token):
    digest = hashlib.sha256(_SIGN_SALT + device_id.encode() + b"|" + expiry_token.encode()).digest()
    return int.from_bytes(digest, "big")


def _verify_signature(message_int, signature_int):
    return pow(signature_int, PUBLIC_KEY_E, PUBLIC_KEY_N) == message_int % PUBLIC_KEY_N


def _is_expired(expiry_token):
    try:
        year, month, day = int(expiry_token[0:4]), int(expiry_token[4:6]), int(expiry_token[6:8])
        return date.today() > date(year, month, day)
    except (ValueError, IndexError):
        return True  # Format tanggal aneh - anggap kedaluwarsa, lebih aman daripada salah loloskan.


def verify_activation_code(device_id, code):
    """Return "PERMANENT" atau expiry_token "YYYYMMDD" kalau signature-nya
    valid, None kalau tidak valid sama sekali (tidak cek kedaluwarsa di
    sini - itu tanggung jawab pemanggil, supaya kode yang signature-nya
    sah tapi sudah lewat tanggal tetap bisa dibedakan dari kode yang
    memang dipalsukan/salah ketik)."""

    if PUBLIC_KEY_N == 0:
        return None

    code = code.strip()

    if "." in code:
        expiry_token, _, sig_part = code.partition(".")
        expiry_token = expiry_token.strip().upper()
        try:
            signature_int = int.from_bytes(_b32decode(sig_part), "big")
        except Exception:
            signature_int = None
        if signature_int is not None and _verify_signature(_hash_to_int(device_id, expiry_token), signature_int):
            return expiry_token

    # Format lama (tanpa titik) - lihat _hash_to_int_legacy().
    try:
        signature_int = int.from_bytes(_b32decode(code), "big")
    except Exception:
        return None
    if _verify_signature(_hash_to_int_legacy(device_id), signature_int):
        return "PERMANENT"
    return None


def _activation_file(data_dir):
    return os.path.join(data_dir, "activation.json")


def _read_activation_record(data_dir, device_id):
    """None kalau tidak ada file/rusak/device_id tidak cocok (disalin
    dari HP lain). Kalau ada, return expiry_token hasil verify_activation_code
    (bisa None kalau signature-nya sendiri tidak valid/dipalsukan)."""

    path = _activation_file(data_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    if record.get("device_id") != device_id:
        return None
    return verify_activation_code(device_id, record.get("code", ""))


def is_activated(data_dir):
    if _activation_ok_cache["ok"]:
        return True

    device_id = get_device_id()
    expiry_token = _read_activation_record(data_dir, device_id)
    if expiry_token is None:
        return False
    if expiry_token != "PERMANENT" and _is_expired(expiry_token):
        return False

    # Kode PERMANENT tidak mungkin berubah jadi tidak sah lagi selama
    # proses ini hidup, aman di-cache selamanya (hemat baca file/verify
    # RSA tiap request). Kode sewa SENGAJA tidak di-cache - supaya
    # begitu tanggalnya lewat, request berikutnya langsung ke-detect
    # tanpa perlu tutup-buka app dulu.
    if expiry_token == "PERMANENT":
        _activation_ok_cache["ok"] = True
    return True


def get_expired_notice(data_dir):
    """Kalau HP ini PERNAH aktivasi sah lewat kode SEWA tapi tanggalnya
    sudah lewat, return tanggal kedaluwarsanya (buat pesan yang beda di
    halaman aktivasi - bukan seolah belum pernah aktivasi sama sekali).
    None kalau tidak relevan (belum pernah aktivasi / masih PERMANENT /
    masih berlaku)."""

    device_id = get_device_id()
    expiry_token = _read_activation_record(data_dir, device_id)
    if expiry_token and expiry_token != "PERMANENT" and _is_expired(expiry_token):
        return f"{expiry_token[0:4]}-{expiry_token[4:6]}-{expiry_token[6:8]}"
    return None


def _save_activation(data_dir, device_id, code):
    with open(_activation_file(data_dir), "w", encoding="utf-8") as f:
        json.dump({"device_id": device_id, "code": code}, f)


_ACTIVATION_PAGE = """
<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aktivasi Aplikasi</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0;
         margin: 0; padding: 24px 16px; min-height: 100vh; }
  .card { max-width: 420px; margin: 32px auto; background: #1e293b; border-radius: 16px; padding: 24px; }
  h1 { font-size: 1.2rem; margin: 0 0 10px; }
  p { color: #94a3b8; font-size: 0.9rem; line-height: 1.55; margin: 0 0 6px; }
  label { display: block; font-size: 0.85rem; color: #cbd5e1; margin-bottom: 6px; font-weight: 600; }
  .device-id { background: #0f172a; border: 1px solid #334155; border-radius: 10px; padding: 12px;
               font-family: monospace; font-size: 1.05rem; letter-spacing: 1px; word-break: break-all; margin: 10px 0 12px; }
  button { background: #f97316; color: #fff; border: none; border-radius: 10px; padding: 12px 16px;
           font-weight: 600; font-size: 0.95rem; width: 100%; }
  .copy-btn { background: #334155; margin-bottom: 20px; }
  input[type=text] { width: 100%; background: #0f172a; border: 1px solid #334155; color: #e2e8f0;
                      border-radius: 10px; padding: 12px; margin: 0 0 16px; font-family: monospace; font-size: 0.95rem; }
  .error { background: #7f1d1d; color: #fecaca; border-radius: 10px; padding: 10px 14px; margin-bottom: 16px; font-size: 0.85rem; }
  .notice { background: #78350f; color: #fed7aa; border-radius: 10px; padding: 10px 14px; margin-bottom: 16px; font-size: 0.85rem; }
  form { margin-top: 22px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Aktivasi Aplikasi</h1>
    {% if expired_notice %}
      <p>Masa aktif aplikasi ini sudah berakhir tanggal <b>{{ expired_notice }}</b>. Hubungi penjual untuk perpanjang, lalu tempel Kode Aktivasi baru di bawah.</p>
    {% else %}
      <p>Kirim <b>Kode Perangkat</b> di bawah ini ke penjual, lalu tempel <b>Kode Aktivasi</b> yang dikirim balik.</p>
    {% endif %}

    <label>Kode Perangkat</label>
    <div class="device-id" id="deviceId">{{ device_id }}</div>
    <button type="button" class="copy-btn" onclick="copyId()">Salin Kode Perangkat</button>

    {% if error %}<div class="error">{{ error }}</div>{% endif %}

    <form method="post">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <label>Kode Aktivasi</label>
      <input type="text" name="code" autocapitalize="off" autocorrect="off" spellcheck="false" required
             placeholder="Tempel Kode Aktivasi di sini">
      <button type="submit">Aktifkan</button>
    </form>
  </div>
  <script>
    function copyId() {
      var text = document.getElementById('deviceId').innerText;
      if (navigator.clipboard) { navigator.clipboard.writeText(text).catch(function () {}); }
    }
  </script>
</body>
</html>
"""


def install_activation_gate(app, data_dir):
    """Pasang pengecekan aktivasi SEBELUM request apa pun masuk ke
    aplikasi POS yang sesungguhnya - dipanggil sekali dari
    umkm_app.run() sesudah create_app(), sebelum app.run()."""

    @app.before_request
    def _check_activation():
        if request.path.startswith("/__activation"):
            return None
        if is_activated(data_dir):
            return None
        return redirect("/__activation")

    @app.route("/__activation", methods=["GET", "POST"])
    def _activation_view():
        device_id = get_device_id()
        error = None

        if request.method == "POST":
            code = request.form.get("code", "").strip()
            expiry_token = verify_activation_code(device_id, code)
            if expiry_token is not None and (expiry_token == "PERMANENT" or not _is_expired(expiry_token)):
                _save_activation(data_dir, device_id, code)
                if expiry_token == "PERMANENT":
                    _activation_ok_cache["ok"] = True
                return redirect("/")
            elif expiry_token is not None:
                error = "Kode ini sudah kedaluwarsa - minta Kode Aktivasi baru ke penjual."
            else:
                error = "Kode Aktivasi salah atau bukan untuk perangkat ini."

        return render_template_string(
            _ACTIVATION_PAGE, device_id=device_id, error=error, expired_notice=get_expired_notice(data_dir)
        )
