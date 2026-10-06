"""Pengecil foto menu (app/imaging.py) dan skrip optimize_menu_photos.py."""

import os

from PIL import Image

import optimize_menu_photos
from app.imaging import MENU_PHOTO_MAX_SIDE, shrink_photo


def _camera_jpeg(path, size=(2400, 1800), orientation=None):
    img = Image.effect_noise(size, 60).convert("RGB")
    exif = img.getexif()
    if orientation:
        exif[0x0112] = orientation
    img.save(path, "JPEG", quality=95, exif=exif)


def test_large_photo_is_shrunk_with_exif_orientation_applied(tmp_path):
    path = str(tmp_path / "foto.jpg")
    _camera_jpeg(path, (2400, 1800), orientation=6)  # 6 = diputar 90 derajat
    before = os.path.getsize(path)

    old, new = shrink_photo(path)

    assert old == before and new == os.path.getsize(path) and new < before / 5
    with Image.open(path) as img:
        assert img.size == (675, 900)  # jadi portrait, sisi terpanjang 900


def test_small_unreadable_and_animated_files_are_left_alone(tmp_path):
    small = str(tmp_path / "kecil.jpg")
    Image.new("RGB", (300, 200), (200, 50, 50)).save(small, "JPEG", quality=40, optimize=True)
    broken = str(tmp_path / "rusak.jpg")
    with open(broken, "wb") as f:
        f.write(b"bukan gambar")
    frames = [Image.new("RGB", (1500, 1500), c) for c in [(255, 0, 0), (0, 255, 0)]]
    animated = str(tmp_path / "anim.webp")
    frames[0].save(animated, "WEBP", save_all=True, append_images=frames[1:], duration=100, loop=0)

    snapshot = {p: open(p, "rb").read() for p in (small, broken, animated)}
    for path in snapshot:
        before, after = shrink_photo(path)
        assert before == after
        assert open(path, "rb").read() == snapshot[path]

    assert not [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]
    with Image.open(small) as img:
        assert img.size == (300, 200)  # tidak pernah diperbesar


def test_script_reports_by_default_and_backs_up_originals_when_applied(tmp_path):
    menu = tmp_path / "menu"
    menu.mkdir()
    _camera_jpeg(str(menu / "menu-1.jpg"))
    Image.new("RGB", (400, 300), (10, 90, 160)).save(str(menu / "menu-2.jpg"), "JPEG", quality=70)
    (menu / "catatan.txt").write_text("bukan foto")
    original_big = (menu / "menu-1.jpg").read_bytes()
    original_small = (menu / "menu-2.jpg").read_bytes()
    backups = tmp_path / "backups"

    # Default: cuma lapor, tidak ada yang berubah & tidak ada folder backup.
    changed, before, after = optimize_menu_photos.run(str(menu), str(backups), apply=False, out=lambda *_: None)
    assert changed == 1 and after < before
    assert (menu / "menu-1.jpg").read_bytes() == original_big
    assert not backups.exists()

    # --apply: foto besar dikecilkan, aslinya disalin ke folder cadangan.
    changed, _, _ = optimize_menu_photos.run(str(menu), str(backups), apply=True, out=lambda *_: None)
    assert changed == 1
    assert (menu / "menu-1.jpg").stat().st_size < len(original_big) / 5
    assert (menu / "menu-2.jpg").read_bytes() == original_small  # sudah kecil: dilewati
    saved = list(backups.glob("foto_menu_asli_*/menu-1.jpg"))
    assert len(saved) == 1 and saved[0].read_bytes() == original_big
    assert not list(backups.glob("foto_menu_asli_*/menu-2.jpg"))

    # Dijalankan lagi: tidak ada yang perlu dikecilkan & tidak membuat folder cadangan baru.
    changed, _, _ = optimize_menu_photos.run(str(menu), str(backups), apply=True, out=lambda *_: None)
    assert changed == 0
    assert len(list(backups.glob("foto_menu_asli_*"))) == 1
    with Image.open(menu / "menu-1.jpg") as img:
        assert max(img.size) <= MENU_PHOTO_MAX_SIDE
