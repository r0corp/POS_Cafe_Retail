# Menjalankan Oru POS GO di iPhone sungguhan

Status: **mesin dan alur kasir sudah terbukti di simulator iPhone** (lihat README.md). Yang tersisa untuk
iPhone sungguhan adalah hal-hal yang **hanya bisa dilakukan dengan akun Apple** - bagian kode dan
otomatisasinya sudah disiapkan.

## A. Yang harus Anda siapkan (tidak bisa saya kerjakan)

| # | Langkah | Keterangan |
|---|---|---|
| 1 | Daftar **Apple Developer Program** di developer.apple.com/programs | Sekitar $99 per tahun. Perorangan biasanya aktif dalam 1-2 hari; badan usaha butuh nomor D-U-N-S dan lebih lama. |
| 2 | Di **App Store Connect** buat catatan app baru | Bundle ID: `id.orulabs.orupos`, nama: Oru POS GO, bahasa utama Indonesia. |
| 3 | Buat **sertifikat Apple Distribution** (.p12) | Developer > Certificates. Ekspor dari Keychain Access dengan password (Mac dibutuhkan sekali ini; boleh pinjam/sewa). |
| 4 | Buat **provisioning profile** tipe "App Store" untuk bundle ID di atas | Developer > Profiles. |
| 5 | Buat **API key App Store Connect** (.p8) | App Store Connect > Users and Access > Integrations. Catat Key ID dan Issuer ID. |
| 6 | Isi **secret GitHub** (Settings > Secrets and variables > Actions) | Daftar di bawah. File dikirim sebagai base64: `base64 -i file | pbcopy`. |

Secret yang dibutuhkan workflow `iOS TestFlight (Oru POS GO)`:

| Secret | Isi |
|---|---|
| `APPLE_TEAM_ID` | 10 karakter, ada di Membership details |
| `IOS_CERT_P12_BASE64` / `IOS_CERT_PASSWORD` | sertifikat distribusi (.p12) dan passwordnya |
| `IOS_PROFILE_BASE64` | provisioning profile (.mobileprovision) |
| `ASC_KEY_ID` / `ASC_ISSUER_ID` / `ASC_KEY_P8_BASE64` | API key App Store Connect |

## B. Setelah itu (otomatis)

1. Actions > **iOS TestFlight (Oru POS GO)** > Run workflow. Hasilnya build masuk ke TestFlight (butuh pemrosesan Apple +- 15 menit).
   Workflow ini **draft yang belum pernah dijalankan**; kemungkinan butuh satu-dua perbaikan kecil pada percobaan pertama.
2. App Store Connect > TestFlight > tambahkan penguji (hingga 100 orang internal tanpa review; link publik butuh review ringan).
3. Salin **link TestFlight**, lalu pasang QR di halaman unduh:

        python android-app-umkm/release_tool/update_page.py --out "D:/10.  PROJECT/0_PROJECT_2026/ORUPOS/oru-go-releases" --ios-url https://testflight.apple.com/join/XXXX --ios-label TestFlight

   Commit dan push repo rilis; QR iPhone muncul di halaman unduh.

## C. Sebelum rilis umum di App Store

- **Lisensi / pembayaran**: Apple umumnya mewajibkan In-App Purchase untuk membuka fitur dan melarang membuka fitur
  dengan kode dari luar. Model kode aktivasi via WhatsApp berisiko ditolak. Pilihan: (a) IOS-only lewat TestFlight untuk
  pelanggan terbatas, (b) IAP untuk lisensi (Apple memotong 15-30%), (c) mode gratis dengan batas fitur. Putuskan sebelum review.
  Saya tidak yakin detail kebijakan terbarunya; baca App Store Review Guidelines bagian 3.1 sebelum memutuskan.
- **Privasi**: isi App Privacy di App Store Connect (aplikasi ini tidak mengirim data keluar; semua lokal).
- **Ikon dan layar peluncur**: ikon sudah dibuat dari logo GO. Screenshot App Store (iPhone 6,7" dan 6,5") perlu disiapkan.
- **Cetak struk**: printer Bluetooth klasik tidak didukung iPhone. Sekarang tombol Cetak Struk membuka struk sebagai PDF
  (bagikan / cetak lewat AirPrint). Printer thermal BLE atau AirPrint langsung dari app = pekerjaan lanjutan.
- **Pembaruan**: lewat TestFlight/App Store (pembaruan lewat GitHub tidak berlaku di iOS).

## D. Yang sudah dikerjakan di kode

- Cangkang Toga + WebView yang menjalankan kode GO yang sama (`src/orupos/app.py`).
- ID perangkat memakai `identifierForVendor` (cadangan: id acak) untuk lisensi.
- Jalur cetak iPhone: `_is_ios()` di `staff.py`, daftar printer Bluetooth disembunyikan.
- Ikon app (`src/orupos/resources`) dari logo GO.
- Uji otomatis 20 langkah (`ci_smoke.py --ios`) yang dijalankan di simulator tiap kali workflow uji dipicu.
