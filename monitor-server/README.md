# Pantau Aplikasi Oru POS GO

Server kecil (Cloudflare Worker + database D1, **paket gratis cukup**) yang menerima status ringan dari aplikasi
Oru POS GO dan ditampilkan di aplikasi **Oru Go License** (menu *Pantau Aplikasi*): siapa yang online, terakhir
aktif kapan, versi berapa, siapa yang belum update, dan sewa mana yang segera habis.

Selama alamat server belum diisi di aplikasi GO (`monitor.py` -> `ENDPOINT` kosong), **tidak ada yang dikirim**
dan kartu pengaturannya tidak tampil di aplikasi pelanggan.

## Data yang dikirim

Per perangkat, sekali tiap ~5 menit selama aplikasi dibuka dan ada internet:

| Field | Isi |
|---|---|
| `d` | Kode Perangkat (16 karakter, sama dengan yang dikirim pelanggan saat minta kode aktivasi) |
| `v` | versi aplikasi |
| `m` | mode lisensi: `trial`, `permanent`, `rental`, `expired` |
| `x` | tanggal berakhir sewa (YYYYMMDD), kosong bila bukan sewa |
| `p` | `android` / `ios` |
| `l` | bahasa |

**Tidak** dikirim: nama toko, data penjualan, menu, pelanggan, lokasi, atau IP yang disimpan. Nama toko di layar
penjual didapat dari riwayat pembuatan kode di HP penjual sendiri (dicocokkan lewat Kode Perangkat).
Pelanggan bisa mematikannya di *Pengaturan > Sistem > Lisensi > Kirim status aktif ke penjual*.
Data perangkat yang tidak aktif lebih dari 180 hari dibuang otomatis.

Perlindungan: kiriman divalidasi ketat (format Kode Perangkat, versi, mode), badan maks 512 byte, kiriman rapat
<60 detik diabaikan, total perangkat dibatasi `MAX_DEVICES` (5000). Membaca daftar wajib token admin.

## Siaran ke pelanggan

Dari menu *Pantau Aplikasi* penjual bisa mengirim satu pesan singkat (maks. 280 karakter, teks biasa, mis. info
update atau pengingat perpanjangan) untuk semua pelanggan, tampil 3 / 7 / 14 / 30 hari. Pesan dititipkan di
jawaban heartbeat, jadi tidak ada koneksi tambahan: muncul sebagai banner di bagian atas halaman pemilik toko saat
aplikasi berikutnya terhubung, sekali per siaran (hilang setelah ditutup, tidak muncul lagi). Siaran baru
menggantikan yang lama; mengirim teks kosong (tombol *Hapus siaran*) menghapusnya. Pelanggan yang mematikan
"Kirim status aktif ke penjual" tidak menerima siaran karena aplikasinya tidak menghubungi server sama sekali.

Perubahan skema: tabel `broadcast` ada di `schema.sql`. Bila Worker sudah terpasang sebelum tabel ini ada, jalankan
ulang `wrangler d1 execute orugo-monitor --remote --file schema.sql` (aman, memakai `IF NOT EXISTS`) lalu `wrangler deploy`.

## Pasang (sekali saja, ~15 menit)

Butuh akun Cloudflare gratis (https://dash.cloudflare.com/sign-up) dan Node.js 18+.

```bash
cd monitor-server
npm install -g wrangler
wrangler login
wrangler d1 create orugo-monitor
```

Salin `database_id` dari hasil perintah terakhir ke `wrangler.toml` (menggantikan `ISI-SETELAH-wrangler-d1-create`).

```bash
wrangler d1 execute orugo-monitor --remote --file schema.sql
wrangler secret put ADMIN_TOKEN
wrangler deploy
```

- `ADMIN_TOKEN`: karangan sendiri, panjang dan acak (mis. 32 karakter). Simpan di password manager; token inilah
  "kunci" untuk melihat daftar perangkat.
- `wrangler deploy` menampilkan alamat seperti `https://orugo-monitor.NAMA-AKUN.workers.dev`.

Cek hidup: buka alamat itu di browser, harus tampil `ok`.

Disarankan: di dashboard Cloudflare > Security > WAF, buat *rate limiting rule* untuk path `/v1/hb`
(mis. 60 permintaan per menit per IP) sebagai lapis tambahan.

## Hubungkan

1. **Aplikasi penjual (Oru Go License)** > *Pantau Aplikasi* > isi alamat Worker dan Token admin. Disimpan lokal
   di HP penjual; tombol *Putuskan sambungan* menghapusnya.
2. **Aplikasi pelanggan (GO):** isi `ENDPOINT` di `android-app-umkm/app/src/main/python/monitor.py` dengan alamat
   Worker, lalu rilis versi GO baru (perangkat lama baru melapor setelah update ke versi itu). Cangkang iPhone
   memakai kode Python yang sama.
3. Bangun ulang APK Oru Go License bila ada perubahan di sisi penjual.

## Tes

```bash
cd monitor-server
node --test test/worker.test.js
```

(Memakai `node:sqlite` bawaan Node 22+; tidak perlu paket tambahan.)
