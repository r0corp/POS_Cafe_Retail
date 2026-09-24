"""Alur staff.new_order() end-to-end lewat test client - meliputi 3
jenis pesanan (Makan di Tempat, Bawa Pulang, Ojek Online) dan validasi
stok/meja yang menjaganya."""

from app import db as _db
from app.models import Order, OrderChannel, CHANNEL_PRICING_PERCENT

from .conftest import login


def test_dine_in_order_requires_available_table(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    login(client, "owner")

    res = client.post(
        "/orders/new",
        data={"order_type": "dine_in", "table_id": table.id, f"qty_{item.id}": "2"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    order = Order.query.filter_by(table_id=table.id).first()
    assert order is not None
    assert order.total == 30000


def test_takeaway_order_needs_no_table(client, db, owner_user, make_menu_item):
    item = make_menu_item(price=15000)
    login(client, "owner")

    res = client.post(
        "/orders/new",
        data={"order_type": "takeaway", f"qty_{item.id}": "1"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    order = Order.query.filter_by(order_type="takeaway").first()
    assert order is not None
    assert order.table_id is None
    assert order.total == 15000


def test_ojol_order_applies_channel_markup(client, db, owner_user, make_menu_item):
    item = make_menu_item(price=10000)
    channel = OrderChannel(name="GrabFood", pricing_mode=CHANNEL_PRICING_PERCENT, markup_percent=20, is_active=True, sort_order=1)
    _db.session.add(channel)
    _db.session.commit()
    login(client, "owner")

    res = client.post(
        "/orders/new",
        data={"order_type": "ojol", "channel_id": channel.id, f"qty_{item.id}": "1"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    order = Order.query.filter_by(order_type="ojol").first()
    assert order is not None
    # 10.000 + 20% markup = 12.000, BUKAN harga normal 10.000.
    assert order.items[0].price_snapshot == 12000
    assert order.total == 12000


def test_second_order_on_occupied_table_is_rejected(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    login(client, "owner")

    client.post(
        "/orders/new",
        data={"order_type": "dine_in", "table_id": table.id, f"qty_{item.id}": "1"},
        follow_redirects=True,
    )
    res = client.post(
        "/orders/new",
        data={"order_type": "dine_in", "table_id": table.id, f"qty_{item.id}": "1"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    # Cuma boleh ada 1 order untuk meja itu, bukan 2.
    assert Order.query.filter_by(table_id=table.id).count() == 1


def test_order_rejected_when_stock_insufficient(client, db, owner_user, make_menu_item, make_ingredient, make_table):
    susu = make_ingredient(name="Susu", unit="ml", stock=50)
    item = make_menu_item(price=15000, recipe=[(susu, 200)])
    table = make_table()
    login(client, "owner")

    res = client.post(
        "/orders/new",
        data={"order_type": "dine_in", "table_id": table.id, f"qty_{item.id}": "1"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    assert Order.query.count() == 0
    assert susu.stock_quantity == 50


def test_unorderable_item_silently_skipped_not_charged(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    item.is_available = False
    _db.session.commit()
    table = make_table()
    login(client, "owner")

    client.post(
        "/orders/new",
        data={"order_type": "dine_in", "table_id": table.id, f"qty_{item.id}": "2"},
        follow_redirects=True,
    )

    # Tidak ada item yang valid dipilih -> order tidak boleh terbentuk.
    assert Order.query.count() == 0
