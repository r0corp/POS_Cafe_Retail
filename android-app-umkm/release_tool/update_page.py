"""Perbarui halaman unduh (README.md + QR) di repo rilis TANPA membuat rilis baru.

Dipakai terutama untuk memasang link iPhone begitu ada (TestFlight / App Store):

    python release_tool/update_page.py --out "D:/10.  PROJECT/oru-go-releases" \\
        --ios-url https://testflight.apple.com/join/XXXXXXXX --ios-label TestFlight

Hasil: ios.json, ios-qr.png, dan bagian "iPhone / iOS" di README.md. Untuk
menghapus bagian iOS: tambahkan --clear-ios. Sesudahnya commit + push repo rilis.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_release as mr  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="folder repo rilis (hasil git clone)")
    ap.add_argument("--repo", default=mr.DEFAULT_REPO)
    ap.add_argument("--ios-url", help="link unduhan iPhone (TestFlight / App Store), harus https")
    ap.add_argument("--ios-label", default="Unduh untuk iPhone", help="teks tautan di halaman, mis. 'Unduh di TestFlight'")
    ap.add_argument("--ios-note", default="Buka tautan ini di iPhone.", help="keterangan satu-dua kalimat di bawah tautan")
    ap.add_argument("--clear-ios", action="store_true", help="hapus bagian iOS dari halaman")
    args = ap.parse_args()

    ios_path = os.path.join(args.out, mr.IOS_CONFIG)
    if args.clear_ios and os.path.exists(ios_path):
        os.remove(ios_path)
    if args.ios_url:
        if not args.ios_url.startswith("https://"):
            sys.exit("--ios-url harus diawali https://")
        with open(ios_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"url": args.ios_url, "label": args.ios_label, "note": args.ios_note}, f, indent=2, ensure_ascii=False)
            f.write("\n")

    with open(os.path.join(args.out, "version.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    # tanggal rilis dipertahankan dari halaman yang sudah ada (jangan jadi hari ini)
    date = None
    readme = os.path.join(args.out, "README.md")
    if os.path.exists(readme):
        m = re.search(r"&middot; (\d\d-\d\d-\d{4})", open(readme, encoding="utf-8").read())
        date = m.group(1) if m else None

    mr.write_download_page(args.out, manifest, args.repo, date=date)
    ios = mr.read_ios_config(args.out)
    print("halaman diperbarui:", readme)
    print("bagian iOS:", ios["url"] if ios else "(tidak ada)")
    print("Berikutnya di repo rilis: git add -A && git commit && git push")


if __name__ == "__main__":
    main()
