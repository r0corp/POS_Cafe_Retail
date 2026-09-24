"""Alur staff.pay_order() end-to-end - bagian paling kritis soal uang:
kembalian, snapshot PPN, dan penjaga bayar-dobel."""

from app import db as _db
from app.models import Order, OrderItem, Settings

from .conftest import login


def _create_dine_in_order(item, table, quantity=1):
    order = Order(table_id=table.id, order_type="dine_in", status="pending", pin="1234")
    order.items.append(
        OrderItem(
            menu_item_id=item.id,
            name_snapshot=item.name,
            price_snapshot=item.price,
            quantity=quantity,
        )
    )
    _db.session.add(order)
    _db.session.commit()
    return order


def test_cash_payment_computes_correct_change(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=2)  # total 30.000
    login(client, "owner")

    res = client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "cash", "cash_received": "50000", "expected_total": "30000"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    _db.session.refresh(order)
    assert order.is_paid is True
    assert order.cash_received == 50000
    assert order.change_amount == 20000


def test_cash_payment_rejected_when_insufficient(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=1)
    login(client, "owner")

    res = client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "cash", "cash_received": "10000", "expected_total": "15000"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    _db.session.refresh(order)
    assert order.is_paid is False


def test_qris_payment_has_no_change(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=20000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=1)
    login(client, "owner")

    client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "qris", "expected_total": "20000"},
        follow_redirects=True,
    )

    _db.session.refresh(order)
    assert order.is_paid is True
    assert order.payment_method == "qris"
    assert order.cash_received is None
    assert order.change_amount is None


def test_double_payment_is_rejected_second_time(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=1)
    login(client, "owner")

    client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "cash", "cash_received": "20000", "expected_total": "15000"},
        follow_redirects=True,
    )
    _db.session.refresh(order)
    assert order.change_amount == 5000
    assert order.served_by == "owner"

    # Submit kedua (mis. klik 2x / tombol back lalu submit ulang) DENGAN
    # metode & jumlah bayar BEDA - tidak boleh menimpa data yang sudah
    # tercatat dari pembayaran pertama.
    client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "qris", "expected_total": "15000"},
        follow_redirects=True,
    )
    _db.session.refresh(order)
    assert order.payment_method == "cash"
    assert order.change_amount == 5000


def test_ppn_snapshot_frozen_after_payment(client, db, owner_user, make_menu_item, make_table):
    settings = Settings.query.first() or Settings(shop_name="Test")
    if not settings.id:
        _db.session.add(settings)
    settings.ppn_enabled = True
    settings.ppn_percentage = 11.0
    _db.session.commit()

    item = make_menu_item(price=100000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=1)
    login(client, "owner")

    client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "qris", "expected_total": str(order.grand_total)},
        follow_redirects=True,
    )
    _db.session.refresh(order)
    assert order.ppn_percentage == 11.0
    assert order.ppn_amount == 11000
    assert order.grand_total == 111000

    # Owner ganti tarif PPN SETELAH order ini lunas - struk yang sudah
    # dibayar TIDAK BOLEH ikut berubah (pakai snapshot, bukan hitung ulang).
    settings.ppn_percentage = 20.0
    _db.session.commit()
    _db.session.refresh(order)
    assert order.grand_total == 111000


def test_payment_rejected_if_items_changed_since_total_shown(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=1)
    login(client, "owner")

    # Kasir buka halaman Kasir (lihat total 15.000), tapi SEBELUM tombol
    # Bayar ditekan, tamu nambah 1 item lagi (mis. lewat pesan tambahan) -
    # expected_total yang dikirim browser jadi basi (masih 15.000).
    order.items.append(
        OrderItem(menu_item_id=item.id, name_snapshot=item.name, price_snapshot=item.price, quantity=1)
    )
    _db.session.commit()

    res = client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "cash", "cash_received": "20000", "expected_total": "15000"},
        follow_redirects=True,
    )

    assert res.status_code == 200
    _db.session.refresh(order)
    assert order.is_paid is False


def test_invalid_payment_method_rejected(client, db, owner_user, make_menu_item, make_table):
    item = make_menu_item(price=15000)
    table = make_table()
    order = _create_dine_in_order(item, table, quantity=1)
    login(client, "owner")

    client.post(
        f"/orders/{order.id}/pay",
        data={"payment_method": "bitcoin", "expected_total": "15000"},
        follow_redirects=True,
    )

    _db.session.refresh(order)
    assert order.is_paid is False
