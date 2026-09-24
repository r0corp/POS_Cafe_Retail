# Test otomatis

Cakupan saat ini: logika yang menyangkut uang & stok (paling berisiko
kalau ada regresi tanpa disadari) - PPN, potong/kembalikan stok bahan
baku, pembuatan pesanan (3 jenis: dine-in/takeaway/ojol), dan
pembayaran (kembalian, snapshot PPN, penjaga bayar-dobel).

## Jalankan

```bash
pip install -r requirements-dev.txt
pytest
```

Tiap test pakai database SQLite sementara sendiri-sendiri (dibuat &
dihapus otomatis per test) - **tidak pernah menyentuh** `instance/cafe.db`
yang asli, aman dijalankan kapan saja termasuk di PC yang sedang
menjalankan aplikasi produksi.

## Sebelum push perubahan ke logika pesanan/pembayaran/stok

Jalankan `pytest` dulu - kalau ada yang merah, cek apakah perubahan
barusan memang sengaja mengubah perilaku itu (update test-nya) atau
tidak sengaja merusak sesuatu yang sudah benar (perbaiki kodenya).

## Nambah test baru

Pakai fixture yang sudah ada di `conftest.py` (`make_menu_item`,
`make_ingredient`, `make_table`, `owner_user`/`kasir_user`, `login()`)
supaya tidak perlu tulis ulang boilerplate bikin data uji.
