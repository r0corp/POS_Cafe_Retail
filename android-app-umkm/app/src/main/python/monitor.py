"""Status aktif ke penjual (opsional, bisa dimatikan pemakai).

Kalau ENDPOINT diisi (alamat Worker Pantau Aplikasi, lihat monitor-server/README.md), aplikasi
mengirim status ringan ke server itu sesekali selama dipakai dan ada internet. Yang dikirim HANYA:
Kode Perangkat, versi aplikasi, mode lisensi, tanggal berakhir sewa, platform, dan bahasa. Tidak ada
nama toko, data penjualan, menu, atau lokasi. Gagal kirim (offline, server mati) diam-diam diabaikan
dan tidak pernah mengganggu aplikasi.

ENDPOINT kosong = fitur tidak aktif sama sekali (tidak ada yang dikirim, kartu pengaturannya tersembunyi).

Jawaban server boleh memuat satu siaran dari penjual ({"msg": {"id", "text"}}, mis. info update). Siaran
ditampilkan sebagai teks biasa di aplikasi sampai ditutup pemakai, sekali untuk tiap id. Dimatikannya
"Kirim status aktif" juga menghentikan siaran (tidak ada kontak ke server sama sekali).
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


MAX_MESSAGE_CHARS = 280


def _broadcast_file(data_dir):
    return os.path.join(data_dir, "broadcast.json")


def _read_broadcast(data_dir):
    try:
        with open(_broadcast_file(data_dir), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def store_message(data_dir, msg):
    """Simpan siaran dari server. Id yang sama dengan yang sudah ada (ditutup atau belum) tidak ditimpa."""
    if not isinstance(msg, dict):
        return
    msg_id = str(msg.get("id") or "")[:32]
    text = "".join(ch for ch in str(msg.get("text") or "") if ch >= " " or ch == "\n").strip()[:MAX_MESSAGE_CHARS]
    if not msg_id or not text or _read_broadcast(data_dir).get("id") == msg_id:
        return
    try:
        with open(_broadcast_file(data_dir), "w", encoding="utf-8") as f:
            json.dump({"id": msg_id, "text": text, "dismissed": False}, f)
    except OSError:
        pass


def pending_message(data_dir):
    """Teks siaran yang belum ditutup pemakai, atau None."""
    data = _read_broadcast(data_dir)
    if data.get("text") and not data.get("dismissed"):
        return {"id": data["id"], "text": data["text"]}
    return None


def dismiss_message(data_dir):
    data = _read_broadcast(data_dir)
    if data:
        data["dismissed"] = True
        try:
            with open(_broadcast_file(data_dir), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass


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
            ok = response.status == 200
            if ok:
                try:
                    store_message(data_dir, json.loads(response.read(4096).decode("utf-8")).get("msg"))
                except ValueError:
                    pass
            return ok
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


def message_for_template(data_dir):
    """Siaran untuk banner; kosong bila fitur tidak terpasang/dimatikan."""
    if not ENDPOINT or not is_enabled(data_dir):
        return None
    return pending_message(data_dir)
