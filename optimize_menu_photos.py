"""Kecilkan foto menu yang SUDAH terlanjur terupload (sebelum upload foto
otomatis dikecilkan). Foto dari kamera HP bisa 3-6 MB, padahal halaman menu
untuk tamu memuat banyak foto sekaligus lewat WiFi kafe.

Cara pakai (di folder aplikasi, pakai python yang sama dengan aplikasinya):

    python optimize_menu_photos.py            # CUMA LAPOR - tidak mengubah apa pun
    python optimize_menu_photos.py --apply    # kecilkan beneran

Dengan --apply, file ASLI disalin dulu ke
    <BACKUP_FOLDER>/foto_menu_asli_<tanggal_jam>/
(di luar folder static, supaya backup harian tidak ikut membengkak) - kalau
hasilnya kurang bagus tinggal salin balik, atau hapus foldernya kalau sudah
yakin. Nama file & isi database tidak berubah. Aman dijalankan berulang
kali: foto yang sudah kecil dilewati.

Setelah --apply, Owner bisa klik "Bersihkan Cache" di Pengaturan > Sistem
supaya HP/tablet langsung memuat foto yang baru dikecilkan.
"""

import argparse
import os
import shutil
import sys
import tempfile
from datetime import datetime

from app.imaging import MENU_PHOTO_MAX_SIDE, shrink_photo

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
# JPEG/WEBP itu lossy: menyimpan ulang foto yang resolusinya SUDAH cukup kecil
# menurunkan kualitasnya sedikit demi sedikit tiap skrip dijalankan. Jadi
# foto begitu cuma diproses ulang kalau resolusinya masih di atas batas atau
# ukurannya masih sangat besar. PNG lossless - aman dicoba ulang (hasilnya
# stabil, dan tidak dipakai kalau tidak lebih kecil).
HEAVY_FILE_BYTES = 600 * 1024
PNG_RETRY_BYTES = 200 * 1024


def _needs_shrink(path):
    from PIL import Image

    size = os.path.getsize(path)
    try:
        with Image.open(path) as img:
            if max(img.size) > MENU_PHOTO_MAX_SIDE:
                return True
    except (OSError, ValueError):
        return False

    if path.lower().endswith(".png"):
        return size > PNG_RETRY_BYTES
    return size > HEAVY_FILE_BYTES


def _human(num_bytes):
    return f"{num_bytes / 1024 / 1024:.2f} MB" if num_bytes >= 1024 * 1024 else f"{num_bytes / 1024:.0f} KB"


def run(menu_dir, backup_root, apply=False, out=print):
    """Return (jumlah_file_berubah, byte_sebelum, byte_sesudah)."""

    files = sorted(
        name for name in os.listdir(menu_dir)
        if name.lower().endswith(IMAGE_EXTENSIONS) and os.path.isfile(os.path.join(menu_dir, name))
    )
    candidates = [name for name in files if _needs_shrink(os.path.join(menu_dir, name))]
    out(f"{len(files)} foto menu ditemukan di {menu_dir}; {len(candidates)} perlu dikecilkan.")

    backup_dir = None
    if apply and candidates:
        backup_dir = os.path.join(backup_root, "foto_menu_asli_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(backup_dir, exist_ok=True)

    scratch = tempfile.mkdtemp() if not apply else None
    changed = total_before = total_after = 0

    try:
        for name in candidates:
            source = os.path.join(menu_dir, name)
            if apply:
                backup_copy = os.path.join(backup_dir, name)
                shutil.copy2(source, backup_copy)
                target = source
            else:
                target = os.path.join(scratch, name)
                shutil.copy2(source, target)

            before, after = shrink_photo(target)

            if after < before:
                changed += 1
                total_before += before
                total_after += after
                out(f"  {name:<24} {_human(before):>9} -> {_human(after):>9}")
            elif apply:
                os.remove(backup_copy)  # tidak berubah - tidak perlu salinan asli
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)

    verb = "dikecilkan" if apply else "akan dikecilkan (belum diubah - jalankan lagi dengan --apply)"
    out(f"{changed} foto {verb}: {_human(total_before)} -> {_human(total_after)}"
        f" (hemat {_human(total_before - total_after)}).")

    if apply and backup_dir:
        if changed:
            out(f"File asli disimpan di: {backup_dir}")
        else:
            shutil.rmtree(backup_dir, ignore_errors=True)

    return changed, total_before, total_after


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kecilkan foto menu yang sudah terupload.")
    parser.add_argument("--apply", action="store_true", help="kecilkan beneran (default: cuma lapor)")
    args = parser.parse_args(argv)

    from config import BASE_DIR, Config

    menu_dir = os.path.join(BASE_DIR, "app", "static", "uploads", "menu")
    if not os.path.isdir(menu_dir):
        print(f"Folder foto menu tidak ditemukan: {menu_dir}")
        return 1

    run(menu_dir, Config.BACKUP_FOLDER, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
