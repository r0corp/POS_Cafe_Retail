import os
import sqlite3
import tempfile
import zipfile


def write_backup_zip(zip_path, db_path, static_folder):
    """Tulis 1 file backup .zip berisi database + folder uploads & qrcodes.
    Dipakai bareng tombol Backup di Pengaturan (staff.backup_create) dan
    script terjadwal backup_now.py.

    Database TIDAK di-copy mentah file-nya - kalau ada transaksi (mis.
    pembayaran) yang commit persis saat file dibaca, hasil copy-nya bisa
    setengah jadi/korup tanpa ketahuan. Pakai SQLite online backup API
    (snapshot konsisten walau aplikasi sedang jalan) ke file sementara,
    baru file itu yang dimasukkan ke zip. Raise FileNotFoundError kalau
    file database-nya tidak ada, supaya tidak pernah ada "backup berhasil"
    yang ternyata kosong tanpa database."""

    if not os.path.isfile(db_path):
        raise FileNotFoundError(db_path)

    fd, snapshot_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        source = sqlite3.connect(db_path)
        try:
            target = sqlite3.connect(snapshot_path)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot_path, arcname=os.path.join("instance", os.path.basename(db_path)))

            uploads_dir = os.path.join(static_folder, "uploads")
            for root, _dirs, files in os.walk(uploads_dir):
                for name in files:
                    full_path = os.path.join(root, name)
                    arcname = os.path.join(
                        "static", "uploads", os.path.relpath(full_path, uploads_dir)
                    )
                    zf.write(full_path, arcname=arcname)

            qrcodes_dir = os.path.join(static_folder, "qrcodes")
            if os.path.isdir(qrcodes_dir):
                for name in os.listdir(qrcodes_dir):
                    full_path = os.path.join(qrcodes_dir, name)
                    if os.path.isfile(full_path):
                        zf.write(full_path, arcname=os.path.join("static", "qrcodes", name))
    except Exception:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise
    finally:
        os.remove(snapshot_path)
