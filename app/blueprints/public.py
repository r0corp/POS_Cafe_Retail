from flask import Blueprint, abort, flash, render_template, request, redirect, session, url_for
from flask_babel import gettext as _
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError

from .. import db
from ..inventory import check_and_deduct_stock
from ..models import Category, MenuItem, Table, Order, OrderItem, generate_order_pin, parse_quantity_fields
from ..rate_limit import is_blocked, record_failure

public_bp = Blueprint("public", __name__)

# PIN cuma 4 digit (10.000 kombinasi) - batasi percobaan SALAH per
# pesanan (bukan per IP, supaya tidak bisa dihindari dengan ganti-ganti
# IP di jaringan yang sama) supaya tidak bisa di-brute-force dalam waktu
# wajar selama 1 sesi makan.
PIN_RATE_LIMIT = 8
PIN_RATE_WINDOW_SECONDS = 10 * 60

# Maksimal berapa pesanan yang diingat "sudah terbuka" per device -
# cukup buat beberapa kali kunjungan, tanpa bikin cookie session bengkak.
MAX_UNLOCKED_ORDERS = 20


def _mark_unlocked(order):
    """Tandai device ini "kenal" PIN pesanan ini. Disimpan di session
    Flask (cookie yang DITANDATANGANI SECRET_KEY), bukan cookie mentah
    berisi PIN - cookie mentah bisa diisi sendiri oleh siapa saja, jadi
    PIN bisa ditebak 0000-9999 lewat cookie tanpa pernah kena batas
    percobaan di unlock_order()."""

    unlocked = dict(session.get("unlocked_orders") or {})
    unlocked.pop(str(order.id), None)
    unlocked[str(order.id)] = order.pin
    while len(unlocked) > MAX_UNLOCKED_ORDERS:
        unlocked.pop(next(iter(unlocked)))
    session["unlocked_orders"] = unlocked
    session.permanent = True


def _is_unlocked(order):
    """True kalau device ini sudah "kenal" PIN pesanan ini - baik karena
    dia yang bikin pesanan ini sendiri, atau sudah pernah input PIN yang
    benar sebelumnya (lihat unlock_order() di bawah). Pesanan lama
    (dibuat sebelum fitur PIN ada) tidak punya pin sama sekali -
    dianggap selalu terbuka supaya tidak mendadak mengunci pesanan yang
    sedang berjalan."""

    if not order.pin:
        return True
    unlocked = session.get("unlocked_orders") or {}
    return unlocked.get(str(order.id)) == order.pin


def _active_order_for_table(table_id):
    """Pesanan yang masih menempati meja ini (kalau ada - lihat
    Order.occupying_table_query) - dipakai untuk nentuin meja itu masih
    "terisi" atau sudah kosong buat tamu baru."""

    return (
        Order.occupying_table_query()
        .filter(Order.table_id == table_id)
        .order_by(Order.created_at.desc())
        .first()
    )


def _has_orderable_menu(categories):
    """True kalau minimal ada 1 item yang bisa dipesan di seluruh kategori -
    dipakai buat nampilin pesan "menu belum tersedia" daripada halaman
    kosong kalau toko belum sempat isi menu sama sekali."""

    return any(item.is_orderable for category in categories for item in category.items)


def _collect_ordered_items(form):
    """Baca semua field qty_<id> dari form pesanan tamu, balikin
    (list OrderItem baru, list nama menu yang di-skip karena kebetulan
    baru saja dinonaktifkan pemilik pas tamu masih milih-milih)."""

    items = []
    skipped_names = []

    for menu_item_id, quantity in parse_quantity_fields(form):
        menu_item = MenuItem.query.get(menu_item_id)

        if not menu_item:
            # Item ini sudah dihapus permanen (bukan cuma dinonaktifkan)
            # oleh Owner persis selagi tamu masih milih-milih di halaman
            # menu yang lama. Perlakukan sama seperti dinonaktifkan -
            # kasih tahu tamu lewat flash, jangan diam-diam hilang dari
            # pesanan tanpa penjelasan.
            skipped_names.append(_("Menu #%(id)s", id=menu_item_id))
            continue

        if not menu_item.is_orderable:
            skipped_names.append(menu_item.name)
            continue

        items.append(
            OrderItem(
                menu_item_id=menu_item.id,
                name_snapshot=menu_item.name,
                price_snapshot=menu_item.price,
                quantity=quantity,
            )
        )

    return items, skipped_names


def _flash_skipped_items(skipped_names):
    if skipped_names:
        flash(
            _(
                "Menu berikut baru saja tidak tersedia lagi dan tidak jadi ditambahkan: %(names)s.",
                names=", ".join(skipped_names),
            ),
            "warning",
        )


@public_bp.route("/t/<code>")
def menu(code):
    """Halaman menu untuk tamu - dibuka lewat scan QR code di meja. Kalau
    meja masih ada pesanan yang belum lunas, tamu diarahkan ke halaman
    "meja terisi" dulu (bisa lanjut lihat status pesanan itu) - supaya
    tidak numpuk pesanan baru padahal meja masih dipakai tamu lain."""

    table = Table.query.filter_by(code=code).first_or_404()

    active_order = _active_order_for_table(table.id)
    if active_order:
        return render_template("public/occupied.html", table=table, order=active_order)

    categories = (
        Category.query.order_by(Category.order, Category.name).all()
    )

    return render_template(
        "public/menu.html",
        table=table,
        categories=categories,
        has_orderable_menu=_has_orderable_menu(categories),
    )


@public_bp.route("/t/<code>/order", methods=["POST"])
def submit_order(code):
    """Tamu submit pesanan sendiri langsung dari halaman menu (opsional -
    tamu yang tidak nyaman pakai HP tetap bisa dilayani manual oleh
    pelayan lewat halaman staff, lihat blueprints/staff.py)."""

    table = Table.query.filter_by(code=code).first_or_404()

    # Jaga-jaga kalau meja keburu terisi pesanan lain sebelum form ini
    # sempat dikirim (misal dua tamu buka QR yang sama bersamaan).
    active_order = _active_order_for_table(table.id)
    if active_order:
        return redirect(url_for("public.menu", code=code))

    new_items, skipped_names = _collect_ordered_items(request.form)
    _flash_skipped_items(skipped_names)

    if not new_items:
        return redirect(url_for("public.menu", code=code))

    order = Order(table_id=table.id, source="qr", status="pending", pin=generate_order_pin())
    order.items.extend(new_items)

    stock_error = check_and_deduct_stock(order)
    if stock_error:
        flash(stock_error, "danger")
        return redirect(url_for("public.menu", code=code))

    db.session.add(order)
    try:
        db.session.commit()
    except IntegrityError:
        # Jaring pengaman terakhir (dijamin database) - meja ini keburu
        # dapat pesanan lain persis di detik yang sama, lolos dari
        # pengecekan active_order di atas.
        db.session.rollback()
        flash(_("Meja ini baru saja terisi pesanan lain. Silakan panggil pelayan."), "danger")
        return redirect(url_for("public.menu", code=code))

    # Device yang bikin pesanan ini otomatis "kenal" PIN-nya sendiri -
    # tidak perlu input ulang buat nambah menu ke pesanan yang baru saja
    # dia buat sendiri.
    _mark_unlocked(order)
    return redirect(url_for("public.order_status", code=code, order_id=order.id))


@public_bp.route("/t/<code>/order/<int:order_id>/add", methods=["GET", "POST"])
def add_to_order(code, order_id):
    """Tamu yang pesanannya sudah dibuat (lihat status.html) bisa balik ke
    menu dari sini untuk nambah item ke pesanan YANG SAMA, bukan bikin
    pesanan baru - dipakai juga sebagai jalan keluar dari halaman "meja
    terisi" kalau memang itu pesanan tamu itu sendiri."""

    table = Table.query.filter_by(code=code).first_or_404()
    order = Order.query.get_or_404(order_id)

    if order.table_id != table.id:
        abort(404)

    if order.is_paid:
        flash(_("Pesanan ini sudah dibayar, tidak bisa ditambah lagi."), "warning")
        return redirect(url_for("public.order_status", code=code, order_id=order.id))

    # Device ini belum tentu tamu yang sama dengan yang bikin pesanan ini
    # (lihat _is_unlocked) - minta PIN dulu sebelum boleh lihat/isi form
    # tambah menu, supaya orang luar meja yang cuma modal link/kode QR
    # tidak bisa asal nambah ke tagihan orang lain.
    if not _is_unlocked(order):
        if request.method == "POST":
            flash(_("Sesi belum terverifikasi. Masukkan PIN dulu."), "danger")
        return render_template("public/enter_pin.html", table=table, order=order)

    if request.method == "POST":
        new_items, skipped_names = _collect_ordered_items(request.form)
        _flash_skipped_items(skipped_names)

        if not new_items:
            return redirect(url_for("public.add_to_order", code=code, order_id=order.id))

        order_id = order.id
        order.items.extend(new_items)

        stock_error = check_and_deduct_stock(order, items=new_items)
        if stock_error:
            db.session.rollback()
            flash(stock_error, "danger")
            return redirect(url_for("public.add_to_order", code=code, order_id=order_id))

        # Kalau dapur/pelayan sudah mulai/selesai kerjain pesanan ini
        # (status sudah lewat "pending"), item baru ini tidak akan
        # kelihatan kalau statusnya tidak di-reset - dapur bisa saja
        # sudah nganggep pesanan ini "Siap"/"Diantar" dan tidak pernah
        # notice ada tambahan. Balikin ke "pending" supaya muncul lagi
        # sebagai perlu diproses, dan endpoint status poll di bawah
        # bakal bunyikan notifikasi baru buat dapur/kasir.
        #
        # UPDATE ... WHERE is_paid = 0 (bukan andalkan cek order.is_paid
        # di awal fungsi ini, yang sudah basi) - jaga-jaga kasir baru
        # saja proses bayar order ini persis di antara cek awal tadi
        # dengan baris ini. Kalau rowcount 0, batalkan semuanya (item
        # yang barusan ditambah & stok yang barusan dipotong di atas)
        # supaya tidak ada item nyelip masuk ke pesanan yang sudah
        # ditutup/ditagih tanpa pernah ikut tertagih.
        result = db.session.execute(
            Order.__table__.update()
            .where(Order.id == order.id, Order.is_paid.is_(False))
            .values(status="pending")
        )

        if result.rowcount == 0:
            db.session.rollback()
            if Order.query.get(order_id) is None:
                # Keburu dibatalkan kasir persis di detik yang sama.
                flash(_("Pesanan ini sudah dibatalkan. Silakan panggil pelayan."), "warning")
                return redirect(url_for("public.menu", code=code))
            flash(_("Pesanan ini sudah dibayar, tidak bisa ditambah lagi."), "warning")
            return redirect(url_for("public.order_status", code=code, order_id=order_id))

        db.session.commit()

        return redirect(url_for("public.order_status", code=code, order_id=order.id))

    categories = Category.query.order_by(Category.order, Category.name).all()

    return render_template(
        "public/menu.html",
        table=table,
        categories=categories,
        editing_order=order,
        has_orderable_menu=_has_orderable_menu(categories),
    )


@public_bp.route("/t/<code>/order/<int:order_id>/unlock", methods=["POST"])
def unlock_order(code, order_id):
    """Verifikasi PIN yang diketik tamu di enter_pin.html - kalau cocok,
    device ini ditandai "kenal" pesanan ini lewat cookie (lihat
    _is_unlocked) supaya boleh ikut nambah menu."""

    table = Table.query.filter_by(code=code).first_or_404()
    order = Order.query.get_or_404(order_id)

    if order.table_id != table.id:
        abort(404)

    rate_key = f"pin-unlock:{order.id}"
    if is_blocked(rate_key, PIN_RATE_LIMIT, PIN_RATE_WINDOW_SECONDS):
        flash(_("Terlalu banyak percobaan PIN salah. Tunggu beberapa menit lalu coba lagi, atau panggil pelayan."), "danger")
        return redirect(url_for("public.add_to_order", code=code, order_id=order.id))

    pin_input = request.form.get("pin", "").strip()

    if order.pin and pin_input == order.pin:
        _mark_unlocked(order)
        return redirect(url_for("public.add_to_order", code=code, order_id=order.id))

    record_failure(rate_key, PIN_RATE_WINDOW_SECONDS)

    flash(_("PIN salah. Tanya teman semeja Anda yang tadi pesan pertama kali."), "danger")
    return redirect(url_for("public.add_to_order", code=code, order_id=order.id))


@public_bp.route("/t/<code>/status/<int:order_id>")
def order_status(code, order_id):
    """Halaman status pesanan tamu, di-refresh berkala (lihat template)
    supaya tamu tahu progres tanpa harus tanya ke pelayan."""

    table = Table.query.filter_by(code=code).first_or_404()
    order = Order.query.get_or_404(order_id)

    if order.table_id != table.id:
        abort(404)

    # Selama masih "Diterima" (belum mulai dikerjakan dapur), tamu lebih
    # butuh tahu posisi antriannya dulu daripada stepper diterima/diproses/
    # siap/diantar yang belum banyak berubah - dihitung dari semua pesanan
    # lain (meja manapun) yang statusnya masih sama-sama pending dan masuk
    # lebih dulu, sama persis urutan yang dipakai di Antrian Dapur staf.
    queue_position = None
    if order.status == "pending":
        # Tie-break pakai id (urutan insert) kalau kebetulan created_at-nya
        # sama persis, supaya urutan antrian tetap deterministik/tidak ambigu.
        earlier_count = Order.query.filter(
            Order.status == "pending",
            or_(
                Order.created_at < order.created_at,
                and_(Order.created_at == order.created_at, Order.id < order.id),
            ),
        ).count()
        queue_position = earlier_count + 1

    return render_template(
        "public/status.html",
        table=table,
        order=order,
        queue_position=queue_position,
        is_unlocked=_is_unlocked(order),
    )
