"""Siapkan rilis Oru POS GO untuk repo rilis publik.

Dipakai SETELAH build rilis (./gradlew.bat assembleRelease). Skrip ini:
  1. membaca versionCode/versionName dari app/build.gradle,
  2. menyalin APK rilis ke folder repo rilis dengan nama oru-go-<versi>.apk,
  3. menghitung SHA-256 APK-nya,
  4. menulis version.json (yang dibaca aplikasi GO di HP pelanggan).

Contoh:
  python release_tool/make_release.py --notes "Perbaikan kasir QRIS" --out "D:/10.  PROJECT/r0corp-oru-go-releases"

Setelah itu (lihat RILIS.md): unggah APK sebagai Release di GitHub dengan tag
v<versionName>, lalu commit + push version.json di repo rilis.
"""

import argparse
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
DEFAULT_REPO = "r0corp/r0corp-oru-go-releases"


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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apk", default=DEFAULT_APK, help="path APK rilis (default: hasil assembleRelease)")
    parser.add_argument("--out", required=True, help="folder kerja repo rilis (hasil git clone)")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/nama repo rilis di GitHub")
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

    manifest = {
        "versionCode": code,
        "versionName": name,
        "apkUrl": "https://github.com/%s/releases/download/v%s/%s" % (args.repo, name, apk_name),
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

    print("APK       :", target)
    print("version   : %s (kode %d)" % (name, code))
    print("SHA-256   :", manifest["sha256"])
    print("manifest  :", manifest_path)
    print()
    print("Langkah berikutnya (lihat RILIS.md):")
    print("  1. GitHub > %s > Releases > Draft a new release, tag v%s," % (args.repo, name))
    print("     unggah file %s lalu Publish." % apk_name)
    print("  2. Di folder repo rilis: git add version.json && git commit && git push")


if __name__ == "__main__":
    main()
