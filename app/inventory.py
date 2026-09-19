from flask_babel import gettext as _

from .models import MenuItemIngredient


def check_and_deduct_stock(order):
    """Cek stok bahan baku cukup untuk semua item di satu order (belum
    di-commit), lalu kurangi stoknya kalau cukup. Dipanggil bareng oleh
    staff.new_order() dan public.submit_order() sebelum order disimpan.

    Return None kalau berhasil (stok sudah dikurangi, siap di-commit),
    atau pesan error (string) kalau ada bahan yang tidak cukup - dalam
    kasus itu TIDAK ada stok yang dikurangi (semua bahan dicek dulu
    sebelum ada yang benar-benar dipotong)."""

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
        entry["ingredient"].stock_quantity -= entry["qty"]

    return None
