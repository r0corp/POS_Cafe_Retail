# Rilis & update Oru POS GO

Update APK GO diambil aplikasi dari repo **publik** `r0corp/r0corp-oru-go-releases`
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
3. Siapkan file rilis:
   `python release_tool/make_release.py --notes "Catatan perubahan" --out "D:/10.  PROJECT/r0corp-oru-go-releases"`
   (tambah `--mandatory` kalau semua pelanggan WAJIB update; atau
   `--min-supported <versionCode>` untuk memaksa update di bawah kode tertentu)
4. GitHub -> repo `r0corp-oru-go-releases` -> **Releases -> Draft a new release**:
   tag `v<versionName>`, unggah `apk/oru-go-<versionName>.apk`, **Publish**.
5. Di folder repo rilis: `git add version.json apk` (APK tidak perlu di-commit
   kalau sudah diunggah sebagai Release; lihat `.gitignore` repo rilis),
   `git commit`, `git push`. **Urutan penting: Release dulu, baru push
   `version.json`**, supaya aplikasi tidak menawarkan update yang filenya belum ada.

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
