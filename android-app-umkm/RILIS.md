# Rilis & update Oru POS GO

Update APK GO diambil aplikasi dari repo **publik** `r0corp/oru-go-releases`
(bukan dari repo POS yang private). Aplikasi membaca `version.json`, lalu
mengunduh APK dari GitHub Releases dan memeriksa SHA-256 sebelum memasang.

## Yang HARUS dijaga

- **Keystore rilis** `D:\10.  PROJECT\orugo-keystore\orugo-release.jks` dan
  `keystore.properties` di folder yang sama. Android hanya mau menimpa app
  kalau tanda tangannya sama. **Kalau file ini hilang, semua pelanggan harus
  uninstall dulu (data toko hilang).** Backup di minimal dua tempat terpisah
  (flashdisk + penyimpanan pribadi). Jangan pernah di-commit (sudah di-gitignore).
- `android-app-umkm/keystore.properties` (salinan yang dipakai Gradle) juga
  di-gitignore.

## Langkah rilis versi baru

1. Naikkan `versionCode` (WAJIB lebih besar dari sebelumnya) dan `versionName`
   di `app/build.gradle`.
2. Build rilis yang ditandatangani:
   `./gradlew.bat assembleRelease`
   (hasil: `app/build/outputs/apk/release/app-release.apk`)
3. Siapkan file rilis (APK disimpan langsung di repo rilis):
   `python release_tool/make_release.py --notes "Catatan perubahan" --out "D:/10.  PROJECT/oru-go-releases"`
   (tambah `--mandatory` kalau semua pelanggan WAJIB update; atau
   `--min-supported <versionCode>` untuk memaksa update di bawah kode tertentu)
4. Di folder repo rilis: `git add version.json apk`, `git commit`, `git push`.
   APK dan `version.json` naik dalam satu push, jadi aplikasi tidak pernah
   melihat update yang filenya belum ada.
5. Cek: buka `https://raw.githubusercontent.com/r0corp/oru-go-releases/main/version.json`
   dan link `apkUrl` di dalamnya; ukuran dan SHA-256 harus sama dengan isi manifest.

Batas: GitHub menolak file di atas 100 MB (APK sekarang ±52 MB) dan repo
makin besar tiap versi (±52 MB per rilis). Kalau APK mendekati 100 MB atau
repo sudah ratusan MB, pindah ke GitHub Releases: jalankan skrip dengan
`--host release`, unggah APK sebagai Release (tag `v<versionName>`) dulu,
baru push `version.json`.

## Yang terjadi di HP pelanggan

- Saat aplikasi dibuka (maks. sekali per 6 jam) atau lewat tombol
  **Pengaturan -> Sistem -> Cek Pembaruan**, aplikasi membaca `version.json`.
- Kalau `versionCode` lebih besar: dialog "Pembaruan tersedia". **Nanti** =
  ditanya lagi besok. **Perbarui** = unduh, cek SHA-256, lalu layar instal Android.
- Pertama kali, Android meminta izin "Pasang dari sumber ini" sekali saja.
- Data toko (database) tetap karena yang diganti hanya aplikasinya.

## Tes alur update tanpa menerbitkan apa pun

Build **debug** membaca manifest dari `http://10.0.2.2:8765/version.json`
(= PC pengembang dilihat dari emulator). Jalankan `python -m http.server 8765`
di folder berisi `version.json` + APK uji, buka app di emulator.

## Catatan

- Dependensi Python di `app/build.gradle` (`pip { install ... }`) belum
  dipatok versinya, jadi build di waktu berbeda bisa membawa versi paket
  berbeda. Sebaiknya dipatok sebelum rilis ke banyak pelanggan.
