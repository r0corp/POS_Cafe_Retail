"""Ops Agent - service kecil terpisah dari aplikasi POS utama, jalan
terus di mini PC (lewat Scheduled Task/NSSM sendiri, lihat
install_agent.ps1) supaya tetap bisa dihubungi walau aplikasi POS
utama sedang di-restart/di-update.

Dipanggil dari dashboard.html (laptop mana pun, lewat Tailscale) pakai
token rahasia di header X-Agent-Token:
  - GET  /status         -> commit yang sedang jalan vs commit terbaru di GitHub
  - GET  /commits        -> riwayat commit terbaru (buat pilihan rollback)
  - POST /update         -> deploy ke origin/main (fetch + reset --hard + restart)
  - POST /rollback       -> deploy ke commit SHA tertentu (fetch + reset --hard
                             ke situ, BUKAN ke origin/main) - buat balik ke versi
                             sebelumnya kalau update terbaru ternyata bermasalah
  - GET  /logs           -> ekor log stdout/stderr aplikasi POS (lewat NSSM)
  - GET  /backups        -> daftar file backup database + ukuran & tanggal
  - POST /backups/verify -> cek 1 file backup beneran valid (bisa dibuka &
                             database di dalamnya lolos integrity check)
Logikanya sama persis dengan migration/update_mini_pc.ps1, cuma
dipicu dari jarak jauh lewat HTTP alih-alih dijalankan manual."""

import hmac
import os
import re
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

PROJECT_ROOT = os.environ.get(
    "PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
AGENT_TOKEN = os.environ.get("AGENT_TOKEN")
AGENT_PORT = int(os.environ.get("AGENT_PORT", "8787"))

# Dimuat lagi (setelah PROJECT_ROOT diketahui) supaya BACKUP_FOLDER kalau
# di-custom lewat .env aplikasi utama (bukan ops/.env) ikut kebaca -
# tidak nge-import config.py langsung supaya agent ini tidak ikut
# mewajibkan SECRET_KEY dkk yang cuma relevan buat aplikasi POS-nya.
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
BACKUP_FOLDER = os.environ.get("BACKUP_FOLDER") or os.path.join(PROJECT_ROOT, "backups")

# Cara restart aplikasi POS setelah update - beda mini PC bisa beda setup
# (NSSM service ATAU Scheduled Task "AutoStart" polos), jadi keduanya
# didukung. "auto" = pakai NSSM kalau nssm.exe ada, kalau tidak fallback
# ke Scheduled Task.
SERVICE_MODE = os.environ.get("SERVICE_MODE", "auto")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "OrulabsPOS")
NSSM_PATH = os.environ.get("NSSM_PATH", r"C:\nssm\nssm.exe")
TASK_NAME = os.environ.get("TASK_NAME", "CafePOS AutoStart")

# Internet mini PC kadang putus-nyambung - tanpa batas waktu eksplisit,
# `git fetch`/`pip install` bisa nyangkut lama sekali (menit) nunggu
# koneksi yang tidak akan pernah nyambung, bukannya gagal cepat.
FETCH_TIMEOUT = 20
PIP_TIMEOUT = 180

if not AGENT_TOKEN:
    raise RuntimeError(
        "AGENT_TOKEN belum diisi di ops/.env - wajib diisi token rahasia "
        "(acak, panjang) sebelum agent ini boleh dijalankan."
    )

app = Flask(__name__)


def _run(cmd, cwd=None, timeout=None):
    try:
        result = subprocess.run(
            cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True, shell=False, timeout=timeout,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, f"(timeout setelah {timeout} detik - internet/koneksi kemungkinan lambat atau macet)"


def _authorized():
    supplied = request.headers.get("X-Agent-Token", "")
    return bool(AGENT_TOKEN) and hmac.compare_digest(supplied, AGENT_TOKEN)


def _unauthorized():
    return jsonify({"error": "unauthorized"}), 401


def _nssm_available():
    return os.path.exists(NSSM_PATH)


def _resolved_mode():
    if SERVICE_MODE in ("nssm", "task"):
        return SERVICE_MODE
    return "nssm" if _nssm_available() else "task"


def _nssm_get(param):
    _, out = _run([NSSM_PATH, "get", SERVICE_NAME, param])
    # Sama seperti "nssm status" - outputnya UTF-16, buang byte null-nya.
    return out.replace("\x00", "").strip()


def _tail_file(path, max_lines):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.readlines()
        return "".join(content[-max_lines:])
    except OSError as e:
        return f"(gagal baca file: {e})"


def _verify_backup_zip(zip_path):
    """Buka file backup .zip, keluarkan database di dalamnya, lalu
    jalankan PRAGMA integrity_check - supaya "backup sudah dibuat"
    beneran berarti "backup bisa dipulihkan", bukan cuma file .zip yang
    ada tapi ternyata isinya korup/kosong."""

    try:
        with zipfile.ZipFile(zip_path) as zf:
            db_entries = [n for n in zf.namelist() if n.startswith("instance/") and n.endswith(".db")]
            if not db_entries:
                return False, "Tidak ada file database di dalam zip ini."

            with tempfile.TemporaryDirectory() as tmp_dir:
                extracted_path = zf.extract(db_entries[0], tmp_dir)
                conn = sqlite3.connect(extracted_path)
                try:
                    result = conn.execute("PRAGMA integrity_check").fetchone()
                finally:
                    conn.close()

        if result and result[0] == "ok":
            return True, "Database di dalam backup valid dan bisa dipulihkan."
        return False, f"Database di dalam backup TIDAK valid: {result}"
    except zipfile.BadZipFile:
        return False, "File .zip rusak/tidak bisa dibuka."
    except Exception as e:
        return False, str(e)


def _powershell(command):
    return _run(["powershell", "-NoProfile", "-Command", command])


def _service_status():
    mode = _resolved_mode()
    if mode == "nssm":
        _, out = _run([NSSM_PATH, "status", SERVICE_NAME])
        # nssm.exe mencetak ke console pakai UTF-16 - subprocess.run(text=True)
        # mendekodenya pakai encoding default OS, jadi tiap karakter kepisah
        # byte null ("S\x00E\x00R\x00..."). Buang byte null-nya saja.
        return out.replace("\x00", "").strip() or "unknown"
    _, out = _powershell(f"(Get-ScheduledTask -TaskName '{TASK_NAME}').State")
    return out.strip() or "unknown"


def _stop_pos(log_lines):
    mode = _resolved_mode()
    if mode == "nssm":
        log_lines.append(f"$ nssm stop {SERVICE_NAME}")
        _, out = _run([NSSM_PATH, "stop", SERVICE_NAME])
    else:
        log_lines.append(f"$ Stop-ScheduledTask '{TASK_NAME}' + hentikan proses serve_production.py")
        _, out = _powershell(
            f"Stop-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue; "
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -like '*serve_production.py*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
    log_lines.append(out.strip())
    return mode


def _start_pos(mode, log_lines):
    if mode == "nssm":
        log_lines.append(f"$ nssm start {SERVICE_NAME}")
        _, out = _run([NSSM_PATH, "start", SERVICE_NAME])
    else:
        log_lines.append(f"$ Start-ScheduledTask '{TASK_NAME}'")
        _, out = _powershell(f"Start-ScheduledTask -TaskName '{TASK_NAME}'")
    log_lines.append(out.strip())


def _commit_info(ref):
    _, out = _run(["git", "log", "-1", f"--format=%H|%s|%ci", ref])
    parts = out.strip().split("|", 2)
    if len(parts) != 3:
        return {"hash": ref, "message": "?", "date": "?"}
    return {"hash": parts[0], "message": parts[1], "date": parts[2]}


@app.after_request
def add_cors_headers(response):
    # Dashboard-nya statis (dibuka langsung dari file lokal/laptop mana
    # pun di tailnet), jadi originnya tidak tetap - CORS dibuka semua
    # origin, keamanan tetap ditegakkan lewat token di setiap request.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "X-Agent-Token, Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/ping", methods=["GET"])
def ping():
    # Sengaja TANPA token - cuma buat cek agent-nya hidup/tidak, tidak
    # membocorkan informasi apa pun.
    return jsonify({"ok": True, "service": "orulabs-ops-agent"})


@app.route("/status", methods=["GET", "OPTIONS"])
def status():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    _run(["git", "fetch", "origin"], timeout=FETCH_TIMEOUT)
    _, current_hash = _run(["git", "rev-parse", "HEAD"])
    _, latest_hash = _run(["git", "rev-parse", "origin/main"])
    current_hash = current_hash.strip()
    latest_hash = latest_hash.strip()

    pending_commits = []
    if current_hash and latest_hash and current_hash != latest_hash:
        _, pending_log = _run(["git", "log", "--format=%H|%s|%ci", f"{current_hash}..{latest_hash}"])
        for line in pending_log.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                pending_commits.append({"hash": parts[0], "message": parts[1], "date": parts[2]})

    return jsonify({
        "current": _commit_info("HEAD"),
        "latest": _commit_info("origin/main"),
        "pending_commits": pending_commits,
        "up_to_date": current_hash == latest_hash,
        "service_status": _service_status(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _commit_exists(sha):
    """Pastikan `sha` beneran commit yang ada di riwayat repo ini SEBELUM
    dipakai di `git reset --hard` - mencegah string aneh dari request
    (typo, atau percobaan jahil) diperlakukan sebagai flag/argumen git."""

    if not FULL_SHA_RE.match(sha):
        return False
    code, _ = _run(["git", "cat-file", "-e", f"{sha}^{{commit}}"])
    return code == 0


def _deploy_to(target_ref, log_lines, require_fetch):
    """Inti dari /update & /rollback - satu-satunya beda cuma target_ref
    ("origin/main" buat update, sebuah commit SHA buat rollback) dan
    require_fetch.

    git fetch dijalankan DULU, SEBELUM aplikasi POS dimatikan - supaya
    kalau internet mini PC lagi bermasalah (timeout/putus), aplikasi
    TIDAK ikut dimatikan sia-sia untuk deploy yang toh tidak akan
    berhasil. Ini nyata kejadian sekali: /rollback sempat mematikan POS
    lalu macet nunggu fetch yang tidak pernah selesai, aplikasi mati
    sampai ada yang nyalakan manual.

    require_fetch=True (dipakai /update): fetch WAJIB berhasil dulu -
    origin/main butuh commit terbaru dari GitHub, jadi kalau fetch
    gagal/timeout, deploy dibatalkan total, POS tidak disentuh sama
    sekali. require_fetch=False (dipakai /rollback): commit tujuannya
    sudah pasti ada di riwayat lokal (sudah divalidasi _commit_exists
    sebelum fungsi ini dipanggil) - TIDAK butuh data baru dari GitHub,
    jadi fetch cuma usaha terbaik (buat data /commits tetap segar),
    boleh lanjut walau fetch-nya gagal.

    Return True kalau proses deploy (stop-reset-restart) benar-benar
    dijalankan, False kalau dibatalkan sebelum sempat menyentuh POS."""

    log_lines.append("$ git fetch origin")
    fetch_code, out = _run(["git", "fetch", "origin"], timeout=FETCH_TIMEOUT)
    log_lines.append(out.strip())

    if fetch_code != 0:
        if require_fetch:
            log_lines.append(
                "Fetch dari GitHub gagal/timeout - deploy DIBATALKAN, aplikasi POS TIDAK disentuh sama sekali."
            )
            return False
        log_lines.append(
            "Fetch dari GitHub gagal/timeout - lanjut pakai riwayat commit lokal yang sudah ada (rollback tidak butuh data baru)."
        )

    mode = _stop_pos(log_lines)

    log_lines.append(f"$ git reset --hard {target_ref}")
    _, out = _run(["git", "reset", "--hard", target_ref])
    log_lines.append(out.strip())

    venv_pip = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pip.exe")
    if os.path.exists(venv_pip):
        log_lines.append("$ pip install -r requirements.txt")
        _, out = _run([venv_pip, "install", "-r", "requirements.txt", "--quiet"], timeout=PIP_TIMEOUT)
        log_lines.append(out.strip())

    venv_pybabel = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pybabel.exe")
    if os.path.exists(venv_pybabel):
        log_lines.append("$ pybabel compile -d app/translations")
        _, out = _run([venv_pybabel, "compile", "-d", os.path.join("app", "translations")], timeout=30)
        log_lines.append(out.strip())

    _start_pos(mode, log_lines)
    return True


@app.route("/commits", methods=["GET", "OPTIONS"])
def commits():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    limit = request.args.get("limit", default=20, type=int)
    _run(["git", "fetch", "origin"], timeout=FETCH_TIMEOUT)
    _, out = _run(["git", "log", f"-{limit}", "--format=%H|%s|%ci", "origin/main"])

    history = []
    for line in out.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            history.append({"hash": parts[0], "message": parts[1], "date": parts[2]})

    _, current_hash = _run(["git", "rev-parse", "HEAD"])
    return jsonify({"commits": history, "current": current_hash.strip()})


@app.route("/update", methods=["POST", "OPTIONS"])
def update():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    log_lines = []
    _, before = _run(["git", "rev-parse", "HEAD"])
    before = before.strip()

    deployed = _deploy_to("origin/main", log_lines, require_fetch=True)

    _, after = _run(["git", "rev-parse", "HEAD"])
    after = after.strip()

    return jsonify({
        "ok": deployed,
        "before": before,
        "after": after,
        "changed": before != after,
        "log": "\n".join(line for line in log_lines if line),
    })


@app.route("/rollback", methods=["POST", "OPTIONS"])
def rollback():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    target = (request.get_json(silent=True) or {}).get("commit") or request.form.get("commit", "")
    target = target.strip().lower()

    if not _commit_exists(target):
        return jsonify({"error": "Commit tidak valid atau tidak ditemukan di riwayat repo ini."}), 400

    log_lines = []
    _, before = _run(["git", "rev-parse", "HEAD"])
    before = before.strip()

    deployed = _deploy_to(target, log_lines, require_fetch=False)

    _, after = _run(["git", "rev-parse", "HEAD"])
    after = after.strip()

    return jsonify({
        "ok": deployed,
        "before": before,
        "after": after,
        "changed": before != after,
        "log": "\n".join(line for line in log_lines if line),
    })


@app.route("/logs", methods=["GET", "OPTIONS"])
def logs():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    if _resolved_mode() != "nssm":
        return jsonify({
            "configured": False,
            "message": "Lihat log dari jarak jauh cuma didukung untuk mode NSSM saat ini.",
        })

    max_lines = request.args.get("lines", default=200, type=int)
    stdout_path = _nssm_get("AppStdout")
    stderr_path = _nssm_get("AppStderr")

    stdout_content = _tail_file(stdout_path, max_lines)
    stderr_content = _tail_file(stderr_path, max_lines)

    if not stdout_path and not stderr_path:
        return jsonify({
            "configured": False,
            "message": (
                "Log file belum diatur di NSSM. Jalankan sekali (sebagai Administrator) "
                "di mini PC untuk mengaktifkan, lalu restart service:\n"
                f'mkdir "{PROJECT_ROOT}\\logs" -Force\n'
                f'& "{NSSM_PATH}" set {SERVICE_NAME} AppStdout "{PROJECT_ROOT}\\logs\\stdout.log"\n'
                f'& "{NSSM_PATH}" set {SERVICE_NAME} AppStderr "{PROJECT_ROOT}\\logs\\stderr.log"\n'
                f'& "{NSSM_PATH}" set {SERVICE_NAME} AppRotateFiles 1\n'
                f'& "{NSSM_PATH}" set {SERVICE_NAME} AppRotateBytes 5242880\n'
                f'& "{NSSM_PATH}" restart {SERVICE_NAME}'
            ),
        })

    return jsonify({
        "configured": True,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "stdout": stdout_content or "(kosong)",
        "stderr": stderr_content or "(kosong)",
    })


@app.route("/backups", methods=["GET", "OPTIONS"])
def backups():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    if not os.path.isdir(BACKUP_FOLDER):
        return jsonify({"folder": BACKUP_FOLDER, "backups": []})

    files = []
    for name in os.listdir(BACKUP_FOLDER):
        if not (name.startswith("cafepos_backup_") and name.endswith(".zip")):
            continue
        path = os.path.join(BACKUP_FOLDER, name)
        if not os.path.isfile(path):
            continue
        files.append({
            "name": name,
            "size_mb": round(os.path.getsize(path) / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat(),
        })
    files.sort(key=lambda f: f["modified"], reverse=True)

    return jsonify({"folder": BACKUP_FOLDER, "backups": files})


@app.route("/backups/verify", methods=["POST", "OPTIONS"])
def backups_verify():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    raw_name = (request.get_json(silent=True) or {}).get("name", "")
    # os.path.basename buang komponen folder - cegah path traversal
    # (mis. "../../../windows/system32/...") lewat nama file ini.
    name = os.path.basename(raw_name)
    path = os.path.join(BACKUP_FOLDER, name)

    if not name or not os.path.isfile(path):
        return jsonify({"error": "File backup tidak ditemukan."}), 404

    ok, message = _verify_backup_zip(path)
    return jsonify({"ok": ok, "message": message})


if __name__ == "__main__":
    # threaded=True - tanpa ini, server dev Flask cuma layani 1 request
    # sekaligus: /update atau /rollback yang butuh puluhan detik (pip
    # install, dst) bikin /ping & /status ikut macet tidak terjawab
    # sampai proses itu selesai, padahal /ping/-status idealnya tetap
    # bisa dicek kapan saja buat tahu agent-nya masih hidup atau tidak.
    app.run(host="0.0.0.0", port=AGENT_PORT, threaded=True)
