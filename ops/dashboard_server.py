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

import os

from flask import Flask, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DASHBOARD_PORT", "8790"))

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(HERE, "dashboard.html")


if __name__ == "__main__":
    print(f"Dashboard kontrol deploy: http://localhost:{PORT}")
    app.run(host="127.0.0.1", port=PORT)
