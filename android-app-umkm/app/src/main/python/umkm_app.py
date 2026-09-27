"""Entry point yang dipanggil dari MainActivity.java lewat Chaquopy.

Tugasnya: siapkan tempat penyimpanan yang BENAR-BENAR bisa ditulis di
dalam HP (folder bundel dari APK sendiri cuma untuk dibaca), lalu
jalankan app Flask yang SAMA PERSIS dipakai di server/mini PC - tanpa
diubah - supaya template & tampilannya identik.
"""

import hashlib
import os
import secrets

# reportlab manggil hashlib.md5(usedforsecurity=False) (buat FIPS
# compliance) - openssl_md5 versi Chaquopy di Android tidak menerima
# argumen itu sama sekali (TypeError). Tidak ada hubungannya dengan
# keamanan (cuma dipakai reportlab sebagai penanda dokumen PDF, bukan
# kriptografi sungguhan), jadi aman dibuang saja di sini - satu-satunya
# tempat lain yang perlu tahu soal ini.
_orig_md5 = hashlib.md5


def _md5_compat(*args, **kwargs):
    kwargs.pop("usedforsecurity", None)
    return _orig_md5(*args, **kwargs)


hashlib.md5 = _md5_compat
import shutil


def _ensure_secret_key(data_dir):
    """SECRET_KEY wajib ada sebelum config.py di-import (lihat
    config.py) - beda dari server, di sini tidak ada orang yang isi
    file .env manual, jadi digenerate sendiri sekali lalu disimpan
    supaya sesi login tidak batal tiap app dibuka ulang."""

    key_file = os.path.join(data_dir, "secret_key.txt")
    if os.path.exists(key_file):
        with open(key_file, "r") as f:
            return f.read().strip()

    key = secrets.token_hex(32)
    with open(key_file, "w") as f:
        f.write(key)
    return key


def _ensure_writable_static(bundled_static_dir, writable_static_dir):
    """static/ yang ikut ke-bundle di APK cuma bisa dibaca - upload foto
    menu dkk butuh folder yang bisa ditulis, jadi disalin sekali ke
    tempat yang bisa ditulis (folder file privat app), lalu Flask
    diarahkan ke situ (lihat umkm_app.run() di bawah). Kode
    app/blueprints/staff.py yang nyimpen upload TIDAK perlu diubah sama
    sekali - dia cuma tahu "static_folder", tidak peduli itu di mana."""

    if os.path.exists(writable_static_dir):
        return

    shutil.copytree(bundled_static_dir, writable_static_dir)


def run(port, files_dir):
    data_dir = os.path.join(files_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    backup_dir = os.path.join(data_dir, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # WAJIB di-set sebelum "from app import create_app" - config.py baca
    # semuanya ini cuma sekali saat pertama kali di-import.
    os.environ["SECRET_KEY"] = _ensure_secret_key(data_dir)
    os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(data_dir, "umkm.db")
    os.environ["BACKUP_FOLDER"] = backup_dir
    os.environ["BASE_URL"] = "http://127.0.0.1:%d" % port
    os.environ.setdefault("CAFE_NAME", "Toko Saya")

    # "app" (paket kode POS) baru benar-benar ke-extract ke disk oleh
    # Chaquopy begitu DI-IMPORT (lihat extractPackages di build.gradle) -
    # WAJIB import dulu baru boleh baca app.root_path, bukan ditebak dari
    # path file ini sendiri.
    from app import create_app, db
    from app.models import ROLE_OWNER, User

    app = create_app()

    bundled_static_dir = os.path.join(app.root_path, "static")
    writable_static_dir = os.path.join(data_dir, "static")
    _ensure_writable_static(bundled_static_dir, writable_static_dir)
    app.static_folder = writable_static_dir

    with app.app_context():
        if not User.query.first():
            owner = User(username="owner", role=ROLE_OWNER)
            owner.set_password("owner123")
            db.session.add(owner)
            db.session.commit()

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
