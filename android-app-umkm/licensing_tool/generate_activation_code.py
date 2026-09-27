"""Dipakai TIAP ADA PENJUALAN BARU - generate Kode Aktivasi buat 1
pembeli, dari Kode Perangkat yang mereka kirim (WA/dst).

    python generate_activation_code.py KODE-PERANGKAT-DARI-PEMBELI

Butuh private_key.json di folder ini (hasil generate_keypair.py, cuma
sekali dijalankan). Kode Aktivasi yang keluar cuma valid buat HP yang
Kode Perangkat-nya persis sama - dicoba di HP lain otomatis ditolak.
"""

import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from rsa_util import sign

PRIVATE_KEY_FILE = os.path.join(os.path.dirname(__file__), "private_key.json")

# HARUS PERSIS SAMA dengan _SIGN_SALT di
# android-app-umkm/app/src/main/python/licensing.py.
_SIGN_SALT = b"orulabs-apk-umkm-activation-v1"


def _b32(data):
    return base64.b32encode(data).decode("ascii").rstrip("=")


def hash_to_int(device_id):
    digest = hashlib.sha256(_SIGN_SALT + device_id.encode()).digest()
    return int.from_bytes(digest, "big")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Pakai: python generate_activation_code.py KODE-PERANGKAT-DARI-PEMBELI")
        sys.exit(1)

    if not os.path.exists(PRIVATE_KEY_FILE):
        print(f"'{PRIVATE_KEY_FILE}' tidak ada - jalankan generate_keypair.py dulu (sekali saja).")
        sys.exit(1)

    with open(PRIVATE_KEY_FILE, "r", encoding="utf-8") as f:
        key = json.load(f)

    device_id = sys.argv[1].strip().upper()
    message_int = hash_to_int(device_id)
    signature_int = sign(message_int, (key["n"], key["d"]))
    signature_bytes = signature_int.to_bytes((signature_int.bit_length() + 7) // 8, "big")

    code = _b32(signature_bytes)
    print()
    print(f"Kode Perangkat : {device_id}")
    print(f"Kode Aktivasi  : {code}")
    print()
    print("Kirim baris 'Kode Aktivasi' di atas ke pembeli.")
