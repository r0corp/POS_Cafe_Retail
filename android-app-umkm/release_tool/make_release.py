"""Siapkan rilis Oru POS GO untuk repo rilis publik.

Dipakai SETELAH build rilis (./gradlew.bat assembleRelease). Skrip ini:
  1. membaca versionCode/versionName dari app/build.gradle,
  2. menyalin APK rilis ke folder repo rilis dengan nama oru-go-<versi>.apk,
  3. menghitung SHA-256 APK-nya,
  4. menulis version.json (yang dibaca aplikasi GO di HP pelanggan).

Contoh:
  python release_tool/make_release.py --notes "Perbaikan kasir QRIS" --out "D:/10.  PROJECT/oru-go-releases"

Setelah itu (lihat RILIS.md): unggah APK sebagai Release di GitHub dengan tag
v<versionName>, lalu commit + push version.json di repo rilis.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
GRADLE = os.path.join(PROJECT, "app", "build.gradle")
DEFAULT_APK = os.path.join(PROJECT, "app", "build", "outputs", "apk", "release", "app-release.apk")
DEFAULT_REPO = "r0corp/oru-go-releases"


def read_version():
    text = open(GRADLE, encoding="utf-8").read()
    code = re.search(r"versionCode\s+(\d+)", text)
    name = re.search(r'versionName\s+"([^"]+)"', text)
    if not code or not name:
        sys.exit("versionCode/versionName tidak ketemu di app/build.gradle")
    return int(code.group(1)), name.group(1)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


PAGE_TEMPLATE = """# Oru POS GO

**Aplikasi kasir (POS) untuk warung, kedai, dan toko kecil - jalan langsung di HP / tablet Android.**
*Point-of-sale app for small shops and cafes - runs right on your Android phone or tablet.*

[![Download](https://img.shields.io/badge/%E2%AC%87%20Download%20APK-v{version}-f97316?style=for-the-badge)]({apk_url})

> **{version}** &middot; {size_mb} MB &middot; Android 7.0+ &middot; {date}

<p align="center"><img src="download-qr.png" width="220" alt="QR download"><br><sub>Scan untuk mengunduh / Scan to download</sub></p>

## Yang didapat / What you get

- Kasir dengan pembayaran **Tunai** dan **QRIS**, struk (printer Bluetooth), dan riwayat transaksi
- Menu & kategori, stok bahan baku, laporan harian / mingguan / bulanan (Excel & PDF)
- Beberapa akun staf dengan hak akses berbeda
- Dua bahasa (Indonesia / English), tema terang / gelap
- Data tersimpan di perangkat Anda sendiri, **tanpa langganan server**
- **Coba gratis 7 hari**, lanjut dengan kode aktivasi dari penjual

## Cara pasang / How to install

1. Buka link unduhan di HP Android Anda, lalu unduh file APK. Kalau peramban memperingatkan file APK, pilih **Tetap unduh**.
2. Buka file yang terunduh. Android akan meminta izin **"Instal dari sumber ini"** - izinkan satu kali untuk peramban Anda.
3. Tekan **Instal**, lalu buka **Oru POS GO**. Login awal ada di petunjuk dari penjual.
4. Masa percobaan 7 hari langsung berjalan. Untuk lanjut setelahnya, buka **Aktifkan Lisensi**, kirim **Kode Perangkat** ke penjual, lalu tempel **Kode Aktivasi** yang Anda terima.

Pembaruan aplikasi muncul otomatis di dalam aplikasi (Pengaturan &rarr; Sistem &rarr; Cek Pembaruan). Tidak perlu mengunduh ulang dari sini.

## Keamanan file / File integrity

SHA-256 `{sha256}`

APK ini ditandatangani **Orulabs** (sidik jari sertifikat SHA-256 `{cert}`). Android hanya mau memperbarui aplikasi ini dengan APK bertanda tangan yang sama.

---
&copy; Orulabs
"""

# Sidik jari sertifikat penanda tangan rilis (keystore Orulabs) - tampil di halaman unduh.
CERT_SHA256 = "5ed6b68757b0c2092cd75e43bccc89028c58f1d61b203441c0fe75d460eb40aa"


def write_download_page(out_dir, manifest, repo):
    """README.md di repo rilis = halaman unduh yang dibagikan ke calon customer
    (https://github.com/<repo>) + QR menuju link unduhan langsung."""
    page = PAGE_TEMPLATE.format(
        version=manifest["versionName"],
        apk_url=manifest["apkUrl"],
        size_mb="%.0f" % (manifest["sizeBytes"] / 1048576.0),
        date=datetime.date.today().strftime("%d-%m-%Y"),
        sha256=manifest["sha256"],
        cert=CERT_SHA256,
    )
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    try:
        import qrcode
        img = qrcode.QRCode(box_size=10, border=3)
        img.add_data(manifest["apkUrl"])
        img.make(fit=True)
        img.make_image(fill_color="black", back_color="white").save(os.path.join(out_dir, "download-qr.png"))
    except ImportError:
        print("(qrcode tidak terpasang - QR tidak dibuat; jalankan dengan python venv POS)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", default=DEFAULT_APK, help="path APK rilis (default: hasil assembleRelease)")
    parser.add_argument("--out", required=True, help="folder kerja repo rilis (hasil git clone)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/nama repo rilis di GitHub")
    parser.add_argument("--host", choices=["repo", "release"], default="repo",
                        help="tempat APK: 'repo' = file ikut di-commit di repo rilis (APK < 100 MB), "
                             "'release' = diunggah manual sebagai GitHub Release")
    parser.add_argument("--notes", default="", help="catatan perubahan yang tampil di dialog update")
    parser.add_argument("--mandatory", action="store_true", help="wajib update (dialog tidak bisa ditutup)")
    parser.add_argument("--min-supported", type=int, default=0,
                        help="versionCode terendah yang masih boleh jalan; di bawahnya dipaksa update")
    args = parser.parse_args()

    if not os.path.exists(args.apk):
        sys.exit("APK tidak ditemukan: %s\nJalankan dulu: ./gradlew.bat assembleRelease" % args.apk)
    if not os.path.isdir(args.out):
        sys.exit("Folder repo rilis tidak ada: %s" % args.out)

    code, name = read_version()
    apk_name = "oru-go-%s.apk" % name
    release_dir = os.path.join(args.out, "apk")
    os.makedirs(release_dir, exist_ok=True)
    target = os.path.join(release_dir, apk_name)
    shutil.copyfile(args.apk, target)

    if args.host == "repo":
        apk_url = "https://raw.githubusercontent.com/%s/main/apk/%s" % (args.repo, apk_name)
    else:
        apk_url = "https://github.com/%s/releases/download/v%s/%s" % (args.repo, name, apk_name)

    manifest = {
        "versionCode": code,
        "versionName": name,
        "apkUrl": apk_url,
        "sha256": sha256_of(target),
        "sizeBytes": os.path.getsize(target),
        "notes": args.notes,
        "mandatory": args.mandatory,
        "minSupportedVersionCode": args.min_supported,
    }
    manifest_path = os.path.join(args.out, "version.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    write_download_page(args.out, manifest, args.repo)
    print("APK       :", target)
    print("version   : %s (kode %d)" % (name, code))
    print("SHA-256   :", manifest["sha256"])
    print("manifest  :", manifest_path)
    print("halaman unduh:", os.path.join(args.out, "README.md"), "(+ download-qr.png)")
    print()
    print("Langkah berikutnya (lihat RILIS.md):")
    if args.host == "repo":
        print("  Di folder repo rilis: git add version.json README.md download-qr.png apk && git commit && git push")
        print("  Link untuk calon customer: https://github.com/%s" % args.repo)
    else:
        print("  1. GitHub > %s > Releases > Draft a new release, tag v%s," % (args.repo, name))
        print("     unggah file %s lalu Publish." % apk_name)
        print("  2. Di folder repo rilis: git add version.json && git commit && git push")


if __name__ == "__main__":
    main()
