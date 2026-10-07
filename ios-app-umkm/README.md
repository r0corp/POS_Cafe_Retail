# Uji coba iOS: Oru POS GO di iPhone (spike)

Tujuan: membuktikan kode GO yang **sama** (Flask + SQLite) bisa jalan di dalam app iOS dan tampil
lewat WebView - pola yang sama dengan `MainActivity.java` di Android. **Belum untuk dirilis.**

## Isi folder

| Berkas | Fungsi |
|---|---|
| `pyproject.toml` | Konfigurasi BeeWare/Briefcase (paket Python, bundle `id.orulabs.orupos`, iOS minimum 15.4) |
| `src/orupos/app.py` | Cangkang Toga: menjalankan `umkm_app.run()` di thread latar, lalu membuka WebView ke `127.0.0.1:8731` |
| `src/orupos/ios_support.py` | Pengganti `get_device_id()` yang khusus Android (id acak tersimpan di folder data app) |
| `sync_go.py` | Menyalin kode GO ke `src/orupos/gopos` (tidak ikut git; dibuat ulang tiap build) |
| `ci_pick_simulator.py` | Memilih simulator iPhone untuk CI |
| `ci_smoke.py` | Uji alur kasir otomatis terhadap server di dalam app (18 langkah, hanya pustaka standar; bisa dijalankan lokal juga) |
| `../.github/workflows/ios-spike.yml` | Workflow manual di GitHub Actions (macOS) |

## Cara menjalankan uji coba

1. Push repo ini ke GitHub (workflow sudah ada di `.github/workflows/`).
2. GitHub > **Actions** > **iOS spike (Oru POS GO)** > **Run workflow**.
3. Tunggu sekitar 15-30 menit. Buka run-nya: bagian **Summary** menunjukkan apakah server di dalam app menjawab `/login`; di **Artifacts** (`ios-spike-hasil`) ada `ios-login.png` (tangkapan layar simulator), `login.html`, `create.log`, `build.log`, `app-log.txt`, dan `server_error.txt` bila ada.

Biaya: repo ini saat ini **publik**, jadi menit GitHub Actions (termasuk macOS) gratis. Kalau suatu saat diubah
menjadi private, runner macOS dihitung 10x menit (jatah gratis 2.000 menit per bulan, sekitar 200 menit macOS);
satu run tetap cukup beberapa kali.

## Sudah diuji lokal (Windows)

`briefcase dev` di Windows: server Flask GO hidup di thread latar, WebView memuat halaman login beserta CSS/JS/font.
Artinya cangkang dan kode GO sudah benar; yang belum terbukti hanya **build untuk iOS** (wheel iOS untuk
Pillow/MarkupSafe, kompilasi Xcode, dan perilaku Python di iOS), dan itulah yang diuji workflow di atas.

## Cara membaca hasilnya

| Hasil | Artinya | Langkah berikut |
|---|---|---|
| `create` gagal di pip | Ada paket tanpa wheel iOS (biasanya Pillow/MarkupSafe versi tertentu) | Ubah pin versi di `pyproject.toml` ke yang punya wheel iOS |
| `build` gagal | Masalah Xcode/template | Lihat `build.log` |
| Server tidak menjawab, ada `server_error.txt` | Kode GO butuh modul yang tak ada di iOS | Baca traceback, tambal di `ios_support.py` |
| Server menjawab + `smoke.log` semua OK | **Lolos.** Alur kasir terbukti di iOS (login, menu, pesanan, bayar tunai/QRIS, struk PDF, batal, laporan + Excel/PDF, ganti password, backup) | Lanjut ke daftar di bawah |
| Ada langkah GAGAL di `smoke.log` | Bagian tertentu bermasalah di iOS (mis. PDF/Excel) | Baca baris GAGAL + `app-log.txt` |

## Yang BELUM ada (sengaja, di luar uji coba ini)

- **Cetak struk Bluetooth**: kode printer GO khusus Android (Bluetooth klasik). Di iPhone hanya printer BLE.
  Perlu jalur baru (BLE lewat CoreBluetooth) atau cetak PDF/AirPrint.
- **Pembaruan lewat GitHub**: tidak berlaku di iOS (update lewat App Store/TestFlight).
- **Lisensi**: aturan App Store soal pembukaan fitur dengan kode aktivasi dari luar perlu dicek (risiko ditolak).
- **ID perangkat** memakai id acak, bukan `identifierForVendor`.
- **Ikon, splash, dan tanda tangan** untuk TestFlight/App Store (butuh Apple Developer Program, sekitar $99/tahun).
