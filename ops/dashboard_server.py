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

from flask import Flask, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DASHBOARD_PORT", "8790"))

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


if __name__ == "__main__":
    print(f"Dashboard kontrol deploy: http://localhost:{PORT}")
    app.run(host="127.0.0.1", port=PORT)
