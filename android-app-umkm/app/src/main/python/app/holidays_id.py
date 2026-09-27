# -*- coding: utf-8 -*-
"""Data hari libur nasional & cuti bersama Indonesia.

PENTING: tanggal cuti bersama & hari raya keagamaan (Idul Fitri, Idul
Adha, Nyepi, Imlek, Waisak, dll) berubah tiap tahun dan baru resmi
ditetapkan pemerintah lewat SKB 3 Menteri (biasanya terbit akhir tahun
sebelumnya). Data di bawah untuk tahun 2026 - perlu diperbarui manual
tiap pergantian tahun begitu SKB tahun berikutnya terbit (aplikasi ini
jalan offline, jadi tidak bisa ambil data ini otomatis dari internet).

type:
  "libur"  = tanggal merah / libur nasional resmi (tidak masuk kerja)
  "cuti"   = cuti bersama (tidak masuk kerja, tapi bukan "tanggal merah")
  "catatan" = hari besar/penanda penting tapi BUKAN hari libur
              (mis. awal Ramadan - relevan buat bisnis F&B walau toko
              tetap buka)
"""

HOLIDAYS_ID = {
    "2026-01-01": {"name": "Tahun Baru Masehi", "type": "libur"},
    "2026-01-16": {"name": "Isra Mikraj Nabi Muhammad SAW", "type": "libur"},
    "2026-02-16": {"name": "Cuti Bersama Tahun Baru Imlek", "type": "cuti"},
    "2026-02-17": {"name": "Tahun Baru Imlek 2577", "type": "libur"},
    "2026-02-19": {"name": "Awal Ramadan 1447 H", "type": "catatan"},
    "2026-03-18": {"name": "Cuti Bersama Hari Suci Nyepi", "type": "cuti"},
    "2026-03-19": {"name": "Hari Suci Nyepi (Tahun Baru Saka 1948)", "type": "libur"},
    "2026-03-20": {"name": "Cuti Bersama Idul Fitri", "type": "cuti"},
    "2026-03-21": {"name": "Hari Raya Idul Fitri 1447 H", "type": "libur"},
    "2026-03-22": {"name": "Hari Raya Idul Fitri 1447 H", "type": "libur"},
    "2026-03-23": {"name": "Cuti Bersama Idul Fitri", "type": "cuti"},
    "2026-03-24": {"name": "Cuti Bersama Idul Fitri", "type": "cuti"},
    "2026-04-03": {"name": "Wafat Isa Almasih", "type": "libur"},
    "2026-04-05": {"name": "Kebangkitan Isa Almasih (Paskah)", "type": "libur"},
    "2026-05-01": {"name": "Hari Buruh Internasional", "type": "libur"},
    "2026-05-14": {"name": "Kenaikan Isa Almasih", "type": "libur"},
    "2026-05-15": {"name": "Cuti Bersama Kenaikan Isa Almasih", "type": "cuti"},
    "2026-05-27": {"name": "Hari Raya Idul Adha 1447 H", "type": "libur"},
    "2026-05-28": {"name": "Cuti Bersama Idul Adha", "type": "cuti"},
    "2026-05-31": {"name": "Hari Raya Waisak 2570", "type": "libur"},
    "2026-06-01": {"name": "Hari Lahir Pancasila", "type": "libur"},
    "2026-06-16": {"name": "Cuti Bersama Tahun Baru Islam", "type": "cuti"},
    "2026-06-17": {"name": "Tahun Baru Islam (1 Muharram 1448 H)", "type": "catatan"},
    "2026-08-17": {"name": "Hari Kemerdekaan RI ke-81", "type": "libur"},
    "2026-08-25": {"name": "Maulid Nabi Muhammad SAW", "type": "libur"},
    "2026-12-24": {"name": "Cuti Bersama Hari Raya Natal", "type": "cuti"},
    "2026-12-25": {"name": "Hari Raya Natal", "type": "libur"},
}
