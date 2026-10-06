"""Halaman Kasir menjalankan 2 query berurutan (belum lunas, lalu lunas
hari ini). Kalau kasir lain menyelesaikan pembayaran DI ANTARA keduanya,
objek Order yang sama muncul di dua daftar - dulu itu bikin
cashier.html error 500 (order.paid_at masih kosong di objek yang sudah
termuat)."""

import sqlite3
from datetime import datetime

from sqlalchemy import event

from app import db as _db
from app.models import Order, OrderItem

from .conftest import login


def test_cashier_page_survives_payment_committed_between_its_two_queries(
    client, db, owner_user, make_menu_item
):
    item = make_menu_item(price=15000)
    order = Order(order_type="takeaway", source="staff", status="pending", pin="1234")
    order.items.append(
        OrderItem(menu_item_id=item.id, name_snapshot=item.name, price_snapshot=item.price, quantity=1)
    )
    _db.session.add(order)
    _db.session.commit()
    order_id = order.id
    db_path = _db.engine.url.database
    login(client, "owner")

    fired = {"done": False}

    def pay_from_another_cashier(conn, cursor, statement, parameters, context, executemany):
        # Query kedua halaman Kasir = satu-satunya yang membandingkan paid_at.
        if not fired["done"] and "paid_at >=" in statement:
            fired["done"] = True
            other = sqlite3.connect(db_path)
            other.execute(
                "UPDATE orders SET is_paid = 1, payment_method = 'qris', paid_at = ? WHERE id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), order_id),
            )
            other.commit()
            other.close()

    event.listen(_db.engine, "before_cursor_execute", pay_from_another_cashier)
    try:
        response = client.get("/cashier")
    finally:
        event.remove(_db.engine, "before_cursor_execute", pay_from_another_cashier)

    assert fired["done"], "pembayaran sela tidak sempat disuntikkan - test tidak valid"
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f"#{order_id}" in html  # tampil di daftar lunas hari ini
