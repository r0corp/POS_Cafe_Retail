"""Server statis kecil buat dashboard.html - biar bisa diakses lewat
alamat tetap (http://localhost:8790) alih-alih buka file dashboard.html
manual tiap kali lewat File Explorer.

Sengaja cuma bind ke 127.0.0.1 (laptop ini sendiri) - TIDAK diekspos ke
jaringan/Tailscale, karena memang tidak perlu: dashboard-nya sendiri
yang menghubungi tiap mini PC lewat Tailscale (arah keluar), bukan
device lain yang perlu menghubungi dashboard ini.

Cara pakai:
    python ops\\dashboard_server.py
lalu buka http://localhost:8790 di browser."""

import json
import os
import shutil
import subprocess
import uuid

from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DASHBOARD_PORT", "8790"))

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


def _find_tailscale():
    on_path = shutil.which("tailscale")
    if on_path:
        return on_path
    for candidate in TAILSCALE_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


@app.route("/")
def index():
    return send_from_directory(HERE, "dashboard.html")


@app.route("/api/tailscale-devices")
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
def list_agents():
    return jsonify({"agents": _load_agents()})


@app.route("/api/agents", methods=["POST"])
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
def delete_agent(agent_id):
    agents = _load_agents()
    remaining = [a for a in agents if a["id"] != agent_id]
    if len(remaining) == len(agents):
        return jsonify({"error": "Mini PC tidak ditemukan."}), 404
    _save_agents(remaining)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"Dashboard kontrol deploy: http://localhost:{PORT}")
    app.run(host="127.0.0.1", port=PORT)
