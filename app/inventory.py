from flask_babel import gettext as _

from . import db
from .models import Ingredient, MenuItemIngredient


def check_and_deduct_stock(order):
    """Cek stok bahan baku cukup untuk semua item di satu order (belum
    di-commit), lalu kurangi stoknya kalau cukup. Dipanggil bareng oleh
    staff.new_order() dan public.submit_order() sebelum order disimpan.

    Return None kalau berhasil (stok sudah dikurangi, siap di-commit),
    atau pesan error (string) kalau ada bahan yang tidak cukup - dalam
    kasus itu TIDAK ada stok yang dikurangi (semua bahan dicek dulu
    sebelum ada yang benar-benar dipotong).

    Deduksi dilakukan lewat UPDATE ... WHERE stock_quantity >= qty
    (bukan baca-lalu-tulis di Python) supaya 2 pesanan yang submit nyaris
    bersamaan (mis. tamu double-tap tombol submit di koneksi lambat) tidak
    bisa berdua lolos cek stok berdasarkan angka lama yang sama - baris
    kedua yang UPDATE-nya tidak match (rowcount 0) dianggap gagal dan
    seluruh transaksi di-rollback oleh pemanggil."""

    required = {}

    for item in order.items:
        if not item.menu_item_id:
            continue

        recipe_rows = MenuItemIngredient.query.filter_by(menu_item_id=item.menu_item_id).all()

        for row in recipe_rows:
            entry = required.setdefault(
                row.ingredient_id,
                {"ingredient": row.ingredient, "qty": 0.0, "menu_names": set()},
            )
            entry["qty"] += row.quantity_used * item.quantity
            entry["menu_names"].add(item.name_snapshot)

    for entry in required.values():
        ingredient = entry["ingredient"]
        if ingredient.stock_quantity < entry["qty"]:
            return _(
                "Stok %(ingredient)s tidak cukup untuk pesanan %(items)s.",
                ingredient=ingredient.name,
                items=", ".join(sorted(entry["menu_names"])),
            )

    for entry in required.values():
        ingredient = entry["ingredient"]
        result = db.session.execute(
            Ingredient.__table__.update()
            .where(
                Ingredient.id == ingredient.id,
                Ingredient.stock_quantity >= entry["qty"],
            )
            .values(stock_quantity=Ingredient.stock_quantity - entry["qty"])
        )
        if result.rowcount == 0:
            # Bahan ini keburu dipotong pesanan lain di antara cek di atas
            # dan UPDATE ini - stoknya sekarang sudah tidak cukup lagi.
            # Rollback supaya bahan LAIN yang sudah kadung ke-UPDATE di
            # loop ini (kalau ada) ikut dibatalkan - tetap all-or-nothing.
            db.session.rollback()
            return _(
                "Stok %(ingredient)s baru saja dipakai pesanan lain, tidak cukup untuk pesanan %(items)s.",
                ingredient=ingredient.name,
                items=", ".join(sorted(entry["menu_names"])),
            )
        # Sinkronkan objek Python di session supaya kode setelah pemanggil
        # (mis. flash/tampilan sisa stok) melihat angka yang sudah baru.
        db.session.refresh(ingredient)

    return None


def restore_stock_for_order(order):
    """Kebalikan dari check_and_deduct_stock() - balikin stok bahan baku
    yang sudah dipotong buat order ini. Dipakai saat order yang belum
    lunas dibatalkan (lihat staff.cancel_order) supaya stok yang
    kadung terpotong tidak hilang permanen cuma karena pesanannya
    salah input/batal, dan tidak perlu di-restock manual satu-satu.

    Tidak ada pengecekan "cukup atau tidak" di sini (beda dengan
    deduct) - nambah balik selalu boleh. Tetap lewat UPDATE atomic
    (bukan baca-lalu-tulis) supaya pembatalan yang nyaris bersamaan
    tetap terjumlah benar."""

    required = {}

    for item in order.items:
        if not item.menu_item_id:
            continue

        recipe_rows = MenuItemIngredient.query.filter_by(menu_item_id=item.menu_item_id).all()

        for row in recipe_rows:
            required[row.ingredient_id] = required.get(row.ingredient_id, 0.0) + row.quantity_used * item.quantity

    for ingredient_id, qty in required.items():
        db.session.execute(
            Ingredient.__table__.update()
            .where(Ingredient.id == ingredient_id)
            .values(stock_quantity=Ingredient.stock_quantity + qty)
        )
