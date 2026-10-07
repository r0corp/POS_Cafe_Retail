# Memasang Oru POS GO di iPhone (tanpa App Store)

> **Status: uji coba.** Belum ada di App Store/TestFlight (butuh akun Apple Developer berbayar).
> Sementara itu aplikasi tersedia sebagai file `.ipa` yang **ditandatangani sendiri oleh pemakai**
> dengan Apple ID gratis. Cara ini cocok untuk mencoba atau demo, **bukan untuk pelanggan awam**.

## Unduh

Ambil `oru-go-ios-unsigned.ipa` dari
[Releases](https://github.com/r0corp/POS_Cafe_Retail/releases/tag/ios-latest) (build otomatis dari kode di repo ini).

## Pasang (dengan komputer)

Butuh: iPhone, kabel, komputer Windows atau Mac, dan **Apple ID** (gratis).

**Pilihan A - Sideloadly** (paling mudah, Windows/Mac)
1. Pasang Sideloadly (sideloadly.io) dan iTunes/Apple Devices di komputer.
2. Sambungkan iPhone, buka Sideloadly, seret file `.ipa` ke dalamnya, isi Apple ID, klik **Start**.
3. Di iPhone: **Pengaturan > Umum > VPN & Manajemen Perangkat**, percayai profil Apple ID Anda.
4. iOS 16 ke atas: aktifkan **Pengaturan > Privasi & Keamanan > Mode Pengembang**, lalu restart iPhone.
5. Buka **Oru POS GO**.

**Pilihan B - AltStore** (bisa memperpanjang otomatis lewat Wi-Fi)
1. Pasang AltServer di komputer dan AltStore di iPhone (altstore.io).
2. Di AltStore buka tab **My Apps**, tekan **+**, pilih file `.ipa`.

## Batasan penting

- **Berlaku 7 hari** untuk Apple ID gratis. Setelah itu app berhenti membuka sampai ditandatangani ulang
  (AltStore bisa memperpanjang otomatis selama iPhone dan komputer tersambung). Data di dalam app tetap ada.
- Maksimal 3 app pribadi dengan Apple ID gratis, dan ada batas pendaftaran app per minggu.
- Tidak ada pembaruan otomatis: unduh `.ipa` terbaru lalu pasang ulang (data tetap).
- Cetak struk: tombol **Cetak Struk** membuka PDF (bagikan atau AirPrint). Printer Bluetooth klasik tidak didukung iPhone.
- Lisensi: Kode Perangkat tampil di **Pengaturan > Sistem** seperti di Android; penjual membuat Kode Aktivasi seperti biasa.

## Untuk pelanggan umum

Gunakan jalur resmi: **TestFlight/App Store** (butuh Apple Developer Program, sekitar $99 per tahun).
Langkahnya ada di [IOS-SETUP.md](IOS-SETUP.md).
