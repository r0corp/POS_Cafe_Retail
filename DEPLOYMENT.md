# Deployment Guide — 1 PC/Mini PC Sebagai Server

Panduan ini untuk memindahkan Cafe POS ke 1 PC/mini PC Windows yang
akan dijadikan server, diakses tablet kasir, HP dapur/pelayan, dan
tamu (scan QR di meja) lewat WiFi kafe yang sama.

Asumsi: server pakai Windows, dan aplikasi hanya perlu diakses dari
dalam jaringan WiFi kafe (bukan dari internet). Kalau nanti butuh
diakses dari luar juga, lihat bagian **HTTPS & Akses dari Luar** di
paling bawah.

---

## 1. Siapkan PC/Mini PC Server

- Install **Python 3.10 atau lebih baru** dari https://python.org (saat
  install, centang "Add Python to PATH").
- **Matikan Sleep/Hibernate**: Settings → System → Power → ubah "Sleep"
  jadi "Never". PC ini harus tetap nyala selama jam operasional kafe
  supaya aplikasi selalu bisa diakses.
- **Set IP tetap** untuk PC server, supaya alamatnya tidak berubah-ubah
  (penting — QR code meja mengarah ke IP ini, kalau IP berubah semua QR
  jadi tidak valid):
  - Cara termudah: reservasi IP di router WiFi berdasarkan MAC address
    PC ini (biasanya ada di menu "DHCP Reservation"/"Address Reservation"
    router).
  - Cek IP dan MAC address PC ini dengan `ipconfig /all` di Command
    Prompt.

## 2. Pindahkan Project

Copy seluruh folder project ini ke PC server, misalnya ke
`C:\CafePOS`. **Jangan ikut copy** folder `venv/`, `__pycache__/`,
`instance/` (database lama), `backups/`, dan `app/static/uploads/` /
`app/static/qrcodes/` — biarkan semua ini dibuat baru dan kosong di
server (lihat langkah 4 & 5). Kalau project ini di-clone dari GitHub,
folder-folder tersebut memang sudah tidak ikut ter-commit (lihat
`.gitignore`), jadi otomatis tidak ada.

## 3. Install Dependencies

Buka Command Prompt / PowerShell di folder project (`C:\CafePOS`):

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Konfigurasi `.env`

Buat file `.env` baru di folder project (copy dari `.env.example`,
**jangan copy `.env` dari komputer development** — harus pakai
`SECRET_KEY` baru yang berbeda). Generate `SECRET_KEY` acak:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Isi `.env`:

```
SECRET_KEY=<hasil generate di atas>
CAFE_NAME=Nama Kafe Anda
BASE_URL=http://<ip-pc-server>:8000
```

`BASE_URL` **wajib** diisi dengan IP + port PC server (bukan
`127.0.0.1`) — ini dipakai untuk generate QR code meja supaya
mengarah ke alamat yang benar dan bisa dibuka dari HP tamu.

## 5. Setup Database (sekali saja, saat pertama kali)

Aplikasi ini belum pakai migration (Flask-Migrate terpasang tapi tidak
dipakai) — cukup buat tabel kosong lalu isi lewat aplikasi atau seed
script:

```bash
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all()"
python seed_users.py           # wajib - buat akun login tiap role
python seed_data.py            # opsional - isi contoh menu & meja
```

`seed_users.py` membuat 4 akun awal (`owner`/`kasir`/`dapur`/`pelayan`,
lihat README.md untuk password default) — **segera login sebagai
owner dan ganti semua password lewat menu Kelola User** sebelum kafe
mulai beroperasi.

Setelah itu, lengkapi lewat aplikasi (bukan lewat script):
- Menu **Pengaturan** — nama toko, logo, alamat, kontak, gambar QRIS.
- Menu **Meja** — tambah meja sesuai kondisi kafe (kalau tidak pakai
  `seed_data.py`), tiap meja otomatis dapat QR code sendiri yang siap
  dicetak.
- Menu **Kelola Menu** — isi kategori & item menu beserta foto (kalau
  tidak pakai `seed_data.py`).

## 6. Buka Windows Firewall

Supaya tablet/HP lain di WiFi kafe bisa akses port aplikasi (default
8000):

```powershell
netsh advfirewall firewall add rule name="Cafe POS" dir=in action=allow protocol=TCP localport=8000
```

## 7. Jalankan Sebagai Windows Service (auto-start & auto-restart)

Supaya aplikasi otomatis jalan saat PC nyala/restart, dan tidak perlu
ada yang login terus-terusan di PC tersebut, pakai
[NSSM](https://nssm.cc/download) (Non-Sucking Service Manager):

1. Download NSSM, extract, lalu copy `nssm.exe` (versi 64-bit, di folder
   `win64`) ke `C:\CafePOS\nssm.exe`.
2. Install service (jalankan sebagai Administrator):

```powershell
nssm install CafePOS "C:\CafePOS\venv\Scripts\python.exe" "C:\CafePOS\serve_production.py"
nssm set CafePOS AppDirectory "C:\CafePOS"
nssm set CafePOS Start SERVICE_AUTO_START
nssm start CafePOS
```

3. Cek statusnya: `nssm status CafePOS` (harus `SERVICE_RUNNING`).
   Untuk stop/restart: `nssm stop CafePOS` / `nssm restart CafePOS`.

Kalau tidak mau pakai NSSM, alternatif paling sederhana: buat shortcut
ke `serve_production.py` di folder Startup Windows — tapi ini butuh
ada user yang login ke PC, dan tidak auto-restart kalau aplikasinya
crash.

## 8. Test Akses & Cetak QR Meja

Dari PC server sendiri: `http://localhost:8000`

Dari tablet/HP lain di WiFi yang sama: `http://<ip-pc-server>:8000`
(pakai IP dari langkah 1).

Login sebagai owner, buka menu **Meja**, klik ikon QR di tiap kartu
meja, lalu **Cetak QR untuk Meja** — tempel hasil cetak di meja fisik
supaya tamu bisa langsung scan untuk lihat menu & pesan sendiri.

Untuk tablet kasir/HP dapur/pelayan, buka alamat di atas lewat Chrome
lalu **Add to Home Screen** supaya terasa seperti aplikasi biasa (tanpa
perlu install APK).

## 9. Backup Otomatis ke Lokasi Lain

Aplikasi sudah punya fitur Backup Database (menu **Sistem** → Backup
Database → Buat Backup Baru), tapi file backup-nya tersimpan di folder
`backups/` di PC server yang sama — kalau PC/disk itu rusak, backup
ikut hilang. Sebaiknya jadwalkan salinan otomatis ke lokasi lain
(flashdisk, network drive, atau cloud storage) pakai Task Scheduler,
misalnya script yang menjalankan:

```powershell
robocopy "C:\CafePOS\backups" "\\NAS\backup-cafepos" /MIR
```

dijadwalkan harian di luar jam operasional.

## 10. Update Aplikasi di Kemudian Hari

Kalau ada perubahan kode yang perlu diterapkan ke server (misalnya
`git pull` dari repo, atau copy file yang berubah):

```powershell
nssm stop CafePOS
:: git pull, atau copy file yang berubah ke C:\CafePOS
venv\Scripts\activate
pip install -r requirements.txt   :: kalau ada dependency baru
nssm start CafePOS
```

Kalau ada perubahan pada teks aplikasi (i18n) yang perlu ikut
diterjemahkan ulang, kompilasi dulu sebelum start ulang:

```powershell
pybabel compile -d app\translations
```

---

## HTTPS & Akses dari Luar (opsional)

Kalau nanti aplikasi juga perlu diakses dari luar jaringan WiFi kafe
(misalnya owner mau pantau laporan dari rumah), **jangan** expose port
8000 langsung ke internet. Pasang reverse proxy (IIS dengan URL
Rewrite, atau nginx) di depan waitress: reverse proxy terima koneksi
HTTPS di port 443 dengan sertifikat TLS, lalu diteruskan ke
`localhost:8000`. Ini di luar cakupan panduan ini — tanya lagi kalau
sudah sampai tahap itu.
