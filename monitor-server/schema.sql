-- Skema D1 untuk Pantau Aplikasi (Oru POS GO).
-- Hanya status ringan per perangkat; TIDAK ada nama toko, data penjualan, atau lokasi.
CREATE TABLE IF NOT EXISTS devices (
  device     TEXT PRIMARY KEY,   -- Kode Perangkat (16 huruf/angka), sama dengan yang dikirim pelanggan saat aktivasi
  version    TEXT NOT NULL,      -- versi aplikasi, mis. 1.0.6
  mode       TEXT NOT NULL,      -- trial | permanent | rental | expired | unknown
  expiry     TEXT NOT NULL DEFAULT '',  -- YYYYMMDD untuk sewa, kosong bila tidak ada
  platform   TEXT NOT NULL,      -- android | ios
  edition    TEXT NOT NULL DEFAULT 'go',  -- go | cafe (edisi aplikasi); database lama: ALTER TABLE devices ADD COLUMN edition TEXT NOT NULL DEFAULT 'go';
  lang       TEXT NOT NULL DEFAULT 'id',
  first_seen INTEGER NOT NULL,   -- detik epoch
  last_seen  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen);

-- Satu siaran aktif untuk semua pelanggan (diisi penjual lewat aplikasi Oru Go License).
CREATE TABLE IF NOT EXISTS broadcast (
  id      INTEGER PRIMARY KEY CHECK (id = 1),
  msg_id  TEXT NOT NULL,         -- berubah tiap siaran baru; aplikasi menampilkan tiap msg_id sekali
  text    TEXT NOT NULL,
  expires INTEGER NOT NULL       -- detik epoch
);
