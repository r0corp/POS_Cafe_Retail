"""Isi data contoh (kategori, menu, meja) supaya aplikasi langsung bisa
dicoba. Jalankan sekali: python seed_data.py"""

from app import create_app, db
from app.models import Category, MenuItem, Table
from app.blueprints.staff import _generate_table_qr

app = create_app()

with app.app_context():
    if Category.query.first():
        print("Data sudah ada, dilewati.")
    else:
        kopi = Category(name="Kopi & Non-Kopi", order=10)
        berat = Category(name="Makanan Berat", order=20)
        lokal = Category(name="Menu Lokal", order=30)
        luar = Category(name="Menu Kafe/Luar", order=40)

        db.session.add_all([kopi, berat, lokal, luar])
        db.session.flush()

        db.session.add_all([
            MenuItem(name="Kopi Hitam", price=10000, category_id=kopi.id),
            MenuItem(name="Kopi Susu", price=15000, category_id=kopi.id),
            MenuItem(name="Teh Manis", price=8000, category_id=kopi.id),
            MenuItem(name="Nasi Goreng", price=20000, category_id=berat.id),
            MenuItem(name="Mie Ayam", price=18000, category_id=berat.id),
            MenuItem(name="Nasi + Ayam Goreng", price=22000, category_id=lokal.id),
            MenuItem(name="Gorengan (5pcs)", price=10000, category_id=lokal.id),
            MenuItem(name="Pasta Aglio Olio", price=28000, category_id=luar.id),
            MenuItem(name="Roti Bakar", price=15000, category_id=luar.id),
        ])

        tables = [
            Table(label="Meja 1", floor=1, code="l1-01"),
            Table(label="Meja 2", floor=1, code="l1-02"),
            Table(label="Meja 3", floor=2, code="l2-01"),
        ]

        db.session.add_all(tables)
        db.session.commit()

        for table in tables:
            _generate_table_qr(table)

        print("Data contoh berhasil dibuat (3 kategori menu, 9 item, 3 meja + QR).")
