# Panduan Setup Cafe POS di Lokasi

Panduan ini untuk orang yang akan memasang & menjalankan aplikasi ini
di komputer server café, langkah demi langkah dari nol sampai siap
dipakai kasir/dapur/pelayan sehari-hari.

---

## Yang Perlu Disiapkan Dulu

- 1 unit komputer/laptop (Windows) yang akan jadi **server** — nyala
  terus selama café buka, taruh di tempat aman (misal dekat kasir)
- 2 unit router WiFi (1 untuk lantai 1, 1 untuk lantai 2)
- 1 tablet untuk kasir
- 1 HP (atau tablet lagi) untuk dapur/pelayan, opsional tapi disarankan
- 1 printer thermal, sudah terinstall sebagai printer biasa di Windows
  (ikuti panduan driver dari merek printernya)

---

## 1. Siapkan Jaringan WiFi

- Router di **lantai 1** disetel sebagai router utama (mode biasa)
- Router di **lantai 2** disetel sebagai **Access Point (AP mode)**,
  bukan router terpisah — supaya jadi 1 jaringan yang sama
- Pakai **nama WiFi (SSID) & password yang sama** di kedua unit
- Cek IP komputer server nanti di langkah 4 (`ipconfig` di Command
  Prompt), lalu **reservasi IP itu** di pengaturan router supaya
  alamatnya tidak berubah-ubah

## 2. Pindahkan Aplikasi ke Komputer Server

Copy seluruh folder project ini ke komputer server, misalnya ke
`C:\CafePOS`. **Jangan ikut copy** folder `venv\`, `__pycache__\`, dan
file `instance\cafe.db` (biarkan dibuat baru & kosong di server).

## 3. Install Python & Dependencies

Install **Python 3.10+** dari https://python.org (saat install, centang
"Add Python to PATH"). Lalu buka Command Prompt di folder project:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Konfigurasi `.env`

```bash
copy .env.example .env
```

Buka file `.env` pakai Notepad, isi:

```
SECRET_KEY=<generate acak, lihat perintah di bawah>
CAFE_NAME=Nama Kafe Anda
BASE_URL=http://<ip-komputer-server>:8000
```

Generate `SECRET_KEY` acak:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Cek IP komputer server dengan `ipconfig` (lihat baris "IPv4 Address").
`BASE_URL` ini penting — dipakai untuk generate QR code meja, jadi
harus alamat yang bisa diakses tablet/HP lain, bukan `127.0.0.1`.

## 5. Setup Database (sekali saja, saat pertama kali)

```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
python seed_users.py
```

`seed_users.py` membuat 4 akun awal (satu per role) — **catat lalu
segera ganti password masing-masing** setelah login pertama kali
(lihat langkah 8):

| Username | Password | Role |
|---|---|---|
| owner | owner123 | Owner |
| kasir | kasir123 | Kasir |
| dapur | dapur123 | Dapur |
| pelayan | pelayan123 | Pelayan |

## 6. Buka Windows Firewall

Supaya tablet/HP lain di jaringan bisa akses (jalankan PowerShell
sebagai Administrator):

```powershell
netsh advfirewall firewall add rule name="Cafe POS" dir=in action=allow protocol=TCP localport=8000
```

## 7. Jalankan Aplikasi

```bash
python serve_production.py
```

Biarkan jendela Command Prompt ini tetap terbuka selama café buka.
Kalau mau otomatis jalan tiap komputer nyala/restart (tidak perlu ada
yang login terus-terusan), pasang sebagai Windows Service pakai
[NSSM](https://nssm.cc/download) — caranya sama seperti panduan
`DEPLOYMENT.md` di project asset-tracker, tinggal ganti target ke
`serve_production.py` folder ini.

## 8. Setup Pertama Kali (login sebagai Owner)

1. Di komputer server (atau tablet), buka `http://<ip-server>:8000`
2. Login pakai `owner` / `owner123`
3. Buka menu **User** → ganti password akun `owner`, `kasir`, `dapur`,
   `pelayan` satu-satu (atau buat akun baru dengan nama staf asli,
   lalu nonaktifkan akun contoh yang lama)
4. Buka menu **Pengaturan** → isi nama toko, upload logo, alamat,
   nomor telepon, sosial media, dan gambar QRIS toko
5. Buka menu **Menu** → hapus/ganti menu contoh dengan menu asli café
6. Buka menu **Denah Meja** → hapus meja contoh, tambah meja sesuai
   jumlah meja asli (tiap meja otomatis dapat QR code sendiri)
7. **Cetak QR code tiap meja** — klik ikon QR di kartu meja → klik
   "Cetak QR untuk Meja" → tombol "Cetak" di halaman yang terbuka,
   lalu tempel hasil cetaknya di meja fisik masing-masing

## 9. Akses dari Tablet & HP Staf

Di tablet/HP, buka Chrome → ketik `http://<ip-server>:8000` → login
pakai akun masing-masing role. Supaya terasa seperti aplikasi biasa
(bukan buka website tiap kali): tekan menu (⋮) di Chrome → **"Add to
Home Screen"**, nanti muncul ikon di layar utama.

## 10. Alur Kerja Harian (ringkas)

- **Pelayan/Kasir**: input pesanan manual lewat menu "Order Baru",
  atau tamu pesan sendiri dengan scan QR di meja
- **Dapur**: pantau menu "Dapur", update status pesanan (Diproses →
  Siap → Diantar)
- **Kasir**: pantau menu "Kasir", tandai lunas begitu tamu bayar
  (cash/QRIS), struk otomatis tampil untuk dicetak
- **Owner**: pantau semuanya lewat Dashboard, cek "Laporan" kapan saja

---

## Kalau Ada Masalah

- **Lupa password**: Owner bisa buat/reset lewat menu User → Tambah
  User, atau nonaktifkan akun lama dan buat baru
- **QR meja tidak bisa dibuka tamu**: cek `BASE_URL` di `.env` sudah
  benar (bukan `127.0.0.1`), dan tamu terhubung ke WiFi café yang sama
- **Tablet tidak bisa akses sama sekali**: cek Windows Firewall
  (langkah 6) dan pastikan tablet & server di jaringan WiFi yang sama
- **Server mati/restart, aplikasi berhenti**: kalau belum pasang
  sebagai Windows Service (NSSM), jalankan ulang manual dengan
  `python serve_production.py`
