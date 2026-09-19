"""Buat akun awal untuk tiap role, supaya bisa langsung dicoba login.
Jalankan sekali: python seed_users.py

PENTING: password di bawah cuma untuk awal/testing. Segera login dan
ganti password masing-masing, atau buat user baru lewat halaman
Kelola User (khusus role Owner) lalu nonaktifkan akun contoh ini."""

from app import create_app, db
from app.models import User, ROLE_OWNER, ROLE_KASIR, ROLE_DAPUR, ROLE_PELAYAN

app = create_app()

DEFAULT_USERS = [
    ("owner", "owner123", ROLE_OWNER),
    ("kasir", "kasir123", ROLE_KASIR),
    ("dapur", "dapur123", ROLE_DAPUR),
    ("pelayan", "pelayan123", ROLE_PELAYAN),
]

with app.app_context():
    if User.query.first():
        print("Sudah ada user, dilewati.")
    else:
        for username, password, role in DEFAULT_USERS:
            user = User(username=username, role=role)
            user.set_password(password)
            db.session.add(user)

        db.session.commit()

        print("Akun awal berhasil dibuat:")
        for username, password, role in DEFAULT_USERS:
            print(f"  {username} / {password}  ({role})")
        print("Segera login dan ganti password masing-masing akun.")
