"""Pulihkan (restore) backup: data kembali, backup rusak/berbahaya ditolak, hanya Owner."""

import io
import os
import sqlite3
import zipfile

import pytest

from app.backup import BackupError, validate_backup_zip, write_backup_zip
from app.models import ROLE_KASIR, Category, MenuItem, User

from .conftest import login


def _db_path(app):
    from app import db

    with app.app_context():
        return db.engine.url.database


def _make_backup(app, folder):
    from app import db

    path = os.path.join(folder, "uji.zip")
    with app.app_context():
        db.session.remove()
        write_backup_zip(path, db.engine.url.database, app.static_folder)
    return path


@pytest.fixture
def backup_folder(app, tmp_path):
    app.config["BACKUP_FOLDER"] = str(tmp_path)
    return tmp_path


def _menu_names(app):
    with app.app_context():
        return sorted(m.name for m in MenuItem.query.all())


def test_restore_brings_back_old_data(client, app, owner_user, db, backup_folder, make_menu_item):
    make_menu_item(name="Kopi Lama", price=10000)
    zip_path = _make_backup(app, str(backup_folder))

    login(client, "owner")
    # data berubah setelah backup
    make_menu_item(name="Menu Baru", price=5000)
    assert "Menu Baru" in _menu_names(app)

    with open(zip_path, "rb") as f:
        resp = client.post(
            "/admin/system/backup/restore-upload",
            data={"backup_file": (f, "uji.zip")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
    assert b"berhasil dipulihkan" in resp.data
    names = _menu_names(app)
    assert "Kopi Lama" in names
    assert "Menu Baru" not in names
    # semua pengguna dikeluarkan setelah restore
    assert b"login" in client.get("/admin/menu").data.lower() or client.get("/admin/menu").status_code == 302
    # salinan pengaman data sebelum restore dibuat
    assert any(n.startswith("sebelum_restore_") for n in os.listdir(backup_folder))


def test_restore_from_listed_backup(client, app, owner_user, db, backup_folder, make_menu_item):
    make_menu_item(name="Isi Awal", price=1000)
    login(client, "owner")
    client.post("/admin/system/backup/create")
    name = next(n for n in os.listdir(backup_folder) if n.startswith("cafepos_backup_"))
    make_menu_item(name="Tambahan", price=2000)

    resp = client.post("/admin/system/backup/restore/" + name, follow_redirects=True)
    assert b"berhasil dipulihkan" in resp.data
    assert "Tambahan" not in _menu_names(app)
    assert "Isi Awal" in _menu_names(app)


def test_restore_replaces_uploaded_images(client, app, owner_user, db, backup_folder, make_menu_item):
    uploads = os.path.join(app.static_folder, "uploads", "menu")
    os.makedirs(uploads, exist_ok=True)
    marker = os.path.join(uploads, "uji_pulihkan.txt")
    open(marker, "w").write("asli")
    try:
        zip_path = _make_backup(app, str(backup_folder))
        os.remove(marker)
        extra = os.path.join(uploads, "tidak_ada_di_backup.txt")
        open(extra, "w").write("x")

        login(client, "owner")
        with open(zip_path, "rb") as f:
            client.post("/admin/system/backup/restore-upload", data={"backup_file": (f, "uji.zip")},
                        content_type="multipart/form-data")
        assert os.path.exists(marker) and open(marker).read() == "asli"
        assert not os.path.exists(extra)
    finally:
        for name in ("uji_pulihkan.txt", "tidak_ada_di_backup.txt"):
            p = os.path.join(uploads, name)
            if os.path.exists(p):
                os.remove(p)


@pytest.mark.parametrize("payload, message", [
    (b"ini bukan zip", b"bukan file .zip"),
])
def test_rejects_non_zip(client, app, owner_user, backup_folder, payload, message):
    login(client, "owner")
    resp = client.post("/admin/system/backup/restore-upload",
                       data={"backup_file": (io.BytesIO(payload), "rusak.zip")},
                       content_type="multipart/form-data", follow_redirects=True)
    assert message in resp.data


def _zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


def test_rejects_zip_slip_and_unknown_paths(client, app, owner_user, backup_folder):
    login(client, "owner")
    for entries in ({"../evil.txt": "x", "instance/a.db": "x"}, {"instance/a.db": "x", "lain/file.txt": "x"}):
        resp = client.post("/admin/system/backup/restore-upload",
                           data={"backup_file": (_zip_bytes(entries), "x.zip")},
                           content_type="multipart/form-data", follow_redirects=True)
        assert b"tidak bisa dipulihkan" in resp.data


def test_rejects_zip_without_database_or_with_foreign_database(client, app, owner_user, backup_folder, tmp_path):
    login(client, "owner")
    resp = client.post("/admin/system/backup/restore-upload",
                       data={"backup_file": (_zip_bytes({"static/uploads/a.txt": "x"}), "x.zip")},
                       content_type="multipart/form-data", follow_redirects=True)
    assert b"database tidak ditemukan" in resp.data

    foreign = tmp_path / "lain.db"
    conn = sqlite3.connect(foreign)
    conn.execute("CREATE TABLE sesuatu (id INTEGER)")
    conn.commit()
    conn.close()
    resp = client.post("/admin/system/backup/restore-upload",
                       data={"backup_file": (_zip_bytes({"instance/lain.db": foreign.read_bytes()}), "x.zip")},
                       content_type="multipart/form-data", follow_redirects=True)
    assert b"tidak lengkap" in resp.data


def test_failed_restore_leaves_data_untouched(client, app, owner_user, db, backup_folder, make_menu_item):
    make_menu_item(name="Aman", price=1)
    login(client, "owner")
    client.post("/admin/system/backup/restore-upload",
                data={"backup_file": (io.BytesIO(b"bukan zip"), "x.zip")}, content_type="multipart/form-data")
    assert "Aman" in _menu_names(app)
    # masih login karena pemulihan tidak pernah dimulai
    assert client.get("/admin/menu").status_code == 200


def test_only_owner_can_restore(client, app, kasir_user, backup_folder):
    login(client, "kasir")
    resp = client.post("/admin/system/backup/restore-upload",
                       data={"backup_file": (io.BytesIO(b"x"), "x.zip")}, content_type="multipart/form-data")
    assert resp.status_code in (302, 403)
    resp = client.post("/admin/system/backup/restore/apa.zip")
    assert resp.status_code in (302, 403)


def test_big_upload_allowed_only_on_restore_path(client, app, owner_user, backup_folder):
    # batas 16 MB tetap berlaku di halaman lain
    assert app.config["MAX_CONTENT_LENGTH"] == 16 * 1024 * 1024
    from app import RESTORE_UPLOAD_LIMIT

    assert RESTORE_UPLOAD_LIMIT > app.config["MAX_CONTENT_LENGTH"]
