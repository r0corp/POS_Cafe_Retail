# Cafe POS

Aplikasi POS sederhana untuk kafe/warkop hybrid (order via QR code di
meja + input manual oleh pelayan), dibuat dengan Flask + SQLite.

## Menjalankan (development)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Buat tabel database:

```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
python seed_data.py    # opsional, isi contoh menu & meja
python seed_users.py   # wajib pertama kali, buat akun login tiap role
python run.py
```

Buka `http://127.0.0.1:5000` — akan diarahkan ke halaman login.

**Akun awal** (dari `seed_users.py`, segera ganti passwordnya lewat menu
"User" setelah login sebagai owner):

| Username  | Password    | Role    |
|-----------|-------------|---------|
| owner     | owner123    | Owner   |
| kasir     | kasir123    | Kasir   |
| dapur     | dapur123    | Dapur   |
| pelayan   | pelayan123  | Pelayan |

> Catatan: kalau port 5000 sudah dipakai aplikasi lain di komputer ini,
> set port lain lewat variabel `PORT`, misalnya `set PORT=5051 && python run.py`.

## Alur singkat

- `/t/<kode-meja>` — halaman menu untuk tamu (dibuka lewat scan QR di meja)
- `/` — **Dashboard**, halaman utama setelah login: ringkasan statistik
  hari ini, daftar pesanan aktif, dan kartu menu ke semua fitur
  (menggantikan link navbar — navbar sekarang cuma berisi jam & profil
  pengguna). Kartu menu punya bubble notifikasi mengikuti alur transaksi
  (jumlah meja terisi, pesanan perlu diproses dapur, menunggu bayar).
- `/tables/map` — **Denah Meja**, ala pemilihan kursi bioskop: hijau =
  kosong (klik "Pesan" untuk langsung buat order di meja itu), oranye =
  terisi (info pesanan + link ke Kasir). Meja otomatis kembali kosong
  begitu dibayar lunas. Khusus Owner, halaman ini juga jadi tempat
  kelola meja: tombol "Tambah Meja" dan ikon QR di tiap kartu untuk
  lihat/cetak QR code-nya — tidak perlu halaman terpisah lagi.
- `/orders/new` — input pesanan manual oleh pelayan
- `/kitchen` — antrian dapur, update status pesanan. Ada **notifikasi
  suara otomatis** (2 nada pendek, dibuat langsung lewat Web Audio API
  jadi tidak butuh internet) tiap ada pesanan baru masuk, plus tombol
  mute/unmute di pojok kanan atas (preferensi tersimpan per-device)
- `/cashier` — tandai pesanan sudah dibayar (lanjut otomatis ke struk).
  Sama seperti Dapur, ada **notifikasi suara** tiap pesanan baru
  menunggu pembayaran, plus bagian **"Riwayat Hari Ini"** buat cari transaksi yang sudah
  lunas dan **cetak ulang struknya** — solusi kalau kertas printer
  habis di tengah jalan atau ada yang minta struk lagi. Ada juga tombol
  **"Tampilkan QRIS"** di tiap pesanan yang menampilkan gambar QRIS
  offline toko + total tagihan dalam layar besar, supaya pelayan bisa
  langsung tunjukkan ke tamu untuk di-scan di meja makan (tidak perlu
  tamu jalan ke kasir).
- `/orders/<id>/receipt` — struk siap cetak (logo, alamat, kontak,
  sosial media, nama kasir yang melayani, rincian item)
- `/admin/menu` — kelola menu (khusus Owner). Tiap item menu bisa
  diatur **resep bahan baku**-nya lewat modal foto (klik gambar
  menu → bagian "Resep Bahan Baku") — pilih bahan & jumlah pemakaian
  per porsi.
- `/admin/inventory` — **Inventory Bahan Baku** (khusus Owner): catat
  stok bahan (kopi, susu, gula, dll) beserta satuan & batas stok
  menipis. Begitu ada resep diatur di suatu menu, stok bahan otomatis
  **berkurang tiap ada pesanan masuk** (baik dari kasir/pelayan maupun
  tamu scan-QR) — dan pesanan akan **ditolak dengan pesan jelas** kalau
  stok bahannya tidak cukup. Menu yang bahannya habis otomatis hilang
  dari daftar pesan (tanpa perlu ditandai "Habis" manual).
- `/admin/users` — kelola user & role, dengan indikator **online
  real-time** per akun (update tiap 15 detik), foto profil tiap user
  (klik avatar untuk upload/hapus), dan **log aktivitas login/logout**
  semua akun (khusus Owner)
- Dropdown profil di navbar — khusus Owner, ada ringkasan **"Staf
  Online"** (siapa saja yang sedang aktif) tanpa perlu buka halaman
  Kelola User dulu. Semua user juga bisa **ganti bahasa** (Indonesia
  / English) lewat bendera di dropdown yang sama — pilihan tersimpan
  per-akun di sesi login, seluruh aplikasi (termasuk struk & halaman
  tamu) ikut berubah bahasa.
- `/admin/settings` — nama toko, logo persegi & panjang (dengan pilihan
  logo mana dipakai untuk aplikasi vs struk penjualan), footer, alamat,
  telepon, sosial media (Instagram/TikTok/WhatsApp/lainnya), lebar
  kertas printer thermal (58mm/80mm), gambar QRIS offline toko, dan tab
  **Notifikasi** (aktif/nonaktifkan suara, volume, pilih dari 10 nada
  notifikasi siap coba-dengar) — khusus Owner
- `/reports` — laporan penjualan, dipisah 4 tab (Harian/Mingguan/
  Bulanan/Tahunan), tiap tab ada 4 card ringkasan (total penjualan,
  jumlah transaksi, rata-rata per transaksi, item terjual) plus daftar
  item terlaris di periode itu (khusus Owner)
- `/admin/system` — **Bersihkan Cache** (paksa semua device ambil
  ulang logo/foto/QR terbaru, bukan versi lama yang ke-cache browser)
  dan **Backup Database** (buat/unduh/hapus backup .zip berisi
  database + semua gambar) — khusus Owner

## Hak akses per role

| Role    | Akses |
|---------|-------|
| Owner   | Semua halaman (menu, meja, user, laporan, dll) |
| Kasir   | Dashboard, Denah Meja, Order Baru, Kasir (pembayaran) |
| Dapur   | Dashboard, Denah Meja, Dapur (update status pesanan) |
| Pelayan | Dashboard, Denah Meja, Order Baru |

Semua role bisa lihat Denah Meja (untuk tahu meja mana yang kosong),
tapi cuma Owner yang bisa tambah meja/lihat QR di halaman itu.

Halaman `/t/<kode-meja>` (menu untuk tamu, lewat scan QR) tetap terbuka
tanpa login — hanya halaman staff yang butuh akun.

## Bahasa (i18n)

Aplikasi mendukung Indonesia (default) & English lewat Flask-Babel.
Teks Indonesia di kode adalah sumber asli (`msgid`), terjemahan
Inggris ada di `app/translations/en/LC_MESSAGES/messages.po`. Kalau
menambah teks baru yang perlu ikut diterjemahkan, bungkus dengan
`{{ _('...') }}` di template atau `gettext()`/`lazy_gettext()` di
Python, lalu jalankan:

```bash
pybabel extract -F babel.cfg -k _l -o app/translations/messages.pot .
pybabel update -i app/translations/messages.pot -d app/translations -l en
# isi msgstr yang masih kosong di messages.po, lalu:
pybabel compile -d app/translations
```

## Belum termasuk (sengaja disederhanakan dulu)

- Belum ada proteksi CSRF di form (Flask-WTF) — cukup aman untuk
  jaringan lokal tertutup, tapi bisa ditambah kalau nanti diakses lebih
  luas.
- Cetak struk pakai dialog print browser ke printer thermal yang sudah
  terinstall sebagai printer Windows biasa — bukan integrasi ESC/POS
  level rendah, tapi cukup untuk kebutuhan sekarang.
- Update status pakai auto-refresh sederhana (bukan real-time
  websocket) — cukup untuk skala 1 kafe, lebih gampang di-maintain
  sendiri.

## Deployment (production) & akses dari tablet/HP

Development server (`run.py`) cuma untuk coding di komputer sendiri.
Untuk dipakai sehari-hari (diakses tablet kasir, HP dapur, dan QR
tamu), jalankan lewat `serve_production.py` (pakai `waitress`),
default di port 8000:

```bash
python serve_production.py
```

Panduan lengkap pindah ke 1 PC/mini PC sebagai server — set IP statis,
`.env` production, setup database awal, buka firewall, jalankan
sebagai Windows Service (auto-start & auto-restart), sampai backup
otomatis — ada di **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Aplikasi Android (opsional)

Folder `android-app/` berisi wrapper WebView sederhana supaya staf bisa
buka aplikasi ini lewat ikon di home screen HP/tablet seperti aplikasi
Android biasa (tidak hilang seperti shortcut PWA kalau kena hapus tidak
sengaja). Ini **template** - sebelum build APK untuk toko tertentu, wajib
edit dulu:

- `android-app/app/src/main/res/values/strings.xml` - `server_url`, isi
  alamat IP server toko yang sebenarnya (samakan dengan `BASE_URL` di
  `.env`).
- `android-app/app/src/main/res/xml/network_security_config.xml` - IP di
  situ juga harus sama persis dengan `server_url` di atas.
- (Opsional) ganti ikon di `android-app/app/src/main/res/mipmap-*/` dan
  `drawable/ic_launcher_foreground.png` dengan logo toko yang bersangkutan.

Build APK debug (butuh JDK 17 + Android SDK terpasang):

```bash
cd android-app
.\gradlew.bat assembleDebug
```

Hasilnya ada di `android-app/app/build/outputs/apk/debug/app-debug.apk`.

## Lisensi

Proprietary — hak cipta dilindungi. Lihat [LICENSE](LICENSE).
