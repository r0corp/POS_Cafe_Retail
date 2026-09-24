"""check_and_deduct_stock() / restore_stock_for_order() - inti dari
pemotongan bahan baku tiap ada pesanan. Ini area yang paling rawan
race condition (2 pesanan nyaris bersamaan), jadi ditekankan di sini."""

from app import db as _db
from app.inventory import check_and_deduct_stock, restore_stock_for_order
from app.models import Order, OrderItem


def _order_with_item(menu_item, quantity):
    order = Order(order_type="takeaway", status="pending", pin="1234")
    order.items.append(
        OrderItem(
            menu_item_id=menu_item.id,
            name_snapshot=menu_item.name,
            price_snapshot=menu_item.price,
            quantity=quantity,
        )
    )
    return order


def test_deducts_stock_when_sufficient(db, make_ingredient, make_menu_item):
    susu = make_ingredient(name="Susu", unit="ml", stock=1000)
    item = make_menu_item(recipe=[(susu, 200)])

    order = _order_with_item(item, quantity=2)
    error = check_and_deduct_stock(order)

    assert error is None
    assert susu.stock_quantity == 1000 - (200 * 2)


def test_rejects_when_insufficient_and_deducts_nothing(db, make_ingredient, make_menu_item):
    susu = make_ingredient(name="Susu", unit="ml", stock=100)
    item = make_menu_item(recipe=[(susu, 200)])

    order = _order_with_item(item, quantity=1)
    error = check_and_deduct_stock(order)

    assert error is not None
    assert "Susu" in error
    # Gagal berarti stok TIDAK BOLEH berkurang sama sekali (all-or-nothing).
    assert susu.stock_quantity == 100


def test_partial_failure_rolls_back_earlier_deductions_in_same_order(db, make_ingredient, make_menu_item):
    # 1 menu butuh 2 bahan - bahan pertama cukup, bahan kedua tidak.
    # Bahan pertama TIDAK BOLEH ikut kepotong kalau bahan kedua gagal.
    kopi = make_ingredient(name="Kopi", unit="gram", stock=1000)
    susu = make_ingredient(name="Susu", unit="ml", stock=50)
    item = make_menu_item(recipe=[(kopi, 20), (susu, 200)])

    order = _order_with_item(item, quantity=1)
    error = check_and_deduct_stock(order)

    assert error is not None
    assert kopi.stock_quantity == 1000
    assert susu.stock_quantity == 50


def test_menu_item_without_recipe_never_blocked(db, make_menu_item):
    item = make_menu_item(name="Air Putih", recipe=None)
    order = _order_with_item(item, quantity=100)

    error = check_and_deduct_stock(order)

    assert error is None


def test_aggregates_quantity_across_multiple_lines_of_same_item(db, make_ingredient, make_menu_item):
    # 2 baris order item berbeda tapi menu_item sama harus dijumlah,
    # bukan cuma dihitung dari baris terakhir.
    kopi = make_ingredient(name="Kopi", unit="gram", stock=100)
    item = make_menu_item(recipe=[(kopi, 20)])

    order = Order(order_type="takeaway", status="pending", pin="1234")
    order.items.append(OrderItem(menu_item_id=item.id, name_snapshot=item.name, price_snapshot=item.price, quantity=2))
    order.items.append(OrderItem(menu_item_id=item.id, name_snapshot=item.name, price_snapshot=item.price, quantity=1))

    error = check_and_deduct_stock(order)

    assert error is None
    # Total 3 porsi x 20 gram = 60 gram.
    assert kopi.stock_quantity == 40


def test_second_order_fails_after_first_takes_all_stock(db, make_ingredient, make_menu_item):
    # Simulasi race condition secara sekuensial: order A memotong SEMUA
    # stok yang tersisa duluan, order B (dibuat belakangan) harus DITOLAK,
    # bukan ikut lolos memakai angka stok yang sudah basi.
    susu = make_ingredient(name="Susu", unit="ml", stock=200)
    item = make_menu_item(recipe=[(susu, 200)])

    order_a = _order_with_item(item, quantity=1)
    order_b = _order_with_item(item, quantity=1)

    assert check_and_deduct_stock(order_a) is None
    assert susu.stock_quantity == 0

    error_b = check_and_deduct_stock(order_b)
    assert error_b is not None
    assert susu.stock_quantity == 0


def test_restore_stock_returns_exact_deducted_amount(db, make_ingredient, make_menu_item):
    susu = make_ingredient(name="Susu", unit="ml", stock=1000)
    item = make_menu_item(recipe=[(susu, 200)])

    order = _order_with_item(item, quantity=2)
    check_and_deduct_stock(order)
    _db.session.add(order)
    _db.session.commit()

    assert susu.stock_quantity == 600

    restore_stock_for_order(order)
    _db.session.commit()
    _db.session.refresh(susu)

    assert susu.stock_quantity == 1000


def test_restore_uses_recorded_amount_not_current_recipe(db, make_ingredient, make_menu_item):
    # Kalau resepnya diubah SETELAH order dibuat, pembatalan harus tetap
    # mengembalikan angka yang BENAR-BENAR dipotong dulu, bukan hitung
    # ulang pakai resep baru.
    susu = make_ingredient(name="Susu", unit="ml", stock=1000)
    item = make_menu_item(recipe=[(susu, 200)])

    order = _order_with_item(item, quantity=1)
    check_and_deduct_stock(order)
    _db.session.add(order)
    _db.session.commit()

    assert susu.stock_quantity == 800

    # Resep diubah jadi butuh lebih banyak susu per porsi.
    from app.models import MenuItemIngredient
    recipe_row = MenuItemIngredient.query.filter_by(menu_item_id=item.id).first()
    recipe_row.quantity_used = 500
    _db.session.commit()

    restore_stock_for_order(order)
    _db.session.commit()
    _db.session.refresh(susu)

    # Harus balik ke 1000 (pakai catatan lama 200), BUKAN 1000+500-200=1300
    # atau angka lain hasil hitung ulang resep baru.
    assert susu.stock_quantity == 1000
