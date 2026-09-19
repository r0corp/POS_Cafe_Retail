from flask import Blueprint, abort, flash, render_template, request, redirect, url_for

from .. import db
from ..inventory import check_and_deduct_stock
from ..models import Category, MenuItem, Table, Order, OrderItem

public_bp = Blueprint("public", __name__)


@public_bp.route("/t/<code>")
def menu(code):
    """Halaman menu untuk tamu - dibuka lewat scan QR code di meja."""

    table = Table.query.filter_by(code=code).first_or_404()

    categories = (
        Category.query.order_by(Category.order, Category.name).all()
    )

    return render_template("public/menu.html", table=table, categories=categories)


@public_bp.route("/t/<code>/order", methods=["POST"])
def submit_order(code):
    """Tamu submit pesanan sendiri langsung dari halaman menu (opsional -
    tamu yang tidak nyaman pakai HP tetap bisa dilayani manual oleh
    pelayan lewat halaman staff, lihat blueprints/staff.py)."""

    table = Table.query.filter_by(code=code).first_or_404()

    order = Order(table_id=table.id, source="qr", status="pending")

    added_any = False

    for key, value in request.form.items():
        if not key.startswith("qty_"):
            continue

        try:
            quantity = int(value)
        except ValueError:
            continue

        if quantity <= 0:
            continue

        menu_item_id = int(key.replace("qty_", ""))
        menu_item = MenuItem.query.get(menu_item_id)

        if not menu_item or not menu_item.is_orderable:
            continue

        order.items.append(
            OrderItem(
                menu_item_id=menu_item.id,
                name_snapshot=menu_item.name,
                price_snapshot=menu_item.price,
                quantity=quantity,
            )
        )
        added_any = True

    if not added_any:
        return redirect(url_for("public.menu", code=code))

    stock_error = check_and_deduct_stock(order)
    if stock_error:
        flash(stock_error, "danger")
        return redirect(url_for("public.menu", code=code))

    db.session.add(order)
    db.session.commit()

    return redirect(url_for("public.order_status", code=code, order_id=order.id))


@public_bp.route("/t/<code>/status/<int:order_id>")
def order_status(code, order_id):
    """Halaman status pesanan tamu, di-refresh berkala (lihat template)
    supaya tamu tahu progres tanpa harus tanya ke pelayan."""

    table = Table.query.filter_by(code=code).first_or_404()
    order = Order.query.get_or_404(order_id)

    if order.table_id != table.id:
        abort(404)

    return render_template("public/status.html", table=table, order=order)
