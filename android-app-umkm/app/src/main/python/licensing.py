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
    if expiry_token is not None:
        if expiry_token != "PERMANENT" and _is_expired(expiry_token):
            # Kode SEWA yang sudah kedaluwarsa - HP ini sudah PERNAH
            # aktivasi (bukan HP baru), jadi TIDAK jatuh balik ke masa
            # percobaan, langsung diblokir.
            return False

        # Kode PERMANENT tidak mungkin berubah jadi tidak sah lagi selama
        # proses ini hidup, aman di-cache selamanya (hemat baca file/verify
        # RSA tiap request). Kode sewa SENGAJA tidak di-cache - supaya
        # begitu tanggalnya lewat, request berikutnya langsung ke-detect
        # tanpa perlu tutup-buka app dulu.
        if expiry_token == "PERMANENT":
            _activation_ok_cache["ok"] = True
        return True

    # Belum pernah aktivasi kode apa pun (device baru) - kasih masa
    # percobaan gratis, lihat get_trial_info().
    trial = get_trial_info(data_dir)
    return not trial["expired"]


_TRIAL_DAYS = 7


def _trial_file(data_dir):
    return os.path.join(data_dir, "trial_start.json")


def _get_trial_start(data_dir):
    """Tanggal HP ini PERTAMA KALI buka aplikasi - disimpan sekali,
    dipakai buat hitung mundur 7 hari masa percobaan."""
    path = _trial_file(data_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            return date.fromisoformat(record["start"])
        except (OSError, ValueError, KeyError):
            pass  # File rusak - anggap belum pernah, buat baru di bawah.

    today = date.today()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"start": today.isoformat()}, f)
    return today


def get_trial_info(data_dir):
    """None kalau HP ini sudah PERNAH ada kode aktivasi (sah ataupun
    sudah kedaluwarsa - bukan device baru, tidak relevan lagi soal
    trial). Kalau belum pernah sama sekali, return dict:
      day_number - hari ke berapa sejak pertama buka (1, 2, 3, ...)
      days_left  - sisa hari trial (0 kalau sudah habis)
      expired    - True kalau 7 hari sudah lewat
    """
    device_id = get_device_id()
    if _read_activation_record(data_dir, device_id) is not None:
        return None

    start = _get_trial_start(data_dir)
    elapsed = (date.today() - start).days
    return {
        "day_number": elapsed + 1,
        "days_left": max(0, _TRIAL_DAYS - elapsed),
        "expired": elapsed >= _TRIAL_DAYS,
    }


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
  body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0;
         margin: 0; padding: 0; min-height: 100vh; }
  .login-page-wrap { display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: 100vh; padding: 32px 16px; }
  .login-card { max-width: 360px; width: 100%; background: #1e293b; border-radius: 28px;
    box-shadow: 0 10px 28px rgba(0,0,0,0.45); padding: 32px 26px 26px; text-align: center; }
  .login-logo-wrap { position: relative; width: 74px; height: 74px; margin: 0 auto 16px; }
  .login-logo-circle { width: 74px; height: 74px; border-radius: 50%; background: #0f172a;
    display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
  .login-logo-circle svg { width: 34px; height: 34px; }
  .login-dot { position: absolute; border-radius: 50%; }
  .login-dot-1 { width: 14px; height: 14px; background: #f97316; top: -5px; right: -5px; }
  .login-dot-2 { width: 9px; height: 9px; background: #38bdf8; bottom: 5px; left: -10px; }
  .login-dot-3 { width: 6px; height: 6px; background: #f97316; bottom: -5px; right: 14px; opacity: 0.55; }
  .login-title { font-weight: 700; font-size: 1.15rem; color: #e2e8f0; margin: 0 0 3px; }
  .login-subtitle { color: #94a3b8; font-size: 0.8rem; margin: 0 0 20px; }
  .login-notice { background: #0f172a; border: 1px solid #334155; color: #94a3b8; border-radius: 12px;
    padding: 10px 14px; font-size: 0.78rem; line-height: 1.5; text-align: left; margin-bottom: 18px; }
  .login-notice-warn { background: #78350f; border-color: #92400e; color: #fed7aa; }
  .login-notice b { color: inherit; }
  .login-label { display: block; text-align: left; font-size: 0.78rem; color: #cbd5e1; font-weight: 600; margin-bottom: 6px; }
  .login-code-box { background: #0f172a; border: 1px solid #334155; border-radius: 14px; padding: 12px;
    font-family: monospace; font-size: 1rem; letter-spacing: 1px; word-break: break-all; margin-bottom: 10px; text-align: left; }
  .login-error { background: #7f1d1d; color: #fecaca; border-radius: 10px; padding: 10px 14px;
    margin-bottom: 14px; font-size: 0.8rem; text-align: left; }
  .login-form { text-align: left; margin-top: 18px; }
  .login-field { margin-bottom: 12px; }
  .login-input { width: 100%; border: none; background: #0f172a; border-radius: 999px;
    padding: 12px 16px; font-size: 0.9rem; color: #e2e8f0; font-family: monospace; }
  .login-input:focus { outline: none; box-shadow: 0 0 0 3px rgba(240,120,40,0.25); }
  .login-input::placeholder { color: #64748b; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .login-submit-btn { width: 100%; border: none; background: #f97316; color: #fff; font-weight: 700;
    letter-spacing: 0.5px; text-transform: uppercase; font-size: 0.8rem; padding: 13px; border-radius: 999px;
    margin-top: 6px; box-shadow: 0 10px 22px rgba(240,120,40,0.35); display: flex; align-items: center;
    justify-content: center; gap: 8px; }
  .login-bio-btn { width: 100%; border: none; background: #334155; color: #e2e8f0; font-weight: 600;
    font-size: 0.85rem; padding: 12px; border-radius: 999px; margin-top: 12px; }
  .login-credit { margin-top: 18px; text-align: center; font-size: 0.78rem; color: #64748b; }
</style>
</head>
<body>
<div class="login-page-wrap">
  <div class="login-card">
    <div class="login-logo-wrap">
      <span class="login-dot login-dot-1"></span>
      <span class="login-dot login-dot-2"></span>
      <span class="login-dot login-dot-3"></span>
      <div class="login-logo-circle">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 8h13v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8z" fill="#f97316"/>
          <path d="M17 9.5h1.2a2.3 2.3 0 0 1 0 4.6H17" stroke="#f97316" stroke-width="1.6" fill="none"/>
          <path d="M7 3.2c0 .9-.9.9-.9 1.8M11 3.2c0 .9-.9.9-.9 1.8M15 3.2c0 .9-.9.9-.9 1.8" stroke="#f97316" stroke-width="1.3" stroke-linecap="round" fill="none"/>
        </svg>
      </div>
    </div>
    <h3 class="login-title">Oru POS GO</h3>
    <p class="login-subtitle">
      {% if trial_expired %}Masa percobaan sudah berakhir{% elif expired_notice %}Masa aktif sudah berakhir{% else %}Aktivasi diperlukan untuk melanjutkan{% endif %}
    </p>

    <div class="login-notice {{ 'login-notice-warn' if (expired_notice or trial_expired) else '' }}">
      {% if expired_notice %}
        Masa aktif aplikasi ini sudah berakhir tanggal <b>{{ expired_notice }}</b>. Hubungi penjual untuk perpanjang, lalu tempel Kode Aktivasi baru di bawah.
      {% elif trial_expired %}
        Masa percobaan 7 hari sudah berakhir. Hubungi penjual untuk berlangganan/beli, lalu tempel <b>Kode Aktivasi</b> yang dikirim ke perangkat ini.
      {% else %}
        Kirim <b>Kode Perangkat</b> di bawah ini ke penjual, lalu tempel <b>Kode Aktivasi</b> yang dikirim balik.
      {% endif %}
    </div>

    <label class="login-label">Kode Perangkat</label>
    <div class="login-code-box" id="deviceId">{{ device_id }}</div>
    <button type="button" class="login-bio-btn" onclick="copyId()">Salin Kode Perangkat</button>

    {% if error %}<div class="login-error" style="margin-top:16px;">{{ error }}</div>{% endif %}

    <form method="post" class="login-form">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="login-field">
        <input type="text" name="code" class="login-input" autocapitalize="off" autocorrect="off" spellcheck="false" required
               placeholder="Tempel Kode Aktivasi di sini">
      </div>
      <button type="submit" class="login-submit-btn">
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
        Aktifkan
      </button>
    </form>
  </div>
  <p class="login-credit">Orulabs &copy; 2026. All rights reserved.</p>
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


_TRIAL_MODAL_TEMPLATE = """
<div id="__trialModalOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.55);
     z-index:99998;align-items:center;justify-content:center;padding:20px;">
  <div style="max-width:320px;width:100%;background:#1e293b;border-radius:20px;padding:24px 20px 20px;
       text-align:center;box-shadow:0 10px 28px rgba(0,0,0,0.5);
       font-family:system-ui,-apple-system,'Segoe UI',sans-serif;">
    <div style="width:52px;height:52px;border-radius:50%;background:#0f172a;display:flex;
         align-items:center;justify-content:center;margin:0 auto 12px;">
      <span style="font-size:1.5rem;">&#9203;</span>
    </div>
    <h3 style="color:#e2e8f0;margin:0 0 6px;font-size:1.05rem;">Masa Percobaan - Hari ke-__DAY__</h3>
    <p style="color:#94a3b8;font-size:0.85rem;line-height:1.5;margin:0 0 18px;">
      __DAYS_LEFT_TEXT__<br>Hubungi penjual untuk berlangganan supaya aplikasi ini terus bisa dipakai.
    </p>
    <button onclick="document.getElementById('__trialModalOverlay').style.display='none';"
      style="width:100%;border:none;background:#f97316;color:#fff;font-weight:700;font-size:0.85rem;
      padding:12px;border-radius:999px;box-shadow:0 8px 18px rgba(240,120,40,0.35);">Nanti Saja</button>
  </div>
</div>
<script>
(function () {
  try {
    var key = "orulabsTrialNoticeDate";
    var today = "__TODAY__";
    if (localStorage.getItem(key) !== today) {
      localStorage.setItem(key, today);
      document.getElementById("__trialModalOverlay").style.display = "flex";
    }
  } catch (e) {}
})();
</script>
"""


def _render_trial_notice(trial):
    if trial["days_left"] <= 1:
        days_left_text = "Ini hari <b>TERAKHIR</b> masa percobaan."
    else:
        days_left_text = "Sisa <b>" + str(trial["days_left"]) + " hari</b> lagi masa percobaan."
    html = _TRIAL_MODAL_TEMPLATE
    html = html.replace("__DAY__", str(min(trial["day_number"], _TRIAL_DAYS)))
    html = html.replace("__DAYS_LEFT_TEXT__", days_left_text)
    html = html.replace("__TODAY__", date.today().isoformat())
    return html


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

    @app.after_request
    def _show_trial_reminder(response):
        """HP yang lagi jalan di masa percobaan (belum pernah masukin
        kode aktivasi sama sekali) dikasih pop-up pengingat ini SEKALI
        tiap hari kalender (dicek dari localStorage browser WebView-nya,
        bukan disimpan di server) - beda dari halaman "/__activation"
        yang MEMBLOKIR, pop-up ini cuma info, tidak mengganggu
        pemakaian. Bukan notifikasi sistem Android (tidak minta izin
        notifikasi apa pun) - cuma pop-up di dalam halaman itu sendiri."""

        if request.path.startswith("/__activation"):
            return response
        if response.status_code != 200 or not response.content_type or "text/html" not in response.content_type:
            return response

        trial = get_trial_info(data_dir)
        if trial is None or trial["expired"]:
            return response

        try:
            body = response.get_data(as_text=True)
        except (UnicodeDecodeError, RuntimeError):
            return response
        if "</body>" not in body:
            return response

        response.set_data(body.replace("</body>", _render_trial_notice(trial) + "</body>", 1))
        return response

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

        trial = get_trial_info(data_dir)
        return render_template_string(
            _ACTIVATION_PAGE, device_id=device_id, error=error,
            expired_notice=get_expired_notice(data_dir),
            trial_expired=bool(trial and trial["expired"]),
        )
