"""Jalankan SEKALI SAJA buat bikin sepasang kunci RSA buat aktivasi APK
UMKM.

    python generate_keypair.py

Private key disimpan ke private_key.json di folder ini - JANGAN PERNAH
commit/kirim file ini ke mana pun, cukup disimpan di laptop sendiri
(sudah masuk .gitignore). Public key ditampilkan buat ditempel ke
android-app-umkm/app/src/main/python/licensing.py (PUBLIC_KEY_N /
PUBLIC_KEY_E), lalu APK di-build ulang.

Kalau generate_keypair.py dijalankan ULANG (bikin keypair baru), semua
kode aktivasi yang sudah pernah dikirim ke pembeli lama otomatis tidak
valid lagi (public key di APK lama beda dengan private key baru) -
jadi jangan diulang kecuali memang niat ganti kunci total.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from rsa_util import generate_keypair

PRIVATE_KEY_FILE = os.path.join(os.path.dirname(__file__), "private_key.json")

if os.path.exists(PRIVATE_KEY_FILE):
    print(f"'{PRIVATE_KEY_FILE}' sudah ada - hapus manual dulu kalau memang")
    print("niat generate keypair baru (baca peringatan di docstring file ini).")
    sys.exit(1)

print("Generating RSA-2048 keypair (perlu beberapa detik)...")
(n, e), (n2, d) = generate_keypair(bits=2048)

with open(PRIVATE_KEY_FILE, "w", encoding="utf-8") as f:
    json.dump({"n": n, "d": d}, f)

print()
print(f"Private key tersimpan di: {PRIVATE_KEY_FILE}")
print("JANGAN PERNAH commit/share file itu ke mana pun.")
print()
print("Tempel 2 baris ini ke android-app-umkm/app/src/main/python/licensing.py:")
print()
print(f"PUBLIC_KEY_N = {n}")
print(f"PUBLIC_KEY_E = {e}")
