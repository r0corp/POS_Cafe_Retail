"""Backup database + file upload/QR code ke .zip, tanpa perlu buka
aplikasi/login - dipakai Task Scheduler buat backup otomatis harian.

Logikanya sama persis dengan tombol "Buat Backup" di halaman Sistem
(app/blueprints/staff.py:backup_create), cuma dijalankan lewat command
line supaya bisa dijadwalkan.

Cara pakai manual:
    python backup_now.py

Retensi: backup yang lebih tua dari BACKUP_RETENTION_DAYS otomatis
dihapus tiap kali skrip ini jalan, supaya folder backups/ tidak
membengkak tanpa batas kalau dijadwalkan harian terus-menerus.
"""

import os
import time
from datetime import datetime

from app import create_app, db
from app.backup import write_backup_zip

BACKUP_RETENTION_DAYS = 30


def run_backup():
    app = create_app()

    with app.app_context():
        backup_folder = app.config["BACKUP_FOLDER"]
        os.makedirs(backup_folder, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cafepos_backup_{timestamp}.zip"
        zip_path = os.path.join(backup_folder, filename)

        write_backup_zip(zip_path, db.engine.url.database, app.static_folder)

        print(f"Backup dibuat: {zip_path}")

        cutoff = time.time() - BACKUP_RETENTION_DAYS * 86400
        removed = 0
        for name in os.listdir(backup_folder):
            if not name.startswith("cafepos_backup_") or not name.endswith(".zip"):
                continue
            path = os.path.join(backup_folder, name)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1

        if removed:
            print(f"Backup lama dihapus (lebih dari {BACKUP_RETENTION_DAYS} hari): {removed} file")


if __name__ == "__main__":
    run_backup()
