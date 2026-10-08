# Panduan uji Oru POS Cafe (2 tablet, 1 WiFi)

Tujuan: memastikan mode server-di-tablet bekerja di perangkat asli sebelum Cafe dijual. Sudah diuji di **emulator Android
15 (tablet)**: pemasangan, Dashboard, kartu Hubungkan Perangkat Lain, batas 3 pengguna, dan ketahanan layar-mati (lihat
"Hasil uji emulator" di bawah). Yang belum teruji: dua tablet sungguhan dan WiFi toko. Perkiraan waktu: 30-45 menit.

## Siapkan
- Tablet/HP **A** (kasir, jadi server) dan **B** (dapur). Keduanya di **WiFi yang sama** (bukan data seluler).
- APK uji: `D:\10.  PROJECT\orugo-cafe-uji\oru-pos-cafe-1.0.11-uji.apk` (kirim ke tablet A saja).
- Cafe punya paket sendiri (`id.orulabs.pos.cafe`), jadi **tidak menimpa** Oru POS GO. Boleh terpasang berdampingan.
- Masa percobaan 7 hari berlaku, jadi aktivasi tidak perlu untuk uji ini. (Uji aktivasi ada di bagian 6.)

## 1. Pasang dan buka di tablet A
1. Pasang APK, buka. Login `owner` / `owner123`; aplikasi meminta ganti password. Ganti.
2. Nama di layar harus **Oru POS Cafe**, dan layar **tidak mati sendiri** selama aplikasi terbuka (dibiarkan 2 menit).
3. Dashboard harus menampilkan tombol **Meja, Pesanan, Dapur, Kasir, Menu, Inventory, Pengguna, Laporan, Pengaturan**
   (GO tidak punya Meja/Dapur/Pengguna; Cafe punya semuanya).

## 2. Hubungkan tablet B
1. Di A: **Pengaturan, tab Sistem, kartu "Hubungkan Perangkat Lain"**. Harus tampil alamat `http://192.168.x.x:5100` dan QR.
   (Bila tertulis "belum tersambung ke WiFi", sambungkan A ke WiFi lalu buka ulang halaman.)
2. Di B: buka **Chrome**, ketik alamat itu (atau pindai QR). Halaman login Oru POS harus tampil.
3. Di A: **Pengguna, tambah akun** `dapur1` dengan role **Dapur**. Di B login sebagai `dapur1`.
4. Yang diharapkan: B melihat layar **Dapur** (daftar pesanan kosong).

## 3. Alur pesanan antar tablet
1. Di A: **Pesanan**, pilih menu, buat pesanan **Makan di Tempat** (pilih meja bila ada; buat meja dulu di Pengaturan,
   tab Aplikasi, Meja & Lantai).
2. Di B (Dapur): pesanan muncul **dalam beberapa detik**, dengan bunyi notifikasi bila diaktifkan. Ubah status Diterima
   lalu Dimasak lalu Siap.
3. Di A: **Kasir** menampilkan pesanan; bayar Tunai, lihat struk.
4. Catat: berapa detik jeda pesanan muncul di B? (seharusnya kurang dari 10 detik.)

## 4. Kekuatan koneksi (yang paling mungkin bermasalah)
| Uji | Yang diharapkan |
|---|---|
| Di A, tekan tombol Home (aplikasi ke latar belakang) 1 menit, lalu buka B | B tetap bisa dimuat. Di A muncul notifikasi tetap **"Oru POS Cafe aktif"** (layanan latar depan; di Android 13+ izinkan notifikasinya). |
| Matikan layar A (tombol power) 5 menit | B tetap bisa dimuat (layanan latar depan + wake lock). Bila terputus, catat berapa lama dan merek/versi Android tabletnya. |
| Matikan lalu nyalakan WiFi di A | Alamat IP bisa berubah. Buka lagi kartu "Hubungkan Perangkat Lain" dan catat IP baru. B perlu memakai alamat baru. |
| Router restart | Idem. |
| Bila router menyediakan "reservasi DHCP/IP tetap" untuk A | Setel, ulangi uji di atas: seharusnya alamat tetap sama. |

## 5. Pembatas yang harus ditolak
- Buat akun ke-3 selain owner dan dapur1 (kasir1): berhasil. Akun ke-4: harus **ditolak** dengan pesan batas 3 pengguna aktif.
- Dari perangkat **di luar** WiFi toko (data seluler) buka alamat A: seharusnya tidak bisa terhubung sama sekali.
- Hanya perangkat di jaringan lokal yang dilayani; coba dari tablet C di WiFi tamu bila ada (bisa tersambung bila satu jaringan; ini normal).

## 6. Aktivasi per edisi
1. Di tablet A: **Pengaturan, Sistem, Lisensi**; salin Kode Perangkat.
2. Di **Oru License**: kotak **Kode Cafe**, buat kode untuk perangkat itu (beli putus).
3. Tempel di A. Harus aktif, tulisan TRIAL hilang.
4. Uji silang: buat satu kode di kotak **Kode GO** untuk perangkat yang sama dan tempel di A. Harus **ditolak** dengan pesan
   "Kode ini untuk Oru POS GO, bukan Oru POS Cafe".
5. Cek di **Pantau Aplikasi**: perangkat A tampil dengan label **Cafe**.

## Hasil uji emulator (referensi)
Emulator tablet Android 15 (x86_64), mode Cafe:
- tanpa layanan latar depan: server berhenti menjawab sekitar 1 menit setelah layar mati dan baru pulih saat aplikasi dibuka lagi;
- dengan layanan latar depan (1.0.11): server tetap menjawab 6 menit setelah layar mati, dan juga saat Doze dalam dipaksakan;
- alamat WiFi tampil, server menjawab di alamat itu dari dalam perangkat, akun ke-4 ditolak.
Tablet asli bisa lebih ketat (penghemat baterai pabrikan). Bila terputus di tablet asli: matikan optimasi baterai untuk
aplikasi ini (Pengaturan Android > Aplikasi > Oru POS Cafe > Baterai > Tanpa batasan) dan biarkan tablet kasir tercolok charger.

## Laporkan
Kirim ke saya: hasil tiap bagian (OK / tidak, plus catatan jeda dan perilaku saat layar mati). Bagian 4 yang
paling menentukan apakah layanan latar depan (sudah ada di 1.0.11) cukup di tablet asli, atau perlu penyesuaian per merek.
