"""Pengecil foto menu - dipakai upload foto di Kelola Menu
(blueprints/staff.py:_save_logo) dan skrip optimize_menu_photos.py buat
foto yang SUDAH terlanjur terupload sebelum fitur ini ada. Sengaja tanpa
dependensi ke Flask/aplikasi supaya skrip bisa jalan sendiri."""

import os

MENU_PHOTO_MAX_SIDE = 900


def shrink_photo(path, max_side=MENU_PHOTO_MAX_SIDE):
    """Kecilkan foto (sisi terpanjang max_side px, tidak pernah diperbesar).
    Foto langsung dari kamera HP biasanya 3-6 MB, padahal halaman menu
    memuat banyak foto sekaligus lewat WiFi kafe - berat & lambat di HP
    tamu. Aman kalau gagal: file asli dibiarkan apa adanya (gambar
    rusak/format aneh/animasi), dan hasil yang ternyata tidak lebih kecil
    dari aslinya tidak dipakai. Return (ukuran_sebelum, ukuran_sesudah)
    dalam byte; keduanya sama kalau file tidak berubah."""

    from PIL import Image, ImageOps

    extension = os.path.splitext(path)[1].lower()
    tmp_path = path + ".tmp"
    before = os.path.getsize(path)

    try:
        with Image.open(path) as opened:
            if getattr(opened, "is_animated", False):
                return before, before

            # Foto HP menyimpan orientasi di EXIF - harus dibakar ke piksel
            # dulu, karena simpan ulang membuang EXIF-nya.
            img = ImageOps.exif_transpose(opened)
            img.thumbnail((max_side, max_side), Image.LANCZOS)

            if extension in (".jpg", ".jpeg"):
                img.convert("RGB").save(tmp_path, "JPEG", quality=82, optimize=True, progressive=True)
            elif extension == ".png":
                img.save(tmp_path, "PNG", optimize=True)
            elif extension == ".webp":
                img.save(tmp_path, "WEBP", quality=82)
            else:
                return before, before

        if os.path.getsize(tmp_path) < before:
            os.replace(tmp_path, path)
            return before, os.path.getsize(path)
    except (OSError, ValueError, Image.DecompressionBombError):
        pass
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return before, before
