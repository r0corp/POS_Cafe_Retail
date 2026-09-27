"""Skema aktivasi offline APK UMKM - 1 Kode Aktivasi cuma jalan di 1 HP,
tanpa server pusat mana pun buat ngecek pembelian (arsitektur produk
ini memang harus fully offline - lihat android-app-umkm/README kalau
ada, atau tanya user).

Alur:
  1. HP belum aktivasi -> semua halaman dialihkan ke "/__activation",
     nampilin "Kode Perangkat" (diturunkan dari ANDROID_ID).
  2. Pembeli kirim Kode Perangkat itu ke penjual (WA/dst).
  3. Penjual jalankan licensing_tool/generate_activation_code.py di
     laptop sendiri (private key TIDAK PERNAH ikut ke APK ini) buat
     bikin "Kode Aktivasi", dikirim balik ke pembeli.
  4. Pembeli tempel Kode Aktivasi -> diverifikasi pakai PUBLIC key di
     bawah -> kalau cocok, tersimpan permanen di
     data_dir/activation.json dan APK langsung bisa dipakai seterusnya
     (termasuk offline, tidak perlu internet lagi sama sekali).

Kenapa aman walau APK ini di-unzip & source-nya dibaca semua orang:
yang ditanam di sini CUMA public key (PUBLIC_KEY_N/E) - itu memang
tidak rahasia. Signature RSA cuma bisa dibuat pakai private key yang
cuma disimpan di laptop penjual (licensing_tool/private_key.json,
sengaja TIDAK ikut di folder ini/APK ini sama sekali), jadi orang yang
bongkar APK paling jauh cuma bisa baca CARA verifikasinya, tidak bisa
bikin Kode Aktivasi baru buat HP lain.

_SIGN_SALT di bawah HARUS PERSIS SAMA dengan yang di
licensing_tool/generate_activation_code.py - itu 2 salinan yang sengaja
dipisah (skrip generate tidak pernah ikut ke dalam APK), jangan diubah
salah satu doang.
"""

import base64
import hashlib
import json
import os

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


def _hash_to_int(device_id):
    digest = hashlib.sha256(_SIGN_SALT + device_id.encode()).digest()
    return int.from_bytes(digest, "big")


def verify_activation_code(device_id, code):
    if PUBLIC_KEY_N == 0:
        return False
    try:
        signature_int = int.from_bytes(_b32decode(code), "big")
    except Exception:
        return False

    expected = _hash_to_int(device_id) % PUBLIC_KEY_N
    actual = pow(signature_int, PUBLIC_KEY_E, PUBLIC_KEY_N)
    return actual == expected


def _activation_file(data_dir):
    return os.path.join(data_dir, "activation.json")


def is_activated(data_dir):
    if _activation_ok_cache["ok"]:
        return True

    path = _activation_file(data_dir)
    if not os.path.exists(path):
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return False

    # Selalu hitung ulang device_id SAAT INI, jangan percaya begitu
    # saja field di file - kalau activation.json ini disalin ke HP
    # lain, device_id-nya pasti beda dan verifikasi di bawah otomatis
    # gagal (mencegah 1 aktivasi dipakai di banyak HP dengan cara
    # nyalin file data).
    device_id = get_device_id()
    ok = record.get("device_id") == device_id and verify_activation_code(device_id, record.get("code", ""))
    if ok:
        _activation_ok_cache["ok"] = True
    return ok


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
  form { margin-top: 22px; }
</style>
</head>
<body>
  <div class="card">
    <h1>Aktivasi Aplikasi</h1>
    <p>Kirim <b>Kode Perangkat</b> di bawah ini ke penjual, lalu tempel <b>Kode Aktivasi</b> yang dikirim balik.</p>

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
            if verify_activation_code(device_id, code):
                _save_activation(data_dir, device_id, code)
                _activation_ok_cache["ok"] = True
                return redirect("/")
            error = "Kode Aktivasi salah atau bukan untuk perangkat ini."

        return render_template_string(_ACTIVATION_PAGE, device_id=device_id, error=error)
