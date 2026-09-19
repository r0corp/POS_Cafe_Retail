from datetime import datetime, time, timedelta

import qrcode
import os
import zipfile

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l
from flask_login import current_user, login_required

from .. import db
from ..decorators import roles_required
from ..inventory import check_and_deduct_stock
from ..models import (
    Category,
    Ingredient,
    MenuItem,
    MenuItemIngredient,
    Table,
    Order,
    OrderItem,
    Settings,
    User,
    LoginLog,
    ORDER_STATUSES,
    PAYMENT_METHODS,
    ROLES,
    ROLE_LABELS,
    ROLE_OWNER,
    ROLE_KASIR,
    ROLE_DAPUR,
    ROLE_PELAYAN,
)

staff_bp = Blueprint("staff", __name__)

ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

# Harus sinkron dengan NOTIFICATION_SOUNDS di app/static/js/notify.js.
NOTIFICATION_SOUND_KEYS = {
    "bell_double",
    "ding_dong",
    "single_beep",
    "triple_beep",
    "cashier_bell",
    "soft_chime",
    "kitchen_alarm",
    "marimba",
    "electronic_ping",
    "classic_restaurant",
}


def get_settings():
    settings = Settings.query.order_by(Settings.id.asc()).first()

    if not settings:
        settings = Settings(shop_name=current_app.config["CAFE_NAME"])
        db.session.add(settings)
        db.session.commit()

    return settings


def _upload_folder(subfolder):
    folder = os.path.join(current_app.static_folder, "uploads", subfolder)
    os.makedirs(folder, exist_ok=True)
    return folder


def _branding_upload_folder():
    return _upload_folder("branding")


def _save_logo(file_field_name, obj, model_field, subfolder="branding", filename_base=None):
    """Simpan file gambar yang diupload untuk field tertentu (logo_square,
    logo_wide, qris_image, foto profil user, dll). Return pesan error
    (string) kalau format tidak valid, atau None kalau berhasil/tidak
    ada file baru dipilih."""

    logo_file = request.files.get(file_field_name)

    if not logo_file or not logo_file.filename:
        return None

    extension = os.path.splitext(logo_file.filename)[1].lower()

    if extension not in ALLOWED_LOGO_EXTENSIONS:
        return _("Format gambar harus PNG, JPG, JPEG, WEBP, atau SVG.")

    upload_folder = _upload_folder(subfolder)
    old_filename = getattr(obj, model_field)

    if old_filename:
        old_path = os.path.join(upload_folder, old_filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    new_filename = f"{filename_base or model_field}{extension}"
    logo_file.save(os.path.join(upload_folder, new_filename))
    setattr(obj, model_field, new_filename)

    return None


def _remove_logo(obj, model_field, subfolder="branding"):
    old_filename = getattr(obj, model_field)

    if not old_filename:
        return

    old_path = os.path.join(_upload_folder(subfolder), old_filename)

    if os.path.exists(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass

    setattr(obj, model_field, None)


# ============================================================
# DASHBOARD
# ============================================================

@staff_bp.route("/")
@login_required
def dashboard():
    active_orders = (
        Order.query.filter(Order.status != "served")
        .order_by(Order.created_at.asc())
        .all()
    )

    today = datetime.now().date()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)

    paid_orders_today = Order.query.filter(
        Order.is_paid.is_(True),
        Order.paid_at >= start,
        Order.paid_at <= end,
    ).all()

    unpaid_orders = Order.query.filter_by(is_paid=False).all()
    occupied_table_count = len({order.table_id for order in unpaid_orders})
    kitchen_pending_count = Order.query.filter(
        Order.status.in_(["pending", "processing"])
    ).count()
    low_stock_count = sum(
        1 for ingredient in Ingredient.query.all() if ingredient.is_low_stock
    )

    stats = {
        "active_count": len(active_orders),
        "sales_today": sum(order.total for order in paid_orders_today),
        "transactions_today": len(paid_orders_today),
        "unpaid_count": len(unpaid_orders),
    }

    # Notifikasi kecil di kartu menu, mengikuti alur pelanggan datang ->
    # duduk (meja) -> dapur proses -> bayar di kasir.
    menu_badges = {
        "staff.table_map": occupied_table_count,
        "staff.kitchen": kitchen_pending_count,
        "staff.cashier": stats["unpaid_count"],
        "staff.admin_inventory": low_stock_count,
    }

    return render_template(
        "staff/dashboard.html",
        orders=active_orders,
        stats=stats,
        menu_badges=menu_badges,
    )


# ============================================================
# DENAH MEJA - status kosong/terisi ala pemilihan kursi bioskop
# ============================================================

@staff_bp.route("/tables/map", methods=["GET", "POST"])
@login_required
def table_map():
    is_owner = current_user.role == ROLE_OWNER

    if request.method == "POST":
        if not is_owner:
            abort(403)

        label = request.form.get("label", "").strip()
        floor = request.form.get("floor", type=int)
        code = request.form.get("code", "").strip().lower()

        if label and floor and code:
            table = Table(label=label, floor=floor, code=code)
            db.session.add(table)
            db.session.commit()
            _generate_table_qr(table)
            flash(_("Meja %(label)s ditambahkan beserta QR code-nya.", label=label), "success")
        else:
            flash(_("Lengkapi label, lantai, dan kode meja."), "danger")

        return redirect(url_for("staff.table_map"))

    tables = Table.query.order_by(Table.floor, Table.label).all()

    # Meja dianggap "terisi" selama masih ada pesanan yang belum lunas
    # di meja itu - begitu dibayar lunas, meja otomatis kembali kosong.
    active_order_by_table = {}
    for order in (
        Order.query.filter_by(is_paid=False)
        .order_by(Order.created_at.asc())
        .all()
    ):
        active_order_by_table.setdefault(order.table_id, order)

    floors = {}
    for table in tables:
        floors.setdefault(table.floor, []).append({
            "table": table,
            "order": active_order_by_table.get(table.id),
        })

    available_count = len(tables) - len(active_order_by_table)

    return render_template(
        "staff/table_map.html",
        floors=sorted(floors.items()),
        available_count=available_count,
        total_count=len(tables),
        can_order=current_user.role in (ROLE_OWNER, ROLE_KASIR, ROLE_PELAYAN),
        can_use_cashier=current_user.role in (ROLE_OWNER, ROLE_KASIR),
        is_owner=is_owner,
    )


@staff_bp.route("/tables/status")
@login_required
def tables_status():
    """Dipoll berkala oleh JS di halaman Meja, buat tahu meja mana yang
    terisi/kosong saat ini - dipakai untuk auto-refresh silent supaya
    tampilan di HP pelayan/kasir selalu sinkron sama data di server
    tanpa perlu reload manual."""

    active_order_by_table = {}
    for order in Order.query.filter_by(is_paid=False).all():
        active_order_by_table.setdefault(order.table_id, order.id)

    tables = [
        {"id": table.id, "order_id": active_order_by_table.get(table.id)}
        for table in Table.query.all()
    ]
    return {"tables": tables}


@staff_bp.route("/tables/<int:table_id>/delete", methods=["POST"])
@roles_required(ROLE_OWNER)
def delete_table(table_id):
    table = Table.query.get_or_404(table_id)

    if table.orders:
        flash(
            _(
                "Meja %(label)s tidak bisa dihapus karena sudah punya riwayat "
                "pesanan (dipakai di laporan/struk). Biarkan saja kalau sudah "
                "tidak dipakai, atau ganti labelnya.",
                label=table.label,
            ),
            "danger",
        )
        return redirect(url_for("staff.table_map"))

    qr_path = os.path.join(current_app.root_path, "static", "qrcodes", f"{table.code}.png")
    if os.path.exists(qr_path):
        try:
            os.remove(qr_path)
        except OSError:
            pass

    label = table.label
    db.session.delete(table)
    db.session.commit()

    flash(_("Meja %(label)s berhasil dihapus.", label=label), "success")
    return redirect(url_for("staff.table_map"))


@staff_bp.route("/tables/<int:table_id>/qr-print")
@roles_required(ROLE_OWNER)
def table_qr_print(table_id):
    table = Table.query.get_or_404(table_id)
    settings = get_settings()

    return render_template("staff/table_qr_print.html", table=table, settings=settings)


# ============================================================
# INPUT PESANAN MANUAL (oleh pelayan, untuk tamu tanpa HP)
# ============================================================

@staff_bp.route("/orders/new", methods=["GET", "POST"])
@roles_required(ROLE_OWNER, ROLE_KASIR, ROLE_PELAYAN)
def new_order():
    tables = Table.query.order_by(Table.floor, Table.label).all()
    categories = Category.query.order_by(Category.order, Category.name).all()
    preselected_table_id = request.args.get("table_id", type=int)

    if request.method == "POST":
        table_id = request.form.get("table_id", type=int)
        table = Table.query.get(table_id)

        if not table:
            flash(_("Meja tidak valid."), "danger")
            return redirect(url_for("staff.new_order"))

        order = Order(table_id=table.id, source="staff", status="pending")
        added_any = False

        for key, value in request.form.items():
            if not key.startswith("qty_"):
                continue

            quantity = int(value or 0)

            if quantity <= 0:
                continue

            menu_item = MenuItem.query.get(int(key.replace("qty_", "")))

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
            flash(_("Pilih minimal 1 item."), "warning")
            return redirect(url_for("staff.new_order"))

        stock_error = check_and_deduct_stock(order)
        if stock_error:
            flash(stock_error, "danger")
            return redirect(url_for("staff.new_order"))

        db.session.add(order)
        db.session.commit()

        flash(_("Pesanan untuk %(label)s berhasil dibuat.", label=table.label), "success")
        return redirect(url_for("staff.dashboard"))

    return render_template(
        "staff/order_new.html",
        tables=tables,
        categories=categories,
        preselected_table_id=preselected_table_id,
    )


# ============================================================
# DAPUR - update status pesanan
# ============================================================

@staff_bp.route("/kitchen")
@roles_required(ROLE_OWNER, ROLE_DAPUR)
def kitchen():
    orders = (
        Order.query.filter(Order.status != "served")
        .order_by(Order.created_at.asc())
        .all()
    )

    return render_template("staff/kitchen.html", orders=orders)


@staff_bp.route("/kitchen/status")
@roles_required(ROLE_OWNER, ROLE_DAPUR)
def kitchen_status():
    """Dipoll berkala oleh JS di halaman Dapur, cuma buat tahu ID
    pesanan aktif saat ini - dipakai buat deteksi "ada pesanan baru"
    supaya bisa bunyikan notifikasi suara tanpa reload manual."""

    ids = [
        order.id
        for order in Order.query.filter(Order.status != "served").all()
    ]
    return {"order_ids": ids}


@staff_bp.route("/orders/<int:order_id>/advance", methods=["POST"])
@roles_required(ROLE_OWNER, ROLE_DAPUR)
def advance_status(order_id):
    order = Order.query.get_or_404(order_id)

    current_index = ORDER_STATUSES.index(order.status)

    if current_index < len(ORDER_STATUSES) - 1:
        order.status = ORDER_STATUSES[current_index + 1]
        db.session.commit()

    return redirect(request.referrer or url_for("staff.kitchen"))


# ============================================================
# KASIR - pembayaran
# ============================================================

@staff_bp.route("/cashier")
@roles_required(ROLE_OWNER, ROLE_KASIR)
def cashier():
    orders = (
        Order.query.filter_by(is_paid=False)
        .order_by(Order.created_at.asc())
        .all()
    )

    today = datetime.now().date()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)

    paid_today = (
        Order.query.filter(
            Order.is_paid.is_(True),
            Order.paid_at >= start,
            Order.paid_at <= end,
        )
        .order_by(Order.paid_at.desc())
        .all()
    )

    return render_template("staff/cashier.html", orders=orders, paid_today=paid_today)


@staff_bp.route("/cashier/status")
@roles_required(ROLE_OWNER, ROLE_KASIR)
def cashier_status():
    """Sama seperti kitchen_status() tapi untuk pesanan yang menunggu
    dibayar - dipakai buat bunyikan notifikasi suara di halaman Kasir."""

    ids = [order.id for order in Order.query.filter_by(is_paid=False).all()]
    return {"order_ids": ids}


@staff_bp.route("/orders/<int:order_id>/pay", methods=["POST"])
@roles_required(ROLE_OWNER, ROLE_KASIR)
def pay_order(order_id):
    order = Order.query.get_or_404(order_id)

    method = request.form.get("payment_method")

    if method not in PAYMENT_METHODS:
        flash(_("Metode pembayaran tidak valid."), "danger")
        return redirect(url_for("staff.cashier"))

    cash_received = None
    change_amount = None

    if method == "cash":
        cash_received = request.form.get("cash_received", type=int)

        if not cash_received or cash_received < order.total:
            flash(_("Uang diterima kurang dari total tagihan."), "danger")
            return redirect(url_for("staff.cashier"))

        change_amount = cash_received - order.total

    order.is_paid = True
    order.payment_method = method
    order.paid_at = datetime.now()
    order.served_by = current_user.username
    order.cash_received = cash_received
    order.change_amount = change_amount
    db.session.commit()

    flash(_("Pesanan #%(id)s ditandai sudah dibayar.", id=order.id), "success")
    return redirect(url_for("staff.receipt", order_id=order.id))


@staff_bp.route("/orders/<int:order_id>/receipt")
@roles_required(ROLE_OWNER, ROLE_KASIR)
def receipt(order_id):
    order = Order.query.get_or_404(order_id)
    settings = get_settings()

    return render_template("staff/receipt.html", order=order, settings=settings)


# ============================================================
# ADMIN - KATEGORI & MENU
# ============================================================

@staff_bp.route("/admin/menu", methods=["GET", "POST"])
@roles_required(ROLE_OWNER)
def admin_menu():
    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "category":
            name = request.form.get("name", "").strip()

            if name:
                db.session.add(Category(name=name))
                db.session.commit()
                flash(_("Kategori ditambahkan."), "success")

        elif form_type == "menu_item":
            name = request.form.get("name", "").strip()
            price = request.form.get("price", type=int)
            category_id = request.form.get("category_id", type=int)

            if name and price and category_id:
                db.session.add(
                    MenuItem(name=name, price=price, category_id=category_id)
                )
                db.session.commit()
                flash(_("Menu ditambahkan."), "success")

        return redirect(url_for("staff.admin_menu"))

    categories = Category.query.order_by(Category.order, Category.name).all()
    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template(
        "staff/menu_admin.html", categories=categories, ingredients=ingredients
    )


@staff_bp.route("/admin/menu/<int:item_id>/toggle", methods=["POST"])
@roles_required(ROLE_OWNER)
def toggle_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    item.is_available = not item.is_available
    db.session.commit()
    return redirect(url_for("staff.admin_menu"))


@staff_bp.route("/admin/menu/<int:item_id>/delete", methods=["POST"])
@roles_required(ROLE_OWNER)
def delete_menu_item(item_id):
    item = MenuItem.query.get_or_404(item_id)

    if item.order_items:
        flash(
            _(
                "Menu %(name)s tidak bisa dihapus karena sudah punya riwayat "
                "pesanan (dipakai di laporan/struk). Tandai \"Habis\" saja kalau "
                "sudah tidak dijual.",
                name=item.name,
            ),
            "danger",
        )
        return redirect(url_for("staff.admin_menu"))

    _remove_logo(item, "photo", subfolder="menu")

    name = item.name
    db.session.delete(item)
    db.session.commit()
    flash(_("Menu %(name)s dihapus.", name=name), "success")
    return redirect(url_for("staff.admin_menu"))


@staff_bp.route("/admin/menu/<int:item_id>/photo", methods=["POST"])
@roles_required(ROLE_OWNER)
def update_menu_item_photo(item_id):
    item = MenuItem.query.get_or_404(item_id)

    if request.form.get("remove_photo") == "1":
        _remove_logo(item, "photo", subfolder="menu")
        db.session.commit()
        flash(_("Foto %(name)s dihapus.", name=item.name), "success")
        return redirect(url_for("staff.admin_menu"))

    error = _save_logo(
        "photo", item, "photo",
        subfolder="menu", filename_base=f"menu-{item.id}",
    )

    if error:
        flash(error, "danger")
        return redirect(url_for("staff.admin_menu"))

    db.session.commit()
    flash(_("Foto %(name)s berhasil diperbarui.", name=item.name), "success")
    return redirect(url_for("staff.admin_menu"))


@staff_bp.route("/admin/menu/<int:item_id>/recipe/add", methods=["POST"])
@roles_required(ROLE_OWNER)
def add_recipe_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    ingredient_id = request.form.get("ingredient_id", type=int)
    quantity_used = request.form.get("quantity_used", type=float)

    ingredient = Ingredient.query.get(ingredient_id) if ingredient_id else None

    if not ingredient or not quantity_used or quantity_used <= 0:
        flash(_("Pilih bahan baku dan isi jumlah pemakaian dengan benar."), "warning")
        return redirect(url_for("staff.admin_menu"))

    existing = MenuItemIngredient.query.filter_by(
        menu_item_id=item.id, ingredient_id=ingredient.id
    ).first()

    if existing:
        existing.quantity_used = quantity_used
    else:
        db.session.add(
            MenuItemIngredient(
                menu_item_id=item.id,
                ingredient_id=ingredient.id,
                quantity_used=quantity_used,
            )
        )

    db.session.commit()
    flash(_("Resep %(name)s berhasil diperbarui.", name=item.name), "success")
    return redirect(url_for("staff.admin_menu"))


@staff_bp.route("/admin/menu/<int:item_id>/recipe/<int:ingredient_id>/remove", methods=["POST"])
@roles_required(ROLE_OWNER)
def remove_recipe_item(item_id, ingredient_id):
    row = MenuItemIngredient.query.filter_by(
        menu_item_id=item_id, ingredient_id=ingredient_id
    ).first_or_404()
    db.session.delete(row)
    db.session.commit()
    return redirect(url_for("staff.admin_menu"))


# ============================================================
# ADMIN - INVENTORY BAHAN BAKU
# ============================================================

@staff_bp.route("/admin/inventory", methods=["GET", "POST"])
@roles_required(ROLE_OWNER)
def admin_inventory():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "").strip()
        stock_quantity = request.form.get("stock_quantity", type=float)
        low_stock_threshold = request.form.get("low_stock_threshold", type=float)

        if name and unit and stock_quantity is not None:
            db.session.add(
                Ingredient(
                    name=name,
                    unit=unit,
                    stock_quantity=stock_quantity,
                    low_stock_threshold=low_stock_threshold or 0,
                )
            )
            db.session.commit()
            flash(_("Bahan baku %(name)s ditambahkan.", name=name), "success")
        else:
            flash(_("Isi nama, satuan, dan stok awal dengan benar."), "warning")

        return redirect(url_for("staff.admin_inventory"))

    ingredients = Ingredient.query.order_by(Ingredient.name).all()
    return render_template("staff/inventory.html", ingredients=ingredients)


@staff_bp.route("/admin/inventory/<int:ingredient_id>/restock", methods=["POST"])
@roles_required(ROLE_OWNER)
def restock_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    amount = request.form.get("amount", type=float)

    if not amount or amount <= 0:
        flash(_("Jumlah restock tidak valid."), "warning")
        return redirect(url_for("staff.admin_inventory"))

    ingredient.stock_quantity += amount
    db.session.commit()
    flash(
        _("Stok %(name)s ditambah %(amount)s %(unit)s.", name=ingredient.name, amount=amount, unit=ingredient.unit),
        "success",
    )
    return redirect(url_for("staff.admin_inventory"))


@staff_bp.route("/admin/inventory/<int:ingredient_id>/delete", methods=["POST"])
@roles_required(ROLE_OWNER)
def delete_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)

    if ingredient.recipe_usages:
        menu_names = ", ".join(sorted({row.menu_item.name for row in ingredient.recipe_usages}))
        flash(
            _(
                "Bahan %(name)s tidak bisa dihapus karena masih dipakai di resep: %(menus)s.",
                name=ingredient.name,
                menus=menu_names,
            ),
            "danger",
        )
        return redirect(url_for("staff.admin_inventory"))

    name = ingredient.name
    db.session.delete(ingredient)
    db.session.commit()
    flash(_("Bahan %(name)s dihapus.", name=name), "success")
    return redirect(url_for("staff.admin_inventory"))


# ============================================================
# HELPER - QR CODE MEJA (dipakai oleh table_map())
# ============================================================

def _generate_table_qr(table):
    """Generate gambar QR code yang mengarah ke halaman menu meja ini,
    disimpan di app/static/qrcodes/<code>.png supaya bisa dicetak/tempel
    di meja fisik."""

    target_url = f"{current_app.config['BASE_URL']}/t/{table.code}"

    qr_dir = os.path.join(current_app.root_path, "static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)

    img = qrcode.make(target_url)
    img.save(os.path.join(qr_dir, f"{table.code}.png"))


# ============================================================
# LAPORAN SEDERHANA
# ============================================================

def _period_report(start, end):
    """Rekap transaksi lunas dalam satu rentang waktu (dipakai untuk
    rekap harian/mingguan/bulanan/tahunan di halaman Laporan)."""

    orders = Order.query.filter(
        Order.is_paid.is_(True),
        Order.paid_at >= start,
        Order.paid_at <= end,
    ).all()

    total_sales = sum(order.total for order in orders)
    transaction_count = len(orders)

    item_counts = {}
    items_sold = 0

    for order in orders:
        for item in order.items:
            item_counts[item.name_snapshot] = (
                item_counts.get(item.name_snapshot, 0) + item.quantity
            )
            items_sold += item.quantity

    top_items = sorted(item_counts.items(), key=lambda pair: pair[1], reverse=True)[:10]

    return {
        "total_sales": total_sales,
        "transaction_count": transaction_count,
        "items_sold": items_sold,
        "avg_per_transaction": (total_sales / transaction_count) if transaction_count else 0,
        "top_items": top_items,
    }


BULAN_ID = [
    _l("Januari"), _l("Februari"), _l("Maret"), _l("April"), _l("Mei"), _l("Juni"),
    _l("Juli"), _l("Agustus"), _l("September"), _l("Oktober"), _l("November"), _l("Desember"),
]
BULAN_ID_SHORT = [
    _l("Jan"), _l("Feb"), _l("Mar"), _l("Apr"), _l("Mei"), _l("Jun"),
    _l("Jul"), _l("Agu"), _l("Sep"), _l("Okt"), _l("Nov"), _l("Des"),
]

PERIOD_KEYS = ("daily", "weekly", "monthly", "yearly")
PERIOD_LABELS = {
    "daily": _l("Harian"),
    "weekly": _l("Mingguan"),
    "monthly": _l("Bulanan"),
    "yearly": _l("Tahunan"),
}


def _period_bounds(period_key):
    """Hitung (start, end, range_label) untuk satu period_key ('daily',
    'weekly', 'monthly', 'yearly'), dipakai bareng oleh reports() dan
    route export CSV/PDF supaya rentang tanggalnya selalu sinkron."""

    today = datetime.now().date()

    if period_key == "daily":
        start_date, end_date = today, today
        range_label = f"{today.day} {BULAN_ID[today.month - 1]} {today.year}"

    elif period_key == "weekly":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        range_label = (
            f"{start_date.day} {BULAN_ID_SHORT[start_date.month - 1]} - "
            f"{end_date.day} {BULAN_ID_SHORT[end_date.month - 1]} {end_date.year}"
        )

    elif period_key == "monthly":
        start_date = today.replace(day=1)
        next_month_date = (
            start_date.replace(year=start_date.year + 1, month=1)
            if start_date.month == 12
            else start_date.replace(month=start_date.month + 1)
        )
        end_date = next_month_date - timedelta(days=1)
        range_label = f"{BULAN_ID[today.month - 1]} {today.year}"

    elif period_key == "yearly":
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(month=12, day=31)
        range_label = str(today.year)

    else:
        abort(404)

    return (
        datetime.combine(start_date, time.min),
        datetime.combine(end_date, time.max),
        range_label,
    )


@staff_bp.route("/reports")
@roles_required(ROLE_OWNER)
def reports():
    periods = {}

    for key in PERIOD_KEYS:
        start, end, range_label = _period_bounds(key)
        periods[key] = {
            "label": PERIOD_LABELS[key],
            "range_label": range_label,
            "data": _period_report(start, end),
        }

    return render_template("staff/reports.html", periods=periods)


def _orders_in_period(start, end):
    return (
        Order.query.filter(
            Order.is_paid.is_(True),
            Order.paid_at >= start,
            Order.paid_at <= end,
        )
        .order_by(Order.paid_at)
        .all()
    )


@staff_bp.route("/reports/export/<period_key>.xlsx")
@roles_required(ROLE_OWNER)
def export_report_excel(period_key):
    if period_key not in PERIOD_KEYS:
        abort(404)

    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    start, end, range_label = _period_bounds(period_key)
    orders = _orders_in_period(start, end)
    data = _period_report(start, end)
    settings = get_settings()

    wb = Workbook()
    ws = wb.active
    ws.title = str(PERIOD_LABELS[period_key])[:31]

    header_fill = PatternFill("solid", fgColor="5C3B1E")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(bold=True, size=14)
    bold_font = Font(bold=True)
    thin_border = Border(bottom=Side(style="thin", color="E4D9CC"))
    rupiah_format = '"Rp" #,##0'

    ws.merge_cells("A1:I1")
    ws["A1"] = settings.shop_name
    ws["A1"].font = title_font

    ws.merge_cells("A2:I2")
    ws["A2"] = f"{PERIOD_LABELS[period_key]} - {range_label}"
    ws["A2"].font = Font(color="6B5B4C")

    summary_rows = [
        (_("Total Penjualan"), data["total_sales"], rupiah_format),
        (_("Transaksi"), data["transaction_count"], "0"),
        (_("Rata-rata/Transaksi"), round(data["avg_per_transaction"]), rupiah_format),
        (_("Item Terjual"), data["items_sold"], "0"),
    ]
    row = 4
    for label, value, num_format in summary_rows:
        ws.cell(row=row, column=1, value=str(label)).font = bold_font
        cell = ws.cell(row=row, column=2, value=value)
        cell.number_format = num_format
        cell.font = bold_font
        row += 1

    row += 1
    header_row = row
    headers = [
        _("No. Struk"), _("Tanggal"), _("Meja"), _("Item"),
        _("Metode"), _("Total"), _("Tunai"), _("Kembalian"), _("Kasir"),
    ]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=str(text))
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")

    row = header_row + 1
    total_sales = 0

    for order in orders:
        items_desc = ", ".join(f"{i.quantity}x {i.name_snapshot}" for i in order.items)
        values = [
            f"#{order.id}",
            order.paid_at.strftime("%d/%m/%Y %H:%M"),
            order.table.label,
            items_desc,
            "Cash" if order.payment_method == "cash" else "QRIS",
            order.total,
            order.cash_received,
            order.change_amount,
            order.served_by or "",
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.border = thin_border
            if col in (6, 7, 8) and value is not None:
                cell.number_format = rupiah_format
        total_sales += order.total
        row += 1

    if not orders:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=9)
        ws.cell(row=row, column=1, value=str(_("Belum ada penjualan di periode ini.")))
        row += 1

    row += 1
    ws.cell(row=row, column=5, value=str(_("Total Penjualan"))).font = bold_font
    total_cell = ws.cell(row=row, column=6, value=total_sales)
    total_cell.number_format = rupiah_format
    total_cell.font = bold_font
    row += 1
    ws.cell(row=row, column=5, value=str(_("Jumlah Transaksi"))).font = bold_font
    ws.cell(row=row, column=6, value=len(orders)).font = bold_font

    ws.freeze_panes = f"A{header_row + 1}"

    widths = [10, 17, 12, 40, 9, 13, 13, 13, 14]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"laporan-{period_key}-{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=filename,
    )


@staff_bp.route("/reports/export/<period_key>.pdf")
@roles_required(ROLE_OWNER)
def export_report_pdf(period_key):
    if period_key not in PERIOD_KEYS:
        abort(404)

    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    start, end, range_label = _period_bounds(period_key)
    orders = _orders_in_period(start, end)
    data = _period_report(start, end)
    settings = get_settings()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=16 * mm, bottomMargin=16 * mm,
        leftMargin=14 * mm, rightMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(settings.shop_name, styles["Title"]))
    story.append(Paragraph(f"{PERIOD_LABELS[period_key]} &middot; {range_label}", styles["Normal"]))
    story.append(Spacer(1, 10 * mm))

    summary_rows = [
        [_("Total Penjualan"), f"Rp {data['total_sales']:,}".replace(",", ".")],
        [_("Transaksi"), str(data["transaction_count"])],
        [_("Rata-rata/Transaksi"), f"Rp {data['avg_per_transaction']:,.0f}".replace(",", ".")],
        [_("Item Terjual"), str(data["items_sold"])],
    ]
    summary_table = Table(summary_rows, colWidths=[55 * mm, 45 * mm])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#E4D9CC")),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8 * mm))

    header = [
        _("No. Struk"), _("Tanggal"), _("Meja"), _("Item"),
        _("Metode"), _("Total"), _("Tunai"), _("Kembalian"), _("Kasir"),
    ]
    table_data = [header]

    for order in orders:
        items_desc = ", ".join(f"{i.quantity}x {i.name_snapshot}" for i in order.items)
        table_data.append([
            f"#{order.id}",
            order.paid_at.strftime("%d/%m/%Y %H:%M"),
            order.table.label,
            Paragraph(items_desc, styles["Normal"]),
            "Cash" if order.payment_method == "cash" else "QRIS",
            f"Rp {order.total:,}".replace(",", "."),
            f"Rp {order.cash_received:,}".replace(",", ".") if order.cash_received else "-",
            f"Rp {order.change_amount:,}".replace(",", ".") if order.change_amount else "-",
            order.served_by or "-",
        ])

    if len(table_data) == 1:
        table_data.append([_("Belum ada penjualan di periode ini."), "", "", "", "", "", "", "", ""])

    orders_table = Table(
        table_data,
        colWidths=[16 * mm, 26 * mm, 20 * mm, 62 * mm, 16 * mm, 24 * mm, 22 * mm, 22 * mm, 22 * mm],
        repeatRows=1,
    )
    orders_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5C3B1E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E4D9CC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FBF3E8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(orders_table)

    doc.build(story)
    buffer.seek(0)

    filename = f"laporan-{period_key}-{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        buffer, mimetype="application/pdf",
        as_attachment=True, download_name=filename,
    )


# ============================================================
# ADMIN - USER & HAK AKSES
# ============================================================

@staff_bp.route("/admin/users", methods=["GET", "POST"])
@roles_required(ROLE_OWNER)
def admin_users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role")

        if not username or not password or role not in ROLES:
            flash(_("Isi username, password, dan role dengan benar."), "danger")
        elif User.query.filter_by(username=username).first():
            flash(_("Username sudah dipakai."), "danger")
        else:
            user = User(username=username, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(
                _(
                    "User '%(username)s' (%(role)s) berhasil dibuat.",
                    username=username,
                    role=ROLE_LABELS[role],
                ),
                "success",
            )

        return redirect(url_for("staff.admin_users"))

    users = User.query.order_by(User.username).all()
    recent_logs = LoginLog.query.order_by(LoginLog.created_at.desc()).limit(50).all()

    return render_template(
        "staff/users_admin.html",
        users=users,
        roles=ROLES,
        role_labels=ROLE_LABELS,
        recent_logs=recent_logs,
    )


@staff_bp.route("/admin/users/status")
@roles_required(ROLE_OWNER)
def admin_users_status():
    """Dipoll berkala lewat JS di halaman Kelola User, supaya indikator
    online tiap akun terasa real-time tanpa perlu reload seluruh
    halaman (biar form Tambah User yang sedang diisi tidak keganggu)."""

    users = User.query.all()

    return {
        "users": [
            {
                "id": user.id,
                "is_online": user.is_online,
                "last_seen_label": (
                    user.last_seen_at.strftime("%d/%m %H:%M")
                    if user.last_seen_at else None
                ),
            }
            for user in users
        ]
    }


@staff_bp.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@roles_required(ROLE_OWNER)
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash(_("Tidak bisa menonaktifkan akun sendiri."), "warning")
        return redirect(url_for("staff.admin_users"))

    user.is_active_user = not user.is_active_user
    db.session.commit()

    return redirect(url_for("staff.admin_users"))


@staff_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@roles_required(ROLE_OWNER)
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash(_("Tidak bisa menghapus akun sendiri."), "warning")
        return redirect(url_for("staff.admin_users"))

    _remove_logo(user, "photo", subfolder="avatars")

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(_("User %(username)s dihapus.", username=username), "success")
    return redirect(url_for("staff.admin_users"))


@staff_bp.route("/admin/users/<int:user_id>/photo", methods=["POST"])
@roles_required(ROLE_OWNER)
def update_user_photo(user_id):
    user = User.query.get_or_404(user_id)

    if request.form.get("remove_photo") == "1":
        _remove_logo(user, "photo", subfolder="avatars")
        db.session.commit()
        flash(_("Foto %(username)s dihapus.", username=user.username), "success")
        return redirect(url_for("staff.admin_users"))

    error = _save_logo(
        "photo", user, "photo",
        subfolder="avatars", filename_base=f"user-{user.id}",
    )

    if error:
        flash(error, "danger")
        return redirect(url_for("staff.admin_users"))

    db.session.commit()
    flash(_("Foto profil %(username)s berhasil diperbarui.", username=user.username), "success")
    return redirect(url_for("staff.admin_users"))


# ============================================================
# ADMIN - PENGATURAN TOKO (NAMA, LOGO, FOOTER)
# ============================================================

@staff_bp.route("/admin/settings", methods=["GET", "POST"])
@roles_required(ROLE_OWNER)
def admin_settings():
    settings = get_settings()

    if request.method == "POST":
        shop_name = request.form.get("shop_name", "").strip()
        footer_text = request.form.get("footer_text", "").strip()

        if not shop_name:
            flash(_("Nama toko wajib diisi."), "danger")
            return redirect(url_for("staff.admin_settings"))

        error = _save_logo("logo_square", settings, "logo_square")
        if error:
            flash(error, "danger")
            return redirect(url_for("staff.admin_settings"))

        error = _save_logo("logo_wide", settings, "logo_wide")
        if error:
            flash(error, "danger")
            return redirect(url_for("staff.admin_settings"))

        error = _save_logo("qris_image", settings, "qris_image")
        if error:
            flash(error, "danger")
            return redirect(url_for("staff.admin_settings"))

        if request.form.get("remove_logo_square") == "1":
            _remove_logo(settings, "logo_square")

        if request.form.get("remove_logo_wide") == "1":
            _remove_logo(settings, "logo_wide")

        if request.form.get("remove_qris_image") == "1":
            _remove_logo(settings, "qris_image")

        app_logo_choice = request.form.get("app_logo_choice", "square")
        receipt_logo_choice = request.form.get("receipt_logo_choice", "wide")

        settings.shop_name = shop_name
        settings.footer_text = footer_text or None
        settings.app_logo_choice = app_logo_choice if app_logo_choice in ("square", "wide") else "square"
        settings.receipt_logo_choice = receipt_logo_choice if receipt_logo_choice in ("square", "wide") else "wide"
        paper_width = request.form.get("receipt_paper_width", "80")
        settings.receipt_paper_width = paper_width if paper_width in ("58", "80") else "80"
        settings.address = request.form.get("address", "").strip() or None
        settings.phone = request.form.get("phone", "").strip() or None
        settings.instagram = request.form.get("instagram", "").strip() or None
        settings.tiktok = request.form.get("tiktok", "").strip() or None
        settings.whatsapp = request.form.get("whatsapp", "").strip() or None
        settings.other_social = request.form.get("other_social", "").strip() or None

        settings.notification_enabled = request.form.get("notification_enabled") == "1"
        notification_sound = request.form.get("notification_sound", "bell_double")
        settings.notification_sound = (
            notification_sound if notification_sound in NOTIFICATION_SOUND_KEYS else "bell_double"
        )
        notification_volume = request.form.get("notification_volume", type=int)
        if notification_volume is None:
            notification_volume = 70
        settings.notification_volume = max(0, min(100, notification_volume))

        db.session.commit()

        flash(_("Pengaturan toko berhasil disimpan."), "success")
        return redirect(url_for("staff.admin_settings"))

    return render_template("staff/settings_admin.html", settings=settings)


# ============================================================
# SISTEM - BERSIHKAN CACHE & BACKUP DATABASE
# ============================================================

def _backup_folder():
    folder = current_app.config["BACKUP_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    return folder


def _db_file_path():
    uri = current_app.config["SQLALCHEMY_DATABASE_URI"]
    # "sqlite:///C:\...\cafe.db" -> "C:\...\cafe.db"
    return uri.replace("sqlite:///", "", 1)


@staff_bp.route("/admin/system")
@roles_required(ROLE_OWNER)
def admin_system():
    settings = get_settings()

    backups = []
    for filename in os.listdir(_backup_folder()):
        if not filename.endswith(".zip"):
            continue
        path = os.path.join(_backup_folder(), filename)
        backups.append({
            "name": filename,
            "size_mb": round(os.path.getsize(path) / (1024 * 1024), 2),
            "created_at": datetime.fromtimestamp(os.path.getmtime(path)),
        })
    backups.sort(key=lambda b: b["created_at"], reverse=True)

    return render_template("staff/system.html", settings=settings, backups=backups)


@staff_bp.route("/admin/system/clear-cache", methods=["POST"])
@roles_required(ROLE_OWNER)
def clear_cache():
    settings = get_settings()
    settings.cache_version += 1
    db.session.commit()

    flash(
        _(
            "Cache aplikasi dibersihkan - logo, foto profil, dan QR code "
            "akan otomatis dimuat ulang versi terbaru di semua device."
        ),
        "success",
    )
    return redirect(url_for("staff.admin_system"))


@staff_bp.route("/admin/system/backup/create", methods=["POST"])
@roles_required(ROLE_OWNER)
def backup_create():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"cafepos_backup_{timestamp}.zip"
    zip_path = os.path.join(_backup_folder(), filename)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        db_path = _db_file_path()
        if os.path.exists(db_path):
            zf.write(db_path, arcname=os.path.join("instance", os.path.basename(db_path)))

        uploads_dir = os.path.join(current_app.static_folder, "uploads")
        for root, _dirs, files in os.walk(uploads_dir):
            for name in files:
                full_path = os.path.join(root, name)
                arcname = os.path.join(
                    "static", "uploads", os.path.relpath(full_path, uploads_dir)
                )
                zf.write(full_path, arcname=arcname)

        qrcodes_dir = os.path.join(current_app.static_folder, "qrcodes")
        if os.path.isdir(qrcodes_dir):
            for name in os.listdir(qrcodes_dir):
                full_path = os.path.join(qrcodes_dir, name)
                if os.path.isfile(full_path):
                    zf.write(full_path, arcname=os.path.join("static", "qrcodes", name))

    flash(_("Backup berhasil dibuat: %(filename)s", filename=filename), "success")
    return redirect(url_for("staff.admin_system"))


@staff_bp.route("/admin/system/backup/download/<path:filename>")
@roles_required(ROLE_OWNER)
def backup_download(filename):
    filename = secure_filename(filename)
    path = os.path.join(_backup_folder(), filename)

    if not os.path.exists(path):
        abort(404)

    return send_file(path, as_attachment=True, download_name=filename)


@staff_bp.route("/admin/system/backup/delete/<path:filename>", methods=["POST"])
@roles_required(ROLE_OWNER)
def backup_delete(filename):
    filename = secure_filename(filename)
    path = os.path.join(_backup_folder(), filename)

    if os.path.exists(path):
        try:
            os.remove(path)
            flash(_("Backup %(filename)s dihapus.", filename=filename), "success")
        except OSError:
            flash(_("Gagal menghapus file backup (mungkin sedang dipakai)."), "danger")

    return redirect(url_for("staff.admin_system"))
