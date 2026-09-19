import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "cafe-pos-dev-secret-key"

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(BASE_DIR, "instance", "cafe.db")
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Nama tampilan kafe, dipakai di header halaman & struk.
    CAFE_NAME = os.environ.get("CAFE_NAME") or "Kafe Saya"

    # Base URL dipakai saat generate QR code meja (mengarah ke halaman
    # pemesanan). Saat production, ganti ke IP/hostname server di
    # jaringan lokal, misalnya http://192.168.1.10:8000
    BASE_URL = os.environ.get("BASE_URL") or "http://127.0.0.1:5000"

    # Folder tempat file backup database (.zip) disimpan.
    BACKUP_FOLDER = os.environ.get("BACKUP_FOLDER") or os.path.join(BASE_DIR, "backups")
