"""Status aktif ke penjual (opsional, bisa dimatikan pemakai).

Kalau ENDPOINT diisi (alamat Worker Pantau Aplikasi, lihat monitor-server/README.md), aplikasi
mengirim status ringan ke server itu sesekali selama dipakai dan ada internet. Yang dikirim HANYA:
Kode Perangkat, versi aplikasi, mode lisensi, tanggal berakhir sewa, platform, dan bahasa. Tidak ada
nama toko, data penjualan, menu, atau lokasi. Gagal kirim (offline, server mati) diam-diam diabaikan
dan tidak pernah mengganggu aplikasi.

ENDPOINT kosong = fitur tidak aktif sama sekali (tidak ada yang dikirim, kartu pengaturannya tersembunyi).
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import date

# Isi setelah Worker dipasang, contoh: "https://orugo-monitor.NAMA-AKUN.workers.dev"
ENDPOINT = ""

FIRST_DELAY_SECONDS = 20
INTERVAL_SECONDS = 300
TIMEOUT_SECONDS = 8

_started = {"thread": None}


def _file(data_dir):
    return os.path.join(data_dir, "monitor.json")


def is_enabled(data_dir):
    """Aktif secara bawaan; pemakai bisa mematikannya di Pengaturan > Sistem > Lisensi."""
    try:
        with open(_file(data_dir), encoding="utf-8") as f:
            return bool(json.load(f).get("enabled", True))
    except (OSError, ValueError):
        return True


def set_enabled(data_dir, enabled):
    with open(_file(data_dir), "w", encoding="utf-8") as f:
        json.dump({"enabled": bool(enabled)}, f)


def app_version():
    """Versi aplikasi: dari env (cangkang iOS) atau PackageInfo Android (lewat Chaquopy)."""
    value = os.environ.get("ORULABS_APP_VERSION")
    if value:
        return value
    try:
        from com.chaquo.python import Python

        context = Python.getPlatform().getApplication()
        return str(context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName)
    except Exception:
        return "0"


def build_payload(data_dir, version=None, today=None):
    import licensing

    state = licensing.get_license_state(data_dir)
    mode = state["mode"]
    expiry = ""
    if mode == "rental":
        expiry = (state.get("expiry_text") or "").replace("-", "")
        if expiry and expiry < (today or date.today()).strftime("%Y%m%d"):
            mode = "expired"
    return {
        "d": state["device_id"],
        "v": version or app_version(),
        "m": mode,
        "x": expiry,
        "p": "ios" if os.environ.get("ORULABS_MOBILE_OS") == "ios" else "android",
        "l": "id",
    }


def send_once(data_dir, endpoint=None, version=None):
    """Kirim satu heartbeat. True bila server menjawab 200."""
    endpoint = endpoint if endpoint is not None else ENDPOINT
    if not endpoint or not is_enabled(data_dir):
        return False
    try:
        body = json.dumps(build_payload(data_dir, version=version)).encode("utf-8")
        request = urllib.request.Request(
            endpoint.rstrip("/") + "/v1/hb", data=body, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "OruPOSGO"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status == 200
    except Exception:
        return False


def _loop(data_dir, endpoint):
    time.sleep(FIRST_DELAY_SECONDS)
    while True:
        send_once(data_dir, endpoint)
        time.sleep(INTERVAL_SECONDS)


def start(data_dir, endpoint=None):
    """Mulai pengirim di thread latar (sekali saja per proses). Tidak melakukan apa-apa bila ENDPOINT kosong."""
    endpoint = endpoint if endpoint is not None else ENDPOINT
    if not endpoint or _started["thread"] is not None:
        return None
    thread = threading.Thread(target=_loop, args=(data_dir, endpoint), name="monitor", daemon=True)
    thread.start()
    _started["thread"] = thread
    return thread


def state(data_dir):
    """Untuk template: kartu pengaturan hanya tampil bila fitur dipasang (ENDPOINT terisi)."""
    return {"available": bool(ENDPOINT), "enabled": is_enabled(data_dir)}
