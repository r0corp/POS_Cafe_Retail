"""Siapkan rilis Oru POS (edisi GO atau Cafe) untuk repo rilis publik.

Dipakai SETELAH build rilis:  ./gradlew.bat assembleRelease  (GO)  /  ./gradlew.bat assembleRelease -Pedition=cafe  (Cafe).
Skrip ini:
  1. membaca versionCode/versionName dari app/build.gradle,
  2. menyalin APK rilis ke folder repo rilis (GO: apk/oru-go-<versi>.apk, Cafe: apk/oru-pos-cafe-<versi>.apk),
  3. menghitung SHA-256 APK-nya,
  4. menulis manifest yang dibaca aplikasi di HP pelanggan (GO: version.json, Cafe: cafe/version.json),
  5. membuat ulang halaman unduh (README.md + QR) yang memuat kedua edisi.

Contoh:
  python release_tool/make_release.py --notes "Perbaikan kasir QRIS" --out "D:/10.  PROJECT/oru-go-releases"
  python release_tool/make_release.py --edition cafe --notes "Rilis pertama Cafe" --out "D:/10.  PROJECT/oru-go-releases"

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
DEFAULT_CAFE_APK = os.path.join(PROJECT, "app", "build-cafe", "outputs", "apk", "release", "app-release.apk")
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


PAGE_TEMPLATE = """# Oru POS

**Aplikasi kasir (POS) untuk gerobak, warung, dan mini cafe - jalan langsung di HP / tablet Android.**
*Point-of-sale apps for street stalls, small shops, and cafes - running right on your Android phone or tablet.*

{cards}
{info_block}{ios_section}
## Yang didapat / What you get

- Kasir dengan pembayaran **Tunai** dan **QRIS**, struk (printer Bluetooth), dan riwayat transaksi
- Menu & kategori, stok bahan baku, laporan harian / mingguan / bulanan (Excel & PDF)
- Akun staf dengan hak akses berbeda
- Dua bahasa (Indonesia / English), tema terang / gelap
- Data tersimpan di perangkat Anda sendiri, **tanpa langganan server**
- **Coba gratis 7 hari**, lanjut dengan kode aktivasi dari penjual

## Cara pasang / How to install

1. Buka link unduhan di HP Android Anda, lalu unduh file APK. Kalau peramban memperingatkan file APK, pilih **Tetap unduh**.
2. Buka file yang terunduh. Android akan meminta izin **"Instal dari sumber ini"** - izinkan satu kali untuk peramban Anda.
3. Tekan **Instal**, lalu buka aplikasinya. Login awal ada di petunjuk dari penjual.
4. Masa percobaan 7 hari langsung berjalan. Untuk lanjut setelahnya, buka **Aktifkan Lisensi**, kirim **Kode Perangkat** ke penjual, lalu tempel **Kode Aktivasi** yang Anda terima. Kode GO dan kode Cafe berbeda; pastikan penjual membuatkan untuk edisi yang Anda pasang.

Pembaruan aplikasi muncul otomatis di dalam aplikasi (Pengaturan &rarr; Sistem &rarr; Cek Pembaruan). Tidak perlu mengunduh ulang dari sini.

## Buku panduan / User manual

Langkah demi langkah, lengkap dengan gambar, untuk pemilik, kasir, pelayan, dan dapur. *Step-by-step guides with screenshots (Indonesian).*

<div align="center">
<table>
<tr>
<th align="center" width="270">Panduan Oru POS GO</th>
<th align="center" width="270">Panduan Oru POS Cafe</th>
<th align="center" width="270">Panduan Oru POS PRO</th>
</tr>
<tr>
<td align="center"><br><a href="{manual_url}"><b>&#128214; Buka PDF GO</b></a><br><sub>gerobak &amp; warung</sub><br><br></td>
<td align="center"><br><a href="{manual_cafe_url}"><b>&#128214; Buka PDF Cafe</b></a><br><sub>mini cafe: meja, dapur, kasir</sub><br><br></td>
<td align="center">{pro_manual_cell}</td>
</tr>
<tr>
<td align="center"><br><img src="manual-qr.png" width="190" alt="QR buku panduan GO"><br><sub>Scan untuk membuka panduan GO</sub><br><br></td>
<td align="center"><br><img src="manual-cafe-qr.png" width="190" alt="QR buku panduan Cafe"><br><sub>Scan untuk membuka panduan Cafe</sub><br><br></td>
<td align="center">{pro_manual_qr}</td>
</tr>
</table>
</div>

## Keamanan file / File integrity

- GO: SHA-256 `{sha256}`
{cafe_sha_line}
APK ditandatangani **Orulabs** (sidik jari sertifikat SHA-256 `{cert}`). Android hanya mau memperbarui aplikasi ini dengan APK bertanda tangan yang sama.

---
&copy; Orulabs
"""

CARDS_TEMPLATE = """## Pilih edisi / Choose your edition

<div align="center">
<table>
<tr>
<th align="center" width="270">Oru POS GO</th>
<th align="center" width="270">Oru POS Cafe</th>
<th align="center" width="270">Oru POS PRO</th>
</tr>
<tr>
<td align="center" valign="top"><br><b>Gerobak &amp; warung</b><br><br>Satu HP, tanpa meja<br>Pilih menu, tekan Bayar<br><br></td>
<td align="center" valign="top"><br><b>Mini cafe</b><br><br>2-3 HP/tablet satu WiFi<br>Meja, dapur, dan kasir<br><br></td>
<td align="center" valign="top"><br><b>Resto &amp; banyak perangkat</b><br><br>Server mini PC + tablet<br>Dipasang oleh penjual<br><br></td>
</tr>
<tr>
<td align="center"><br><a href="{go_url}"><b>&#11015; Unduh GO</b></a><br><sub>v{go_version} &middot; {go_size} MB</sub><br><br></td>
<td align="center">{cafe_cell}</td>
<td align="center">{pro_cell}</td>
</tr>
<tr>
<td align="center"><br><img src="download-qr.png" width="190" alt="QR download GO"><br><sub>Scan untuk mengunduh</sub><br><br></td>
<td align="center">{cafe_qr}</td>
<td align="center">{pro_qr}</td>
</tr>
</table>
</div>

"""

CAFE_SECTION = """
## Oru POS Cafe &mdash; mini cafe

Meja, layar dapur, sampai 3 pengguna, dan tablet dapur/kasir lain yang tersambung lewat WiFi toko. HP atau tablet kasir menjadi servernya; biarkan aplikasinya terbuka dan tercolok charger.

[![Download Cafe](https://img.shields.io/badge/%E2%AC%87%20Download%20Cafe-v{version}-f97316?style=for-the-badge)]({apk_url})

> **{version}** &middot; {size_mb} MB &middot; Android 7.0+ &middot; {date}

Cafe dan GO adalah aplikasi terpisah; keduanya boleh terpasang di HP yang sama. Kode Aktivasi tidak saling tukar.
"""

# Buku panduan pengguna (PDF) disimpan di repo rilis, folder manual/ (dibuat terpisah, bukan oleh skrip ini).
MANUAL_URL = "https://raw.githubusercontent.com/{repo}/main/manual/Panduan-Oru-POS-GO.pdf"
MANUAL_CAFE_URL = "https://raw.githubusercontent.com/{repo}/main/manual/Panduan-Oru-POS-Cafe.pdf"

# Sidik jari sertifikat penanda tangan rilis (keystore Orulabs) - tampil di halaman unduh.
CERT_SHA256 = "5ed6b68757b0c2092cd75e43bccc89028c58f1d61b203441c0fe75d460eb40aa"


IOS_CONFIG = "ios.json"

IOS_SECTION = """
## iPhone / iOS

**[{label}]({url})**
{note}
"""


def read_ios_config(out_dir):
    """ios.json di repo rilis: {"url": "...", "label": "TestFlight"}. Tidak ada
    file = belum ada versi iPhone, bagian iOS tidak ditampilkan sama sekali."""
    path = os.path.join(out_dir, IOS_CONFIG)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg if cfg.get("url") else None


CONTACT_CONFIG = "contact.json"


def read_contact(out_dir):
    """contact.json di repo rilis: {"whatsapp": "62812...", "text": "pesan awal"}. Tidak ada = tanpa kontak."""
    path = os.path.join(out_dir, CONTACT_CONFIG)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg if cfg.get("whatsapp") else None


def whatsapp_url(contact, text=None):
    from urllib.parse import quote

    url = "https://wa.me/%s" % contact["whatsapp"]
    text = text if text is not None else contact.get("text")
    return url + ("?text=" + quote(text) if text else "")


PRO_MANUAL_TEXT = "Halo, saya ingin meminta buku panduan Oru POS PRO."


CAFE_MANIFEST = os.path.join("cafe", "version.json")


def read_cafe_manifest(out_dir):
    path = os.path.join(out_dir, CAFE_MANIFEST)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _qr(data, path):
    import qrcode

    img = qrcode.QRCode(box_size=10, border=3)
    img.add_data(data)
    img.make(fit=True)
    img.make_image(fill_color="black", back_color="white").save(path)


def write_download_page(out_dir, manifest, repo, date=None, cafe_date=None):
    """README.md di repo rilis = halaman unduh yang dibagikan ke calon customer
    (https://github.com/<repo>) + QR menuju link unduhan langsung. Memuat GO, dan Cafe bila cafe/version.json ada."""
    ios = read_ios_config(out_dir)
    cafe = read_cafe_manifest(out_dir)
    today = datetime.date.today().strftime("%d-%m-%Y")
    cafe_section, cafe_sha_line = "", ""
    cafe_cell = "<br>Segera hadir<br><sub>edisi Cafe</sub><br><br>"
    cafe_qr = "&nbsp;"
    if cafe:
        cafe_cell = '<br><a href="%s"><b>&#11015; Unduh Cafe</b></a><br><sub>v%s &middot; %.0f MB</sub><br><br>' % (
            cafe["apkUrl"], cafe["versionName"], cafe["sizeBytes"] / 1048576.0)
        cafe_qr = '<br><img src="cafe-qr.png" width="190" alt="QR download Cafe"><br><sub>Scan untuk mengunduh</sub><br><br>'
    contact = read_contact(out_dir)
    pro_cell = "<br>Hubungi penjual<br><sub>pemasangan di lokasi</sub><br><br>"
    pro_qr = "&nbsp;"
    if contact:
        pro_cell = ('<br><a href="%s"><b>&#128172; Hubungi penjual</b></a><br><sub>lewat WhatsApp &middot; pemasangan di lokasi</sub><br><br>'
                    % whatsapp_url(contact))
        pro_qr = '<br><img src="wa-qr.png" width="190" alt="QR WhatsApp penjual"><br><sub>Scan untuk chat WhatsApp</sub><br><br>'
    pro_manual_cell = "<br>Diberikan penjual<br><sub>saat pemasangan di lokasi</sub><br><br>"
    pro_manual_qr = "&nbsp;"
    if contact:
        pro_manual_cell = ('<br><a href="%s"><b>&#128196; Minta panduan PRO</b></a><br><sub>kirim permintaan lewat WhatsApp</sub><br><br>'
                           % whatsapp_url(contact, PRO_MANUAL_TEXT))
        pro_manual_qr = ('<br><img src="wa-panduan-pro-qr.png" width="190" alt="QR minta panduan PRO"><br>'
                         '<sub>Scan untuk meminta panduan PRO</sub><br><br>')
    cards = CARDS_TEMPLATE.format(pro_cell=pro_cell, pro_qr=pro_qr, go_url=manifest["apkUrl"], go_version=manifest["versionName"],
                                  go_size="%.0f" % (manifest["sizeBytes"] / 1048576.0), cafe_cell=cafe_cell, cafe_qr=cafe_qr)
    if cafe:
        cafe_section = CAFE_SECTION.format(
            version=cafe["versionName"], apk_url=cafe["apkUrl"], size_mb="%.0f" % (cafe["sizeBytes"] / 1048576.0),
            date=cafe_date or cafe.get("releasedAt") or today)
        cafe_sha_line = "- Cafe: SHA-256 `%s`\n" % cafe["sha256"]
    info_block = "> Android 7.0 ke atas &middot; GO v%s (%s)" % (manifest["versionName"], date or manifest.get("releasedAt") or today)
    if cafe:
        info_block += " &middot; Cafe v%s (%s)" % (cafe["versionName"], cafe_date or cafe.get("releasedAt") or today)
        info_block += ("\n>\n> **Cafe:** HP atau tablet kasir menjadi servernya, jadi biarkan aplikasinya terbuka dan tercolok charger. "
                       "GO dan Cafe adalah aplikasi terpisah (boleh terpasang di HP yang sama); Kode Aktivasi tidak saling tukar.")
    info_block += "\n\n"
    page = PAGE_TEMPLATE.format(
        cards=cards,
        info_block=info_block,
        cafe_section=cafe_section,
        cafe_sha_line=cafe_sha_line,
        ios_section=IOS_SECTION.format(label=ios.get("label", "Unduh untuk iPhone"), url=ios["url"],
                           note=ios.get("note", "Buka tautan ini di iPhone.")) if ios else "",
        version=manifest["versionName"],
        apk_url=manifest["apkUrl"],
        size_mb="%.0f" % (manifest["sizeBytes"] / 1048576.0),
        date=date or manifest.get("releasedAt") or today,
        sha256=manifest["sha256"],
        cert=CERT_SHA256,
        manual_url=MANUAL_URL.format(repo=repo),
        manual_cafe_url=MANUAL_CAFE_URL.format(repo=repo),
        pro_manual_cell=pro_manual_cell,
        pro_manual_qr=pro_manual_qr,
    )
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    try:
        _qr(manifest["apkUrl"], os.path.join(out_dir, "download-qr.png"))
        ios_png = os.path.join(out_dir, "ios-qr.png")          # iPhone: hanya tautan, tanpa QR
        if os.path.exists(ios_png):
            os.remove(ios_png)
        cafe_png = os.path.join(out_dir, "cafe-qr.png")
        if cafe:
            _qr(cafe["apkUrl"], cafe_png)
        elif os.path.exists(cafe_png):
            os.remove(cafe_png)
        _qr(MANUAL_URL.format(repo=repo), os.path.join(out_dir, "manual-qr.png"))
        _qr(MANUAL_CAFE_URL.format(repo=repo), os.path.join(out_dir, "manual-cafe-qr.png"))
        wa_png = os.path.join(out_dir, "wa-qr.png")
        wa_pro_png = os.path.join(out_dir, "wa-panduan-pro-qr.png")
        if contact:
            _qr(whatsapp_url(contact), wa_png)
            _qr(whatsapp_url(contact, PRO_MANUAL_TEXT), wa_pro_png)
        else:
            for stale in (wa_png, wa_pro_png):
                if os.path.exists(stale):
                    os.remove(stale)
    except ImportError:
        print("(qrcode tidak terpasang - QR tidak dibuat; jalankan dengan python venv POS)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edition", choices=["go", "cafe"], default="go", help="edisi yang dirilis (default: go)")
    parser.add_argument("--apk", default=None, help="path APK rilis (default: hasil assembleRelease edisi itu)")
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

    if not args.apk:
        args.apk = DEFAULT_APK if args.edition == "go" else DEFAULT_CAFE_APK
    if not os.path.exists(args.apk):
        sys.exit("APK tidak ditemukan: %s\nJalankan dulu: ./gradlew.bat assembleRelease%s" % (
            args.apk, "" if args.edition == "go" else " -Pedition=cafe"))
    if not os.path.isdir(args.out):
        sys.exit("Folder repo rilis tidak ada: %s" % args.out)

    code, name = read_version()
    apk_name = ("oru-go-%s.apk" if args.edition == "go" else "oru-pos-cafe-%s.apk") % name
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
        "releasedAt": datetime.date.today().strftime("%d-%m-%Y"),
    }
    if args.edition == "go":
        manifest_path = os.path.join(args.out, "version.json")
    else:
        manifest_path = os.path.join(args.out, CAFE_MANIFEST)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    if args.edition == "go":
        write_download_page(args.out, manifest, args.repo)
    else:
        with open(os.path.join(args.out, "version.json"), encoding="utf-8") as f:
            go_manifest = json.load(f)
        write_download_page(args.out, go_manifest, args.repo, cafe_date=manifest["releasedAt"])
    print("APK       :", target)
    print("version   : %s (kode %d)" % (name, code))
    print("SHA-256   :", manifest["sha256"])
    print("manifest  :", manifest_path)
    print("halaman unduh:", os.path.join(args.out, "README.md"), "(+ download-qr.png)")
    print()
    print("Langkah berikutnya (lihat RILIS.md):")
    if args.host == "repo":
        print("  Di folder repo rilis: git add -A && git commit && git push")
        print("  Link untuk calon customer: https://github.com/%s" % args.repo)
    else:
        print("  1. GitHub > %s > Releases > Draft a new release, tag v%s," % (args.repo, name))
        print("     unggah file %s lalu Publish." % apk_name)
        print("  2. Di folder repo rilis: git add version.json && git commit && git push")


if __name__ == "__main__":
    main()
