import os
import shutil
import sqlite3
import tempfile
import zipfile


class BackupError(Exception):
    """Berkas backup tidak valid / tidak aman dipulihkan (pesan siap tampil ke pengguna)."""


# Tabel yang HARUS ada di database backup yang sah (nama tabel di app/models.py).
REQUIRED_TABLES = {"users", "settings", "orders", "menu_items"}
_ALLOWED_PREFIXES = ("static/uploads/", "static/qrcodes/")


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


def _normalized(name):
    return name.replace("\\", "/")


def _classify_members(zf):
    """Periksa semua isi zip. Kembalikan (nama_db_di_zip, daftar_nama_static).
    Tolak path berbahaya (zip-slip: '..', path absolut, huruf drive) dan isi di luar
    instance/*.db, static/uploads/, static/qrcodes/."""

    db_members = []
    static_members = []
    for info in zf.infolist():
        name = _normalized(info.filename)
        if name.endswith("/"):
            continue
        parts = name.split("/")
        if name.startswith("/") or ".." in parts or (len(name) > 1 and name[1] == ":"):
            raise BackupError("isi backup mengandung path yang tidak aman")
        if name.startswith("instance/") and name.endswith(".db") and name.count("/") == 1:
            db_members.append(info.filename)
        elif name.startswith(_ALLOWED_PREFIXES):
            static_members.append(info.filename)
        else:
            raise BackupError("isi backup tidak dikenal: %s" % name)
    if len(db_members) != 1:
        raise BackupError("berkas ini bukan backup aplikasi (database tidak ditemukan)")
    return db_members[0], static_members


def _check_database(path):
    """Pastikan file adalah database SQLite yang utuh dan punya tabel inti POS."""
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error as exc:
        raise BackupError("database di dalam backup tidak bisa dibuka (%s)" % exc)
    try:
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.DatabaseError as exc:
            raise BackupError("database di dalam backup rusak (%s)" % exc)
        if not result or result[0] != "ok":
            raise BackupError("database di dalam backup rusak")
        missing = REQUIRED_TABLES - tables
        if missing:
            raise BackupError("database di dalam backup tidak lengkap (tabel %s tidak ada)" % ", ".join(sorted(missing)))
    finally:
        conn.close()


def validate_backup_zip(zip_path):
    """Periksa backup TANPA mengubah apa pun. Raise BackupError dengan pesan yang bisa
    dibaca pengguna bila tidak sah."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            bad = zf.testzip()
            if bad:
                raise BackupError("berkas rusak (%s)" % bad)
            db_member, _static = _classify_members(zf)
            tmp = tempfile.mkdtemp(prefix="validasi_backup_")
            try:
                extracted = zf.extract(db_member, tmp)
                _check_database(extracted)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    except zipfile.BadZipFile:
        raise BackupError("berkas bukan file .zip yang valid")


def restore_backup_zip(zip_path, db_path, static_folder):
    """Pulihkan database + gambar dari backup .zip buatan write_backup_zip().

    Urutan sengaja begini supaya data lama tidak setengah rusak: (1) semua isi
    diperiksa dan diekstrak ke folder sementara (gagal di sini = tidak ada yang
    berubah), (2) database diganti lewat SQLite online backup (salinan halaman
    demi halaman, transaksi - gagal di tengah = database lama tetap utuh),
    (3) baru folder gambar diganti. Pemanggil WAJIB menutup koneksi database
    (db.engine.dispose()) sebelum dan sesudah memanggil fungsi ini, dan
    menjalankan _ensure_schema() sesudahnya (backup lama bisa kekurangan kolom)."""

    with zipfile.ZipFile(zip_path) as zf:
        db_member, static_members = _classify_members(zf)
        tmp = tempfile.mkdtemp(prefix="pulihkan_backup_")
        try:
            extracted_db = zf.extract(db_member, tmp)
            _check_database(extracted_db)
            for name in static_members:
                zf.extract(name, tmp)

            src = sqlite3.connect(extracted_db)
            try:
                dst = sqlite3.connect(db_path, timeout=30)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()

            for sub in ("uploads", "qrcodes"):
                new_dir = os.path.join(tmp, "static", sub)
                target = os.path.join(static_folder, sub)
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
                if os.path.isdir(new_dir):
                    shutil.copytree(new_dir, target, dirs_exist_ok=True)
                else:
                    os.makedirs(target, exist_ok=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
