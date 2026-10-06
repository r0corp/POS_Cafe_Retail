"""Pesanan lunas dari hari bisnis sebelumnya otomatis ditutup (status
"served") supaya tidak numpuk di Dashboard/Dapur dan tidak menahan meja -
tanpa menghapus apa pun: omzet di Laporan tetap sama."""

from datetime import datetime, timedelta

from app import db as _db
from app.blueprints.staff import _period_report
from app.housekeeping import business_day_start, close_stale_paid_orders
from app.models import Order, OrderItem

NOW = datetime(2026, 10, 6, 10, 0)  # Selasa 10:00 - hari bisnis dimulai 06 Okt 04:00


def _order(item, *, paid_at=None, status="pending", table=None):
    paid = paid_at is not None
    order = Order(
        table_id=table.id if table else None, order_type="dine_in" if table else "takeaway",
        source="staff", status=status, pin="1234", is_paid=paid,
    )
    if paid:
        order.payment_method = "cash"
        order.paid_at = paid_at
    order.items.append(OrderItem(menu_item_id=item.id, name_snapshot=item.name, price_snapshot=item.price, quantity=2))
    _db.session.add(order)
    _db.session.commit()
    return order


def test_business_day_starts_at_four_in_the_morning():
    assert business_day_start(datetime(2026, 10, 6, 10, 0)) == datetime(2026, 10, 6, 4, 0)
    assert business_day_start(datetime(2026, 10, 6, 4, 0)) == datetime(2026, 10, 6, 4, 0)
    assert business_day_start(datetime(2026, 10, 6, 3, 59)) == datetime(2026, 10, 5, 4, 0)


def test_only_paid_orders_from_before_this_business_day_are_closed(db, make_menu_item):
    item = make_menu_item(price=10000)
    yesterday_paid = _order(item, paid_at=NOW - timedelta(hours=14))               # kemarin 20:00
    before_cutoff = _order(item, paid_at=datetime(2026, 10, 6, 3, 59))             # 03:59 = masih hari kemarin
    today_paid = _order(item, paid_at=datetime(2026, 10, 6, 9, 0))                 # hari ini
    yesterday_unpaid = _order(item)                                                # belum lunas: tidak disentuh
    already_done = _order(item, paid_at=NOW - timedelta(days=2), status="served")

    closed = close_stale_paid_orders(now=NOW)

    assert closed == 2
    statuses = {o.id: _db.session.get(Order, o.id).status for o in
                (yesterday_paid, before_cutoff, today_paid, yesterday_unpaid, already_done)}
    assert statuses[yesterday_paid.id] == "served"
    assert statuses[before_cutoff.id] == "served"
    assert statuses[today_paid.id] == "pending"
    assert statuses[yesterday_unpaid.id] == "pending"
    assert statuses[already_done.id] == "served"


def test_late_night_shift_is_not_closed_at_midnight(db, make_menu_item):
    item = make_menu_item()
    paid_at_11_30_pm = _order(item, paid_at=datetime(2026, 10, 5, 23, 30))

    assert close_stale_paid_orders(now=datetime(2026, 10, 6, 0, 30)) == 0
    assert _db.session.get(Order, paid_at_11_30_pm.id).status == "pending"
    assert close_stale_paid_orders(now=datetime(2026, 10, 6, 4, 30)) == 1


def test_closing_keeps_sales_reports_and_frees_the_table(db, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    paid_at = datetime.now() - timedelta(days=2)
    order = _order(item, paid_at=paid_at, table=table)
    start, end = paid_at - timedelta(hours=1), paid_at + timedelta(hours=1)

    assert order in Order.occupying_table_query().all()  # sebelum: meja masih "terisi"
    report_before = _period_report(start, end)

    close_stale_paid_orders()

    assert order not in Order.occupying_table_query().all()
    report_after = _period_report(start, end)
    assert report_after["total_sales"] == report_before["total_sales"] == 30000
    assert report_after["transaction_count"] == report_before["transaction_count"] == 1
    fresh = _db.session.get(Order, order.id)
    assert fresh.is_paid and fresh.paid_at == paid_at and len(fresh.items) == 1


def test_first_request_of_the_day_closes_stale_orders(client, db, make_menu_item):
    item = make_menu_item()
    stale = _order(item, paid_at=datetime.now() - timedelta(days=3))
    fresh = _order(item, paid_at=datetime.now())

    client.get("/login")

    assert _db.session.get(Order, stale.id).status == "served"
    assert _db.session.get(Order, fresh.id).status == "pending"
