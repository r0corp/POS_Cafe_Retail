import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    # Sengaja TIDAK ada fallback ke nilai default - source code ini ada
    # di repo GitHub publik, jadi default apa pun yang ditulis di sini
    # otomatis diketahui semua orang. Kalau ini kepakai diam-diam (env
    # var lupa di-set), siapa pun yang baca repo publiknya bisa forge
    # session cookie & login sebagai owner tanpa password. Lebih baik
    # aplikasi gagal jelas saat start daripada jalan dengan lubang ini.
    raise RuntimeError(
        "SECRET_KEY belum di-set. Buat file .env (copy dari .env.example) "
        "lalu isi SECRET_KEY dengan nilai acak, contoh cara generate:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "Lihat DEPLOYMENT.md langkah 4 untuk detail."
    )


class Config:
    SECRET_KEY = _secret_key

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(BASE_DIR, "instance", "cafe.db")
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Batas ukuran 1 request (upload logo/foto/nada) - tanpa ini siapa pun,
    # termasuk dari halaman publik tamu, bisa kirim body raksasa.
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Tamu bisa buka halaman menu lewat QR lalu baru submit pesanan lama
    # kemudian (ngobrol dulu, dsb) - token CSRF default WTForms kedaluwarsa
    # 1 jam, jangan sampai submit pesanan gagal cuma gara-gara kelamaan
    # buka halamannya. Token tetap terikat ke session (SECRET_KEY), jadi
    # tidak mengurangi proteksi CSRF-nya sendiri.
    WTF_CSRF_TIME_LIMIT = None

    # Nama tampilan kafe, dipakai di header halaman & struk.
    CAFE_NAME = os.environ.get("CAFE_NAME") or "Kafe Saya"

    # Base URL dipakai saat generate QR code meja (mengarah ke halaman
    # pemesanan). Saat production, ganti ke IP/hostname server di
    # jaringan lokal, misalnya http://192.168.1.10:8000
    BASE_URL = os.environ.get("BASE_URL") or "http://127.0.0.1:5000"

    # Folder tempat file backup database (.zip) disimpan.
    BACKUP_FOLDER = os.environ.get("BACKUP_FOLDER") or os.path.join(BASE_DIR, "backups")
