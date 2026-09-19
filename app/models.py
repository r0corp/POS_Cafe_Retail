from datetime import datetime, timedelta

from flask_login import UserMixin
from flask_babel import lazy_gettext as _l
from werkzeug.security import generate_password_hash, check_password_hash

from . import db

# Dianggap "online" kalau ada aktivitas dalam N menit terakhir.
ONLINE_THRESHOLD_MINUTES = 3

ROLE_OWNER = "owner"
ROLE_KASIR = "kasir"
ROLE_DAPUR = "dapur"
ROLE_PELAYAN = "pelayan"

ROLES = [ROLE_OWNER, ROLE_KASIR, ROLE_DAPUR, ROLE_PELAYAN]

ROLE_LABELS = {
    ROLE_OWNER: _l("Owner"),
    ROLE_KASIR: _l("Kasir"),
    ROLE_DAPUR: _l("Dapur"),
    ROLE_PELAYAN: _l("Pelayan"),
}

# Status alur dapur: pesanan diterima -> diproses -> siap -> sudah diantar.
ORDER_STATUSES = ["pending", "processing", "ready", "served"]

ORDER_STATUS_LABELS = {
    "pending": _l("Diterima"),
    "processing": _l("Diproses"),
    "ready": _l("Siap Diantar"),
    "served": _l("Sudah Diantar"),
}

PAYMENT_METHODS = ["cash", "qris"]


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_PELAYAN)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_seen_at = db.Column(db.DateTime)
    photo = db.Column(db.String(255))

    # True sejak login sampai logout eksplisit - dipakai bersama
    # last_seen_at supaya "Terakhir aktif" tetap kelihatan setelah
    # logout (last_seen_at tidak ikut dikosongkan).
    is_logged_in = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        # Nama kolom sengaja "is_active_user" supaya tidak bentrok
        # dengan atribut default UserMixin.is_active.
        return self.is_active_user

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def is_online(self):
        if not self.is_logged_in or not self.last_seen_at:
            return False
        return (datetime.now() - self.last_seen_at) < timedelta(minutes=ONLINE_THRESHOLD_MINUTES)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class LoginLog(db.Model):
    """Catatan login/logout - username disimpan sebagai teks (bukan FK)
    supaya riwayat tetap ada walau akun user-nya belakangan dihapus."""

    __tablename__ = "login_logs"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    event = db.Column(db.String(10), nullable=False)  # "login" / "logout"
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.now)


class Settings(db.Model):
    """Pengaturan identitas toko (nama, logo, footer) - cuma 1 baris
    (singleton), diedit lewat halaman /admin/settings (khusus Owner)."""

    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(100), nullable=False, default="Kafe Saya")
    footer_text = db.Column(db.String(255))

    # Dinaikkan tiap kali Owner klik "Bersihkan Cache" - ditempel sebagai
    # query string (?v=) ke semua file static, supaya browser ambil
    # ulang file terbaru (logo/foto/QR) bukan versi lama yang ke-cache.
    cache_version = db.Column(db.Integer, nullable=False, default=1)

    # Notifikasi suara pesanan baru (halaman Dapur & Kasir).
    notification_enabled = db.Column(db.Boolean, nullable=False, default=True)
    notification_sound = db.Column(db.String(30), nullable=False, default="bell_double")
    notification_volume = db.Column(db.Integer, nullable=False, default=70)

    # Logo kotak/persegi - dipakai di navbar & halaman login.
    logo_square = db.Column(db.String(255))

    # Logo lebar/panjang - dipakai di header menu tamu & (nanti) struk.
    logo_wide = db.Column(db.String(255))

    # Pilihan logo mana ("square"/"wide") yang dipakai di tiap konteks -
    # supaya toko yang cuma punya 1 jenis logo tetap bisa pakai itu di
    # mana saja, tanpa wajib upload dua-duanya.
    app_logo_choice = db.Column(db.String(10), nullable=False, default="square")
    receipt_logo_choice = db.Column(db.String(10), nullable=False, default="wide")

    # Lebar kertas printer thermal ("58" atau "80" mm) - menentukan
    # ukuran halaman cetak struk.
    receipt_paper_width = db.Column(db.String(5), nullable=False, default="80")

    # Gambar QRIS statis/offline milik toko - ditunjukkan ke tamu saat
    # bayar QRIS langsung di meja (tanpa perlu ke kasir).
    qris_image = db.Column(db.String(255))

    # Info kontak & sosial media - dilampirkan di struk pembelian supaya
    # pelanggan gampang follow toko.
    address = db.Column(db.String(255))
    phone = db.Column(db.String(30))
    instagram = db.Column(db.String(100))
    tiktok = db.Column(db.String(100))
    whatsapp = db.Column(db.String(30))
    other_social = db.Column(db.String(255))

    def _pick_logo(self, choice):
        if choice == "square":
            return self.logo_square or self.logo_wide
        return self.logo_wide or self.logo_square

    @property
    def app_logo_filename(self):
        """Logo dipakai di navbar, halaman login, dan menu tamu."""
        return self._pick_logo(self.app_logo_choice)

    @property
    def receipt_logo_filename(self):
        """Logo dipakai di struk penjualan."""
        return self._pick_logo(self.receipt_logo_choice)

    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, default=0)

    items = db.relationship(
        "MenuItem",
        backref="category",
        order_by="MenuItem.name",
    )

    def __repr__(self):
        return f"<Category {self.name}>"


class MenuItem(db.Model):
    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=False
    )
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Integer, nullable=False)  # dalam Rupiah, tanpa desimal
    is_available = db.Column(db.Boolean, default=True)
    photo = db.Column(db.String(255), nullable=True)

    order_items = db.relationship("OrderItem", backref="menu_item")
    recipe = db.relationship(
        "MenuItemIngredient", backref="menu_item", cascade="all, delete-orphan"
    )

    @property
    def is_in_stock(self):
        # Item tanpa resep (belum diatur bahan bakunya) dianggap selalu
        # ada stok - tidak dibatasi inventory sampai ownernya mengatur
        # resep bahan baku untuk item itu.
        if not self.recipe:
            return True
        return all(row.ingredient.stock_quantity >= row.quantity_used for row in self.recipe)

    @property
    def is_orderable(self):
        return self.is_available and self.is_in_stock

    def __repr__(self):
        return f"<MenuItem {self.name}>"


class Table(db.Model):
    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    label = db.Column(db.String(50), nullable=False)
    floor = db.Column(db.Integer, nullable=False, default=1)

    orders = db.relationship("Order", backref="table")

    def __repr__(self):
        return f"<Table {self.label}>"


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey("tables.id"), nullable=False)

    # "qr" = tamu submit sendiri dari HP, "staff" = diinput pelayan.
    source = db.Column(db.String(10), nullable=False, default="staff")

    status = db.Column(db.String(20), nullable=False, default="pending")

    is_paid = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(10))
    paid_at = db.Column(db.DateTime)
    served_by = db.Column(db.String(50))  # username kasir yang memproses bayar

    # Cuma diisi untuk pembayaran cash - dipakai buat hitung & tampilkan
    # kembalian di struk/riwayat, tidak relevan untuk QRIS.
    cash_received = db.Column(db.Integer)
    change_amount = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.now)

    items = db.relationship(
        "OrderItem", backref="order", cascade="all, delete-orphan"
    )

    @property
    def total(self):
        return sum(item.subtotal for item in self.items)

    @property
    def status_label(self):
        return ORDER_STATUS_LABELS.get(self.status, self.status)

    def __repr__(self):
        return f"<Order #{self.id} - {self.table.label if self.table else '?'}>"


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"))

    # Snapshot nama & harga saat order dibuat, supaya laporan lama tetap
    # akurat walau harga/nama menu berubah belakangan.
    name_snapshot = db.Column(db.String(150), nullable=False)
    price_snapshot = db.Column(db.Integer, nullable=False)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.String(200))

    @property
    def subtotal(self):
        return self.price_snapshot * self.quantity


class Ingredient(db.Model):
    """Bahan baku (kopi, susu, gula, dst) - stoknya otomatis berkurang
    tiap ada pesanan lewat resep yang diatur di MenuItemIngredient."""

    __tablename__ = "ingredients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    unit = db.Column(db.String(20), nullable=False)  # gram, ml, pcs, dst
    stock_quantity = db.Column(db.Float, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Float, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    def __repr__(self):
        return f"<Ingredient {self.name}>"


class MenuItemIngredient(db.Model):
    """Satu baris resep: 1 unit menu_item butuh quantity_used dari 1
    ingredient tertentu. Beberapa baris per menu_item = resep lengkap."""

    __tablename__ = "menu_item_ingredients"

    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    quantity_used = db.Column(db.Float, nullable=False)

    ingredient = db.relationship("Ingredient", backref="recipe_usages")

    def __repr__(self):
        return f"<MenuItemIngredient menu={self.menu_item_id} ingredient={self.ingredient_id}>"
