"""Buat logo per edisi dari logo GO: tulisan "GO" di kotak oranye diganti "CAFE" / "PRO".

Hasil:
  - app/src/main/python/app/static/img/cafe-logo.png          logo navbar/login edisi Cafe
  - app/src/main/res/drawable/ic_launcher_cafe_foreground.png  ikon adaptif Cafe
  - app/src/main/res/mipmap-*/ic_launcher_cafe(.|_round).png   ikon lama (API < 26)
  - (opsional) --promo-dir: logo GO/Cafe/PRO untuk brosur dan materi promosi

Jalankan dari folder android-app-umkm:  python release_tool/make_edition_logos.py [--promo-dir <folder>]
Sumber: ic_launcher_foreground.png, ic_launcher.png, ic_launcher_round.png, go-logo.png (edisi GO, tidak diubah).
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
RES = os.path.join(PROJECT, "app", "src", "main", "res")
IMG = os.path.join(PROJECT, "app", "src", "main", "python", "app", "static", "img")
FONT = "C:/Windows/Fonts/segoeuib.ttf"
DENSITIES = ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")


def _is_orange(px):
    r, g, b = px[0], px[1], px[2]
    return r > 225 and 90 < g < 150 and b < 80


def relabel(src_path, text, out_path):
    """Salin gambar dan ganti tulisan di kotak oranye dengan `text`."""
    im = Image.open(src_path)
    mode = im.mode
    rgba = im.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if p[3] > 200 and _is_orange(p):
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit("kotak oranye tidak ditemukan di %s" % src_path)
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    tile_w, tile_h = x1 - x0 + 1, y1 - y0 + 1
    # warna kotak = rata-rata piksel oranye di tepi dalam (bukan huruf)
    samples = [px[x0 + tile_w // 2, y0 + int(tile_h * 0.08)], px[x0 + int(tile_w * 0.08) + 2, y0 + tile_h // 2]]
    fill = tuple(int(sum(s[i] for s in samples) / len(samples)) for i in range(3)) + (255,)
    # hapus huruf lama: seluruh area dalam kotak (menjauh dari sudut membulat dan garis pemisah)
    inset_x, inset_y = int(tile_w * 0.18), int(tile_h * 0.25)   # jauh dari sudut membulat kanan atas
    draw = ImageDraw.Draw(rgba)
    draw.rectangle([x0 + inset_x, y0 + inset_y, x1 - inset_x, y1 - inset_y], fill=fill)
    # tulis teks baru, ditengahkan
    max_w = tile_w * 0.74 if len(text) > 2 else tile_w * 0.62
    size = int(tile_h * 0.6)
    font = ImageFont.truetype(FONT, size)
    while draw.textlength(text, font=font) > max_w and size > 6:
        size -= 1
        font = ImageFont.truetype(FONT, size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = x0 + (tile_w - tw) / 2 - bbox[0]
    ty = y0 + (tile_h - th) / 2 - bbox[1]
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
    out = rgba if mode == "RGBA" else rgba.convert("RGB")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--promo-dir", help="folder untuk logo GO/Cafe/PRO (materi promosi)")
    args = parser.parse_args()

    # Cafe: aset aplikasi
    relabel(os.path.join(IMG, "go-logo.png"), "CAFE", os.path.join(IMG, "cafe-logo.png"))
    relabel(os.path.join(RES, "drawable", "ic_launcher_foreground.png"), "CAFE",
            os.path.join(RES, "drawable", "ic_launcher_cafe_foreground.png"))
    for d in DENSITIES:
        for suffix in ("", "_round"):
            src = os.path.join(RES, "mipmap-%s" % d, "ic_launcher%s.png" % suffix)
            relabel(src, "CAFE", os.path.join(RES, "mipmap-%s" % d, "ic_launcher_cafe%s.png" % suffix))
    for suffix in ("", "_round"):
        with open(os.path.join(RES, "mipmap-anydpi-v26", "ic_launcher_cafe%s.xml" % suffix), "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                    '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
                    '    <background android:drawable="@android:color/white" />\n'
                    '    <foreground android:drawable="@drawable/ic_launcher_cafe_foreground" />\n'
                    '</adaptive-icon>\n')
    print("aset Cafe dibuat")

    if args.promo_dir:
        os.makedirs(args.promo_dir, exist_ok=True)
        for name, text in (("go", "GO"), ("cafe", "CAFE"), ("pro", "PRO")):
            src = os.path.join(RES, "drawable", "ic_launcher_foreground.png")
            out = os.path.join(args.promo_dir, "logo-oru-pos-%s.png" % name)
            if text == "GO":
                Image.open(src).save(out)
            else:
                relabel(src, text, out)
        print("logo promosi di", args.promo_dir)


if __name__ == "__main__":
    main()
