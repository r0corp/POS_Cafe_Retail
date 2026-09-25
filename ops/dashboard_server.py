"""Server statis kecil buat dashboard.html - biar bisa diakses lewat
alamat tetap (http://localhost:8790) alih-alih buka file dashboard.html
manual tiap kali lewat File Explorer.

Bind ke 0.0.0.0 - bisa diakses dari device lain (HP, dll) lewat IP
Tailscale laptop ini, bukan cuma dari laptop itu sendiri. Karena
dashboard ini bisa memicu Update/Rollback ke POS café yang live dan
/api/agents menyimpan token semua mini PC, akses ke sini WAJIB login
(lihat DASHBOARD_PASSWORD di bawah) - jangan andalkan cuma "yang tahu
alamatnya" sebagai proteksi.

Cara pakai:
    python ops\\dashboard_server.py
lalu buka http://localhost:8790 (dari laptop ini) atau
http://<IP-tailscale-laptop-ini>:8790 (dari HP/device lain di tailnet
yang sama)."""

import hmac
import json
import os
import secrets
import shutil
import subprocess
import uuid
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

PORT = int(os.environ.get("DASHBOARD_PORT", "8790"))

# Password buat masuk ke dashboard - WAJIB diisi di ops/.env, sengaja
# tidak ada default, supaya tidak keimpor lupa diisi lalu dashboard-nya
# kebuka bebas begitu di-bind ke 0.0.0.0.
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD")
if not DASHBOARD_PASSWORD:
    raise RuntimeError(
        "DASHBOARD_PASSWORD belum diisi di ops/.env - wajib diisi karena dashboard "
        "ini sekarang bisa diakses dari jaringan/Tailscale, bukan cuma laptop ini "
        "sendiri, dan berisi token rahasia semua mini PC."
    )
# Secret key buat sesi login - beda tiap kali service restart itu tidak
# masalah (paling semua orang cuma perlu login ulang), dan tidak perlu
# diisi manual di .env.
FLASK_SECRET_KEY = secrets.token_hex(32)

# Daftar mini PC yang terdaftar di dashboard ini - disimpan di file lokal
# (bukan localStorage browser) supaya "statis": selalu sama isinya berapa
# pun kali dashboard dibuka, browser apa pun dipakai, dan tidak hilang
# kalau sebelumnya sempat dibuka lewat cara lain (file:// vs http://).
# File ini SENGAJA tidak masuk git (lihat .gitignore) karena isinya token
# rahasia tiap mini PC.
AGENTS_FILE = os.path.join(HERE, "dashboard_agents.json")


def _load_agents():
    if not os.path.exists(AGENTS_FILE):
        return []
    try:
        with open(AGENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_agents(agents):
    with open(AGENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)

# Dicari di lokasi umum instalasi Tailscale di Windows kalau tidak ada
# di PATH (umum terjadi - installer GUI-nya tidak selalu nambahin PATH).
TAILSCALE_CANDIDATES = [
    os.environ.get("TAILSCALE_PATH", ""),
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
]

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


def _find_tailscale():
    on_path = shutil.which("tailscale")
    if on_path:
        return on_path
    for candidate in TAILSCALE_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


LOGIN_PAGE = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Login - Orulabs POS Kontrol Deploy</title>
<style>
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #0B1220; color: #E7ECF3; font-family: -apple-system, Segoe UI, Arial, sans-serif;
  }}
  form {{
    background: #131C2E; border: 1px solid #1F2A3D; border-radius: 14px;
    padding: 28px 26px; width: 280px;
  }}
  h1 {{ font-size: 16px; margin: 0 0 18px; }}
  input {{
    width: 100%; box-sizing: border-box; background: #0A0F1A; border: 1px solid #1F2A3D;
    color: #E7ECF3; border-radius: 8px; padding: 10px 12px; font-size: 14px; margin-bottom: 12px;
  }}
  button {{
    width: 100%; background: #F07828; color: #fff; border: none; border-radius: 10px;
    padding: 10px; font-size: 14px; font-weight: 700; cursor: pointer;
  }}
  .err {{ color: #FF5C5C; font-size: 12px; margin: -6px 0 12px; }}
</style></head>
<body>
<form method="post">
  <h1>Orulabs POS &middot; Kontrol Deploy</h1>
  {error_html}
  <input type="password" name="password" placeholder="Password" autofocus>
  <button type="submit">Masuk</button>
</form>
</body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    error_html = ""
    if request.method == "POST":
        supplied = request.form.get("password", "")
        if hmac.compare_digest(supplied, DASHBOARD_PASSWORD):
            session["authenticated"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error_html = '<div class="err">Password salah.</div>'
    return LOGIN_PAGE.format(error_html=error_html)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return send_from_directory(HERE, "dashboard.html")


@app.route("/api/tailscale-devices")
@login_required
def tailscale_devices():
    # Endpoint ini murni BACA status Tailscale (read-only, tidak ada
    # command apa pun yang bisa dipengaruhi lewat parameter request) -
    # dipakai dashboard buat menyarankan IP mini PC yang sudah ada di
    # tailnet, supaya tidak perlu ketik/salin IP manual tiap tambah
    # cabang baru.
    tailscale_exe = _find_tailscale()
    if not tailscale_exe:
        return jsonify({"error": "tailscale.exe tidak ditemukan di laptop ini."}), 500

    try:
        result = subprocess.run(
            [tailscale_exe, "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(result.stdout)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    nodes = list(data.get("Peer", {}).values())
    self_node = data.get("Self")
    if self_node:
        nodes.append(self_node)

    devices = [
        {
            "name": node.get("HostName", "?"),
            "ip": (node.get("TailscaleIPs") or [None])[0],
            "os": node.get("OS", "?"),
            "online": bool(node.get("Online")),
            "is_self": node is self_node,
        }
        for node in nodes
        if (node.get("TailscaleIPs") or [None])[0]
    ]

    return jsonify({"devices": devices})


@app.route("/api/agents", methods=["GET"])
@login_required
def list_agents():
    return jsonify({"agents": _load_agents()})


@app.route("/api/agents", methods=["POST"])
@login_required
def add_agent():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    host = (body.get("host") or "").strip()
    port = (body.get("port") or "").strip() or "8787"
    token = (body.get("token") or "").strip()

    if not name or not host or not token:
        return jsonify({"error": "Nama, host, dan token wajib diisi."}), 400

    agents = _load_agents()
    agent = {"id": uuid.uuid4().hex[:12], "name": name, "host": host, "port": port, "token": token}
    agents.append(agent)
    _save_agents(agents)
    return jsonify({"agent": agent}), 201


@app.route("/api/agents/<agent_id>", methods=["PUT"])
@login_required
def update_agent(agent_id):
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    host = (body.get("host") or "").strip()
    port = (body.get("port") or "").strip() or "8787"
    token = (body.get("token") or "").strip()

    if not name or not host or not token:
        return jsonify({"error": "Nama, host, dan token wajib diisi."}), 400

    agents = _load_agents()
    for a in agents:
        if a["id"] == agent_id:
            a.update({"name": name, "host": host, "port": port, "token": token})
            _save_agents(agents)
            return jsonify({"agent": a})

    return jsonify({"error": "Mini PC tidak ditemukan."}), 404


@app.route("/api/agents/<agent_id>", methods=["DELETE"])
@login_required
def delete_agent(agent_id):
    agents = _load_agents()
    remaining = [a for a in agents if a["id"] != agent_id]
    if len(remaining) == len(agents):
        return jsonify({"error": "Mini PC tidak ditemukan."}), 404
    _save_agents(remaining)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"Dashboard kontrol deploy: http://localhost:{PORT}")
    print("Juga bisa diakses dari device lain di tailnet yang sama lewat IP Tailscale laptop ini.")
    app.run(host="0.0.0.0", port=PORT)
