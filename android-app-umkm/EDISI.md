# Edisi Oru POS: GO, Cafe, PRO

Tiga produk untuk tiga jenis usaha. **GO dan Cafe memakai satu basis kode ini** (folder `android-app-umkm`, dibedakan
oleh "edisi" saat build). **PRO adalah aplikasi server terpisah** (folder `app/` di akar repo, untuk mini PC) dan tidak
memakai modul edisi.

| | **GO** | **Cafe** | **PRO** |
|---|---|---|---|
| Untuk | gerobak, warung (tanpa meja) | mini cafe | resto, banyak perangkat |
| Perangkat | 1 HP (Android, iPhone) | 2-3 HP/tablet satu WiFi, Android | mini PC + tablet |
| Alur jual | satu layar: **Bayar** Tunai/QRIS langsung dari layar pesanan | pesanan lalu Kasir | pesanan lalu Kasir |
| Meja, Info WiFi | mati bawaan (bisa dinyalakan di Pengaturan) | nyala bawaan | nyala |
| Layar Dapur | tidak ada | ada | ada |
| Pengguna | 1 (menu Pengguna ada di Pengaturan > Sistem; akun lama tetap jalan) | maks. 3 aktif, termasuk Owner | tanpa batas |
| Server di WiFi toko | tidak (hanya 127.0.0.1) | ya, hanya dari jaringan lokal | ya |
| Kode Aktivasi | rumus asli | rumus + `\|cafe` | - |

Definisi per edisi ada di `app/src/main/python/edition.py` (satu tempat untuk menambah atau mengubah perilaku edisi).

## Membangun

```
# GO (bawaan; hasil di app/build/outputs/apk/release/app-release.apk) - alur rilis di RILIS.md
.\gradlew.bat assembleRelease

# Cafe (hasil di app/build-cafe/outputs/apk/release/app-release.apk)
.\gradlew.bat assembleRelease -Pedition=cafe
```

| | GO | Cafe |
|---|---|---|
| applicationId | `id.orulabs.umkm` | `id.orulabs.pos.cafe` (bisa terpasang bersama GO) |
| Nama di HP | Oru POS GO | Oru POS Cafe |
| Manifest pembaruan | `.../main/version.json` | `.../main/cafe/version.json` |
| APK di repo rilis | `apk/oru-go-<versi>.apk` | `apk/oru-pos-cafe-<versi>.apk` |
| Port lokal | 5000 | 5100 (supaya GO dan Cafe bisa berjalan bersamaan) |
| Layar | normal | dijaga tetap menyala (HP kasir adalah server) |

Keduanya ditandatangani keystore rilis yang sama. versionCode/versionName satu angka untuk dua edisi.

## Lisensi terikat edisi

Kode Aktivasi = tanda tangan RSA atas `device_id|expiry` (GO) atau `device_id|expiry|cafe` (Cafe). Akibatnya:

- kode GO yang sudah beredar tetap sah (rumus GO tidak berubah);
- kode GO tidak bisa mengaktifkan Cafe, dan sebaliknya. Aplikasi menyebutkan edisi kode yang salah itu di layar aktivasi;
- aplikasi **Oru License** punya dua kotak, *Kode GO* dan *Kode Cafe*; riwayat, dasbor, dan CSV mencatat edisinya.

## Cafe: menghubungkan tablet dapur/kasir lain

HP/tablet kasir (yang memasang Cafe) menjadi server. Di **Pengaturan > Sistem > Hubungkan Perangkat Lain** tampil alamat
(`http://<IP WiFi>:5100`) dan QR-nya. Tablet lain di WiFi yang sama membuka alamat itu di browser dan login memakai akun
masing-masing. Server hanya melayani alamat jaringan lokal (privat); permintaan dari alamat publik ditolak.

Batasan yang perlu diingat:

- aplikasi di HP kasir harus tetap terbuka (layar dijaga menyala); jika aplikasi ditutup, tablet lain terputus;
- alamat IP HP kasir bisa berganti jika router memberi alamat baru; atur "IP tetap/reservasi DHCP" di router untuk toko yang
  serius memakainya, atau buka lagi halaman Hubungkan Perangkat Lain untuk melihat alamat terbaru;
- belum ada QR meja untuk tamu pada Cafe versi ini (hanya perangkat staf).

## Pantau

Setiap heartbeat membawa edisi (`e`: `go`/`cafe`; aplikasi lama tanpa `e` dianggap GO). Tampil sebagai label di halaman
Pantau Aplikasi.
