"""Endpoint status yang di-poll tablet tiap beberapa detik (kasir, dapur,
notifikasi bayar). Isinya ("tanda tangan" pesanan) dibandingkan klien
sebagai himpunan string, jadi FORMAT-nya tidak boleh berubah; dan jumlah
query-nya tidak boleh ikut naik tiap ada pesanan tambahan (dulu 1 query
tambahan per pesanan - len(order.items))."""

from datetime import datetime

from sqlalchemy import event

from app import db as _db
from app.models import Order, OrderItem

from .conftest import login


def _make_order(item, quantity_rows, *, status="pending", paid=False):
    order = Order(order_type="takeaway", source="staff", status=status, pin="1234", is_paid=paid)
    if paid:
        order.payment_method = "cash"
        order.paid_at = datetime.now()
    for quantity in quantity_rows:
        order.items.append(
            OrderItem(menu_item_id=item.id, name_snapshot=item.name, price_snapshot=item.price, quantity=quantity)
        )
    _db.session.add(order)
    return order


def _seed(item):
    _make_order(item, [1, 2, 1])                               # belum lunas, pending
    _make_order(item, [1], status="processing")                # belum lunas, diproses dapur
    _make_order(item, [3, 1], status="ready")                  # belum lunas, siap diantar
    _make_order(item, [1, 1], status="served", paid=True)      # lunas & sudah diantar
    _make_order(item, [2], status="pending", paid=True)        # lunas tapi dapur belum selesai
    _db.session.commit()


def _get(client, path):
    return sorted(client.get(path).get_json()["order_ids"])


def test_status_signatures_keep_their_format(client, db, owner_user, make_menu_item):
    item = make_menu_item()
    _seed(item)
    login(client, "owner")

    orders = Order.query.all()
    start = datetime.combine(datetime.now().date(), datetime.min.time())

    assert _get(client, "/kitchen/status") == sorted(
        f"{o.id}:{o.status}:{len(o.items)}" for o in orders if o.status != "served"
    )
    assert _get(client, "/cashier/status") == sorted(
        f"{o.id}:{len(o.items)}" for o in orders if not o.is_paid
    )
    assert _get(client, "/orders/paid-status") == sorted(
        f"{o.id}:{o.paid_at.isoformat()}" for o in orders if o.is_paid and o.paid_at >= start
    )


def test_status_endpoints_do_not_issue_a_query_per_order(client, db, owner_user, make_menu_item):
    item = make_menu_item()
    login(client, "owner")

    counter = {"n": 0}

    def count(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    def queries_for(path):
        counter["n"] = 0
        event.listen(_db.engine, "before_cursor_execute", count)
        try:
            client.get(path)
        finally:
            event.remove(_db.engine, "before_cursor_execute", count)
        return counter["n"]

    for _ in range(3):
        _make_order(item, [1, 1, 1])
    _db.session.commit()
    client.get("/kitchen/status")  # pemanasan (login, last_seen)
    few = {p: queries_for(p) for p in ("/kitchen/status", "/cashier/status", "/orders/paid-status")}

    for _ in range(30):
        _make_order(item, [1, 1, 1])
    _db.session.commit()
    client.get("/kitchen/status")  # pemanasan lagi: commit di atas meng-expire current_user di sesi bersama
    many = {p: queries_for(p) for p in few}

    assert many == few
