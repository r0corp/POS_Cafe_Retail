import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from flask_login import UserMixin
from flask_babel import lazy_gettext as _l
from werkzeug.security import generate_password_hash, check_password_hash

from . import db

def calculate_ppn(subtotal, percentage):
    """Nominal PPN (Rupiah bulat) dari subtotal - dibulatkan setengah ke
    ATAS (16,5 -> 17), bukan round() bawaan Python yang membulatkan ke
    angka genap terdekat (16,5 -> 16). Dihitung pakai Decimal supaya
    tidak kena galat floating point (mis. 11% dari 150 = 16,500000001)."""

    if not subtotal or not percentage:
        return 0
    amount = Decimal(int(subtotal)) * Decimal(str(percentage)) / Decimal(100)
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


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

    # Dinaikkan tiap kali Owner klik "Bersihkan Cache" - ditempel sebagai
    # query string (?v=) ke semua file static, supaya browser ambil
    # ulang file terbaru (logo/foto/QR) bukan versi lama yang ke-cache.
    cache_version = db.Column(db.Integer, nullable=False, default=1)

    # Notifikasi suara - aktif/nonaktif & volume masih 1 pengaturan
    # bersama buat semua role, tapi NADA-nya sengaja dipisah per role
    # (lihat 3 kolom notification_sound_* di bawah) supaya tiap jenis
    # staf bisa dikenali dari bunyi device-nya sendiri kalau beberapa
    # device nyala bareng di toko. notification_sound ini jadi nada
    # untuk role Owner SEKALIGUS fallback kalau role lain belum
    # ditentukan nadanya secara eksplisit oleh Owner.
    notification_enabled = db.Column(db.Boolean, nullable=False, default=True)
    notification_sound = db.Column(db.String(30), nullable=False, default="bell_double")
    notification_volume = db.Column(db.Integer, nullable=False, default=70)

    notification_sound_dapur = db.Column(db.String(30), nullable=True)
    notification_sound_kasir = db.Column(db.String(30), nullable=True)
    notification_sound_pelayan = db.Column(db.String(30), nullable=True)

    # Nada dering sendiri (upload .mp3/.wav/.ogg/.m4a) - dipilih dengan
    # notification_sound="custom". Kalau kosong/belum upload, "custom"
    # otomatis fallback ke nada default (lihat notify.js). Dipakai
    # bersama oleh role manapun yang nadanya diset "custom".
    notification_sound_file = db.Column(db.String(255))

    # Logo kotak/persegi - dipakai di navbar & halaman login.
    logo_square = db.Column(db.String(255))

    # Logo lebar/panjang - dipakai di header menu tamu & (nanti) struk.
    logo_wide = db.Column(db.String(255))

    # Pilihan logo mana ("square"/"wide") yang dipakai di tiap konteks -
    # supaya toko yang cuma punya 1 jenis logo tetap bisa pakai itu di
    # mana saja, tanpa wajib upload dua-duanya.
    app_logo_choice = db.Column(db.String(10), nullable=False, default="square")
    login_logo_choice = db.Column(db.String(10), nullable=False, default="square")
    receipt_logo_choice = db.Column(db.String(10), nullable=False, default="wide")

    # Tampilan navbar setelah login: "logo" (cuma logo), "name" (cuma
    # nama toko), atau "both" (logo + nama).
    navbar_display = db.Column(db.String(10), nullable=False, default="both")

    # Lebar kertas printer thermal dalam mm, salah satu dari
    # RECEIPT_PAPER_WIDTHS di atas - menentukan ukuran halaman cetak
    # struk. 58mm dipakai sebagai default karena printer thermal
    # ukuran itu yang paling umum dipakai UMKM/warkop.
    receipt_paper_width = db.Column(db.String(5), nullable=False, default="58")

    # Ketebalan teks struk ("thin"/"normal"/"bold", lihat
    # RECEIPT_PRINT_WEIGHTS) - printer thermal yang head-nya sudah agak
    # aus sering mencetak terlalu tipis/pudar walau tintanya (panasnya)
    # sebenarnya cukup, jadi toko butuh cara menebalkan tampilan tanpa
    # ganti/servis printer. "normal" = tampilan default (cuma judul &
    # total yang bold, seperti sebelum fitur ini ada).
    receipt_print_weight = db.Column(db.String(10), nullable=False, default="normal")

    # Sistem PPN (Pajak Pertambahan Nilai) - kalau aktif, dihitung dari
    # persentase ini dan ditambahkan otomatis ke total tagihan saat bayar
    # sampai ke struk. Tiap Order menyimpan snapshot persen & nominalnya
    # sendiri saat dibayar, supaya riwayat/laporan lama tidak berubah
    # kalau persentase PPN diedit belakangan.
    ppn_enabled = db.Column(db.Boolean, nullable=False, default=False)
    ppn_percentage = db.Column(db.Float, nullable=False, default=11.0)

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

    # Nama & password WiFi toko - ditampilkan di kartu cetak QR meja
    # (sebelum ajakan "Scan untuk pesan"), soalnya aplikasi ini diakses
    # lewat jaringan LOKAL (bukan internet publik) - tamu wajib nyambung
    # ke WiFi toko dulu sebelum QR-nya bisa dibuka. Kosong berarti
    # blok WiFi tidak ditampilkan sama sekali di kartu QR.
    wifi_name = db.Column(db.String(100))
    wifi_password = db.Column(db.String(100))

    # Snapshot JSON identitas toko asli (nama, alamat, kontak, nama file
    # logo) - dibuat OTOMATIS sesaat sebelum Mode Demo menimpa field-field
    # itu dengan konten contoh (lihat staff._seed_demo_data()), dan dipakai
    # buat kembalikan persis seperti semula saat Mode Demo dimatikan (lihat
    # staff._clear_demo_data()). Kosong berarti tidak sedang ada demo aktif.
    demo_settings_backup = db.Column(db.Text, nullable=True)

    # Kill switch buat perbaikan kode di server produksi - saat True,
    # semua role SELAIN Owner (termasuk pengunjung yang belum login) akan
    # melihat halaman "Sedang Dalam Perbaikan" (lihat app/__init__.py:
    # check_maintenance_mode()), sementara Owner tetap bisa pakai aplikasi
    # seperti biasa buat menguji perubahan sebelum dinyalakan ke semua orang.
    maintenance_mode = db.Column(db.Boolean, nullable=False, default=False)

    def _pick_logo(self, choice):
        if choice == "square":
            return self.logo_square or self.logo_wide
        return self.logo_wide or self.logo_square

    @property
    def app_logo_filename(self):
        """Logo dipakai di navbar (setelah login) & menu tamu."""
        return self._pick_logo(self.app_logo_choice)

    @property
    def login_logo_filename(self):
        """Logo dipakai khusus di halaman login."""
        return self._pick_logo(self.login_logo_choice)

    @property
    def receipt_logo_filename(self):
        """Logo dipakai di struk penjualan."""
        return self._pick_logo(self.receipt_logo_choice)

    def notification_sound_for_role(self, role):
        """Nada notifikasi yang dipakai role tertentu - Owner atur semuanya
        dari Pengaturan, staf tidak bisa ganti sendiri. Role yang belum
        pernah ditentukan nadanya (masih kosong) otomatis ikut nada Owner
        (notification_sound) sebagai fallback."""

        role_field = {
            ROLE_DAPUR: self.notification_sound_dapur,
            ROLE_KASIR: self.notification_sound_kasir,
            ROLE_PELAYAN: self.notification_sound_pelayan,
        }.get(role)

        return role_field or self.notification_sound

    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, default=0)

    # True kalau baris ini bagian dari "Mode Demo" (lihat blueprints/staff.py
    # demo_mode_toggle) - dibedakan dari data asli toko supaya bisa
    # dihapus lagi secara aman tanpa menyentuh data yang beneran diisi
    # owner.
    is_demo = db.Column(db.Boolean, default=False, nullable=False)

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
    is_demo = db.Column(db.Boolean, default=False, nullable=False)

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


class Floor(db.Model):
    """Nama custom per lantai bangunan, diatur Owner lewat Pengaturan
    Toko - "number" cuma penanda biasa (BUKAN foreign key ke Table.floor)
    supaya data meja lama tetap jalan apa adanya tanpa migrasi, tinggal
    dicocokkan lewat floor_display_name() di bawah."""

    __tablename__ = "floors"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False, unique=True)
    name = db.Column(db.String(50), nullable=False)

    # Sama polanya dengan Category/MenuItem/Table/Ingredient/OrderChannel -
    # ditandai True kalau lantai ini dibuat Mode Demo, supaya bisa
    # dihapus lagi otomatis lewat staff._clear_demo_data() tanpa
    # menyentuh lantai asli toko.
    is_demo = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("0"))

    def __repr__(self):
        return f"<Floor {self.number}: {self.name}>"


def floor_display_name(number):
    """Nama lantai yang ditampilkan - pakai nama custom dari Pengaturan
    kalau sudah diatur Owner, atau fallback "Lantai N" polos kalau
    nomor lantai itu belum pernah dikasih nama custom."""

    floor = Floor.query.filter_by(number=number).first()
    if floor and floor.name:
        return floor.name
    return _l("Lantai %(number)s", number=number)


class Table(db.Model):
    __tablename__ = "tables"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    label = db.Column(db.String(50), nullable=False)
    floor = db.Column(db.Integer, nullable=False, default=1)

    # Ditandai True kalau meja ini dibuat oleh Mode Demo (lihat
    # staff._seed_demo_data()) - supaya bisa dihapus bersih lagi saat
    # demo dimatikan, tanpa menyentuh meja asli toko (is_demo=False).
    is_demo = db.Column(db.Boolean, default=False, nullable=False)

    orders = db.relationship("Order", backref="table")

    @property
    def floor_label(self):
        return floor_display_name(self.floor)

    def __repr__(self):
        return f"<Table {self.label}>"


def generate_order_pin():
    """PIN 4 digit acak buat 1 pesanan baru - lihat kolom Order.pin."""

    return f"{random.randint(0, 9999):04d}"


# Batas atas jumlah 1 item per pesanan - menangkal salah ketik (mis.
# "1000" padahal maksudnya "10") dan input iseng yang bikin total
# tagihan tidak masuk akal / overflow di database.
MAX_ITEM_QUANTITY = 99


def parse_quantity_fields(form):
    """Baca semua field qty_<menu_item_id> dari form pesanan (staff & tamu),
    balikin list (menu_item_id, quantity) yang valid saja. Field yang
    rusak/iseng (id bukan angka, jumlah bukan angka, <= 0) di-skip diam-
    diam, bukan bikin error 500; jumlah di atas MAX_ITEM_QUANTITY
    dipotong ke batas itu."""

    parsed = []

    for key, value in form.items():
        if not key.startswith("qty_"):
            continue

        raw_id = key[len("qty_"):]
        raw_qty = (value or "").strip()
        if not raw_id.isascii() or not raw_id.isdigit() or len(raw_id) > 9:
            continue
        if not raw_qty.isascii() or not raw_qty.isdigit():
            continue

        quantity = int(raw_qty[:6])
        if quantity <= 0:
            continue

        parsed.append((int(raw_id), min(quantity, MAX_ITEM_QUANTITY)))

    return parsed


ORDER_TYPE_DINE_IN = "dine_in"
ORDER_TYPE_TAKEAWAY = "takeaway"
ORDER_TYPE_OJOL = "ojol"

ORDER_TYPES = [ORDER_TYPE_DINE_IN, ORDER_TYPE_TAKEAWAY, ORDER_TYPE_OJOL]

ORDER_TYPE_LABELS = {
    ORDER_TYPE_DINE_IN: _l("Makan di Tempat"),
    ORDER_TYPE_TAKEAWAY: _l("Bawa Pulang"),
    ORDER_TYPE_OJOL: _l("Ojek Online"),
}

CHANNEL_PRICING_PERCENT = "percent"
CHANNEL_PRICING_MANUAL = "manual"

# Pilihan lebar kertas struk (mm) - dua ukuran roll umum (58mm/80mm),
# plus varian "area cetak sempit"-nya. Banyak printer thermal murah
# punya lebar kertas fisik 58mm/80mm tapi area cetak sebenarnya lebih
# sempit (48mm/72mm), jadi struk kepotong di pinggir kanan kalau
# lebar halaman disamakan dengan lebar kertas fisik. Nilai = font
# size PDF (px CSS-nya diatur terpisah di receipt.html).
RECEIPT_PAPER_WIDTHS = {
    "48": 7,
    "58": 8,
    "72": 8.5,
    "80": 9,
}

# Opsi ketebalan cetak struk, urut dari paling tipis ke paling tebal.
RECEIPT_PRINT_WEIGHTS = ["thin", "normal", "bold"]

RECEIPT_PRINT_WEIGHT_LABELS = {
    "thin": _l("Tipis"),
    "normal": _l("Sedang"),
    "bold": _l("Tebal"),
}


class OrderChannel(db.Model):
    """Platform pesan-antar pihak ketiga (GrabFood, ShopeeFood, dst) -
    daftar bebas ditambah Owner lewat Pengaturan > Platform Delivery, BUKAN
    daftar hardcode, supaya platform baru bisa ditambah tanpa ubah kode.
    Setiap platform punya harga sendiri: markup persentase otomatis
    dari harga menu biasa, atau harga manual per item (lihat
    MenuItemChannelPrice & price_for() di bawah)."""

    __tablename__ = "order_channels"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    logo = db.Column(db.String(255))
    pricing_mode = db.Column(db.String(10), nullable=False, default=CHANNEL_PRICING_PERCENT)
    markup_percent = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    # True kalau baris ini dibuat oleh Mode Demo (lihat staff._seed_demo_data())
    # - dibedakan dari platform asli yang ditambah Owner sendiri, supaya bisa
    # dihapus lagi dengan bersih saat demo dimatikan tanpa menyentuh platform
    # sungguhan yang sudah diatur toko.
    is_demo = db.Column(db.Boolean, default=False, nullable=False)

    custom_prices = db.relationship(
        "MenuItemChannelPrice", backref="channel", cascade="all, delete-orphan"
    )

    def price_for(self, menu_item):
        """Harga menu_item kalau dipesan lewat platform ini - manual
        (dari MenuItemChannelPrice, fallback ke harga toko biasa kalau
        item itu belum diisi harganya) atau markup persentase otomatis."""

        if self.pricing_mode == CHANNEL_PRICING_MANUAL:
            row = MenuItemChannelPrice.query.filter_by(
                channel_id=self.id, menu_item_id=menu_item.id
            ).first()
            return row.price if row else menu_item.price

        markup = self.markup_percent or 0
        return menu_item.price + round(menu_item.price * markup / 100)

    def __repr__(self):
        return f"<OrderChannel {self.name}>"


class MenuItemChannelPrice(db.Model):
    """Harga manual 1 menu khusus 1 platform ojol - cuma dipakai kalau
    OrderChannel.pricing_mode == "manual". Item yang belum punya baris
    di sini otomatis pakai harga toko biasa sebagai fallback (lihat
    OrderChannel.price_for)."""

    __tablename__ = "menu_item_channel_prices"
    __table_args__ = (db.UniqueConstraint("menu_item_id", "channel_id"),)

    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_items.id"), nullable=False)
    channel_id = db.Column(db.Integer, db.ForeignKey("order_channels.id"), nullable=False)
    price = db.Column(db.Integer, nullable=False)

    menu_item = db.relationship("MenuItem")


class Order(db.Model):
    __tablename__ = "orders"

    # Kunci di level database: 1 meja cuma boleh punya 1 pesanan yang
    # belum lunas dalam satu waktu. Jaring pengaman terakhir kalau ada
    # 2 pesanan nyaris bersamaan lolos dari pengecekan di kode (staff.py
    # new_order() & public.py submit_order()) - percobaan insert kedua
    # akan gagal dengan IntegrityError, ditangkap & ditangani di sana.
    # Syarat "table_id IS NOT NULL" sengaja ditambahkan supaya pesanan
    # Bawa Pulang/Ojek Online (table_id kosong) tidak ikut kena kunci
    # ini - boleh ada banyak sekaligus tanpa dianggap "tabrakan meja".
    __table_args__ = (
        db.Index(
            "ux_one_unpaid_order_per_table",
            "table_id",
            unique=True,
            sqlite_where=db.text("is_paid = 0 AND table_id IS NOT NULL"),
        ),
        # AUTOINCREMENT supaya ID pesanan yang dibatalkan (dihapus) tidak
        # pernah dipakai ulang - tanpa ini SQLite kasih pesanan berikutnya
        # max(id)+1, dan HP tamu lama yang masih buka halaman status
        # pesanan #N bisa tiba-tiba melihat pesanan tamu lain.
        {"sqlite_autoincrement": True},
    )

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey("tables.id"), nullable=True)

    # "qr" = tamu submit sendiri dari HP, "staff" = diinput pelayan.
    source = db.Column(db.String(10), nullable=False, default="staff")

    # Makan di Tempat (butuh meja) / Bawa Pulang / Ojek Online (keduanya
    # tidak butuh meja - lihat ORDER_TYPE_*, table_id boleh kosong).
    order_type = db.Column(db.String(10), nullable=False, default=ORDER_TYPE_DINE_IN)
    channel_id = db.Column(db.Integer, db.ForeignKey("order_channels.id"), nullable=True)
    channel = db.relationship("OrderChannel")

    status = db.Column(db.String(20), nullable=False, default="pending")

    is_paid = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(10))
    paid_at = db.Column(db.DateTime)
    served_by = db.Column(db.String(50))  # username kasir yang memproses bayar

    # PIN 4 digit acak - device yang bikin pesanan ini (atau berhasil input
    # PIN yang benar) baru boleh ikut nambah menu ke pesanan yang sama.
    # Lihat _is_unlocked()/generate_order_pin() di blueprints/public.py.
    pin = db.Column(db.String(4))

    # Cuma diisi untuk pembayaran cash - dipakai buat hitung & tampilkan
    # kembalian di struk/riwayat, tidak relevan untuk QRIS.
    cash_received = db.Column(db.Integer)
    change_amount = db.Column(db.Integer)

    # Snapshot ketentuan PPN saat pembayaran dikonfirmasi (bukan saat
    # order dibuat) - dipakai bareng cash_received/change_amount, supaya
    # struk & laporan lama tetap akurat walau persentase PPN di
    # Pengaturan diubah belakangan. Tetap None untuk order yang belum
    # dibayar atau dibayar sebelum fitur PPN ada.
    ppn_percentage = db.Column(db.Float)
    ppn_amount = db.Column(db.Integer)

    created_at = db.Column(db.DateTime, default=datetime.now)

    items = db.relationship(
        "OrderItem", backref="order", cascade="all, delete-orphan"
    )
    stock_deductions = db.relationship(
        "OrderStockDeduction", backref="order", cascade="all, delete-orphan"
    )

    @property
    def total(self):
        return sum(item.subtotal for item in self.items)

    @property
    def grand_total(self):
        """Total akhir yang harus dibayar tamu, termasuk PPN kalau
        aktif. Order yang sudah lunas pakai snapshot PPN saat dibayar;
        order yang belum lunas dihitung "live" pakai ketentuan PPN yang
        berlaku sekarang, supaya preview totalnya selalu up-to-date."""

        if self.is_paid:
            return self.total + (self.ppn_amount or 0)

        settings = Settings.query.order_by(Settings.id.asc()).first()
        if settings and settings.ppn_enabled and settings.ppn_percentage:
            return self.total + calculate_ppn(self.total, settings.ppn_percentage)

        return self.total

    @classmethod
    def occupying_table_query(cls):
        """Pesanan yang masih "menempati" mejanya - belum lunas, ATAU
        sudah lunas tapi makanan/minumannya belum full diantar (status
        belum "served"). Sengaja BUKAN cuma is_paid=False - kalau kasir
        terima bayar duluan sementara dapur belum selesai masak/antar,
        meja itu tidak boleh langsung dianggap kosong buat tamu baru,
        supaya dapur/pelayan tidak bingung pesanan lama vs baru numpuk
        di meja yang sama. Dipakai bareng oleh staff.table_map(),
        staff.tables_status(), staff.new_order(), dan
        public._active_order_for_table()."""

        return cls.query.filter(
            db.or_(cls.is_paid.is_(False), cls.status != "served")
        )

    @property
    def status_label(self):
        return ORDER_STATUS_LABELS.get(self.status, self.status)

    @property
    def display_label(self):
        """Pengganti "Meja X" untuk pesanan tanpa meja (Bawa Pulang/Ojek
        Online) - dipakai di kartu Dapur/Pelayan/Kasir & struk supaya
        template tidak perlu tahu lagi soal table_id yang boleh kosong."""

        if self.table:
            return self.table.label
        if self.order_type == ORDER_TYPE_OJOL and self.channel:
            return self.channel.name
        return str(ORDER_TYPE_LABELS.get(self.order_type, self.order_type))

    @property
    def display_sublabel(self):
        if self.table:
            return self.table.floor_label
        return str(ORDER_TYPE_LABELS.get(self.order_type, ""))

    def __repr__(self):
        return f"<Order #{self.id} - {self.display_label}>"


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

    # True kalau item ini SUDAH dikerjakan dapur sebelum tamu menambah
    # menu lain ke pesanan yang sama (lihat public.add_to_order) - pesanan
    # dibalikin ke "pending" supaya tambahannya kelihatan di Dapur, tapi
    # item lama ini ditampilkan sebagai "sudah dibuat" supaya tidak ikut
    # dimasak ulang.
    kitchen_done = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("0"))

    @property
    def subtotal(self):
        return self.price_snapshot * self.quantity


class CancelledOrderLog(db.Model):
    """Jejak setiap pesanan yang dibatalkan kasir/owner (lihat
    staff.cancel_order). Pesanannya sendiri dihapus supaya tidak ikut
    laporan penjualan, tapi catatan ini tetap ada - Owner bisa lihat siapa
    membatalkan apa, kapan, dan berapa nilainya di halaman Laporan (cegah
    uang tunai diterima lalu pesanannya "dibatalkan" tanpa jejak)."""

    __tablename__ = "cancelled_order_logs"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, nullable=False)  # bukan FK - order-nya sudah dihapus
    label = db.Column(db.String(150), nullable=False)
    order_type = db.Column(db.String(10))
    items_summary = db.Column(db.Text, nullable=False)
    total = db.Column(db.Integer, nullable=False, default=0)
    status_at_cancel = db.Column(db.String(20), nullable=False)
    stock_restored = db.Column(db.Boolean, nullable=False, default=False)
    order_created_at = db.Column(db.DateTime)
    cancelled_by = db.Column(db.String(50), nullable=False)
    cancelled_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)

    @property
    def status_label(self):
        return ORDER_STATUS_LABELS.get(self.status_at_cancel, self.status_at_cancel)


class OrderStockDeduction(db.Model):
    """Catatan berapa stok bahan baku yang BENAR-BENAR dipotong untuk 1
    order (lihat inventory.check_and_deduct_stock). Dipakai saat order
    dibatalkan supaya yang dikembalikan persis sama dengan yang dipotong -
    bukan dihitung ulang dari resep saat ini, yang bisa saja sudah diubah
    Owner di antara pesanan dibuat dan dibatalkan."""

    __tablename__ = "order_stock_deductions"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey("ingredients.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)


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
    is_demo = db.Column(db.Boolean, default=False, nullable=False)

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
