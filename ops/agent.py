"""Ops Agent - service kecil terpisah dari aplikasi POS utama, jalan
terus di mini PC (lewat Scheduled Task/NSSM sendiri, lihat
install_agent.ps1) supaya tetap bisa dihubungi walau aplikasi POS
utama sedang di-restart/di-update.

Tugasnya cuma 2, dipanggil dari dashboard.html (laptop mana pun,
lewat Tailscale) pakai token rahasia di header X-Agent-Token:
  - GET  /status  -> commit yang sedang jalan vs commit terbaru di GitHub
  - POST /update  -> git fetch + reset --hard origin/main, sinkron
                      dependency, compile terjemahan, restart POS
Logikanya sama persis dengan migration/update_mini_pc.ps1, cuma
dipicu dari jarak jauh lewat HTTP alih-alih dijalankan manual."""

import hmac
import os
import subprocess
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

PROJECT_ROOT = os.environ.get(
    "PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
AGENT_TOKEN = os.environ.get("AGENT_TOKEN")
AGENT_PORT = int(os.environ.get("AGENT_PORT", "8787"))

# Cara restart aplikasi POS setelah update - beda mini PC bisa beda setup
# (NSSM service ATAU Scheduled Task "AutoStart" polos), jadi keduanya
# didukung. "auto" = pakai NSSM kalau nssm.exe ada, kalau tidak fallback
# ke Scheduled Task.
SERVICE_MODE = os.environ.get("SERVICE_MODE", "auto")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "OrulabsPOS")
NSSM_PATH = os.environ.get("NSSM_PATH", r"C:\nssm\nssm.exe")
TASK_NAME = os.environ.get("TASK_NAME", "CafePOS AutoStart")

if not AGENT_TOKEN:
    raise RuntimeError(
        "AGENT_TOKEN belum diisi di ops/.env - wajib diisi token rahasia "
        "(acak, panjang) sebelum agent ini boleh dijalankan."
    )

app = Flask(__name__)


def _run(cmd, cwd=None):
    result = subprocess.run(
        cmd, cwd=cwd or PROJECT_ROOT, capture_output=True, text=True, shell=False,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


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

    _run(["git", "fetch", "origin"])
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


@app.route("/update", methods=["POST", "OPTIONS"])
def update():
    if request.method == "OPTIONS":
        return "", 204
    if not _authorized():
        return _unauthorized()

    log_lines = []
    _, before = _run(["git", "rev-parse", "HEAD"])
    before = before.strip()

    mode = _stop_pos(log_lines)

    log_lines.append("$ git fetch origin")
    _, out = _run(["git", "fetch", "origin"])
    log_lines.append(out.strip())

    log_lines.append("$ git reset --hard origin/main")
    _, out = _run(["git", "reset", "--hard", "origin/main"])
    log_lines.append(out.strip())

    venv_pip = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pip.exe")
    if os.path.exists(venv_pip):
        log_lines.append("$ pip install -r requirements.txt")
        _, out = _run([venv_pip, "install", "-r", "requirements.txt", "--quiet"])
        log_lines.append(out.strip())

    venv_pybabel = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pybabel.exe")
    if os.path.exists(venv_pybabel):
        log_lines.append("$ pybabel compile -d app/translations")
        _, out = _run([venv_pybabel, "compile", "-d", os.path.join("app", "translations")])
        log_lines.append(out.strip())

    _start_pos(mode, log_lines)

    _, after = _run(["git", "rev-parse", "HEAD"])
    after = after.strip()

    return jsonify({
        "ok": True,
        "before": before,
        "after": after,
        "changed": before != after,
        "log": "\n".join(line for line in log_lines if line),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=AGENT_PORT)
