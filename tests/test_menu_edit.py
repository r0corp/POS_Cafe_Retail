"""Ubah nama & harga menu oleh Owner."""

from app.models import MenuItem, Order, OrderItem

from .conftest import login


def test_owner_edits_name_and_price(client, owner_user, db, make_menu_item):
    item = make_menu_item(name="Kopi Susu", price=15000)
    login(client, "owner")
    resp = client.post(f"/admin/menu/{item.id}/edit", data={"name": "  Kopi Susu Gula Aren ", "price": "18.000"}, follow_redirects=True)
    assert b"diperbarui" in resp.data
    db.session.refresh(item)
    assert item.name == "Kopi Susu Gula Aren"
    assert item.price == 18000


def test_rejects_invalid_values(client, owner_user, db, make_menu_item):
    item = make_menu_item(name="Teh", price=5000)
    login(client, "owner")
    for data in ({"name": "", "price": "5000"}, {"name": "Teh", "price": "0"}, {"name": "Teh", "price": ""}, {"name": "Teh", "price": "abc"}):
        resp = client.post(f"/admin/menu/{item.id}/edit", data=data, follow_redirects=True)
        assert b"Isi nama dan harga" in resp.data
    db.session.refresh(item)
    assert (item.name, item.price) == ("Teh", 5000)


def test_old_orders_keep_their_price(client, owner_user, kasir_user, db, make_menu_item):
    item = make_menu_item(name="Roti", price=10000)
    order = Order(order_type="takeaway", source="staff", status="pending", pin="1234")
    order.items.append(OrderItem(menu_item_id=item.id, name_snapshot="Roti", price_snapshot=10000, quantity=2))
    db.session.add(order)
    db.session.commit()

    login(client, "owner")
    client.post(f"/admin/menu/{item.id}/edit", data={"name": "Roti Premium", "price": "12000"})
    db.session.refresh(order)
    assert order.items[0].price_snapshot == 10000
    assert order.items[0].name_snapshot == "Roti"
    assert order.total == 20000


def test_staff_cannot_edit(client, kasir_user, db, make_menu_item):
    item = make_menu_item(name="Susu", price=7000)
    login(client, "kasir")
    resp = client.post(f"/admin/menu/{item.id}/edit", data={"name": "Retas", "price": "1"})
    assert resp.status_code in (302, 403)
    db.session.refresh(item)
    assert (item.name, item.price) == ("Susu", 7000)


def test_edit_form_is_in_menu_page(client, owner_user, make_menu_item):
    item = make_menu_item(name="Es Teh", price=4000)
    login(client, "owner")
    html = client.get("/admin/menu").data
    assert f"/admin/menu/{item.id}/edit".encode() in html
