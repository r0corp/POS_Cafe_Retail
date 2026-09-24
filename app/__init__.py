from datetime import datetime

from flask import Flask, flash, g, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, logout_user
from flask_babel import Babel
from flask_babel import lazy_gettext as _l
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
babel = Babel()
csrf = CSRFProtect()

SUPPORTED_LANGUAGES = ["id", "en"]
DEFAULT_LANGUAGE = "id"


def _same_host_referrer():
    """Referrer cuma dipakai sebagai tujuan redirect kalau masih di host
    aplikasi ini sendiri - bukan situs luar (open redirect)."""

    from urllib.parse import urlparse

    referrer = request.referrer
    if not referrer:
        return None
    parsed = urlparse(referrer)
    if parsed.netloc and parsed.netloc != request.host:
        return None
    return referrer


def get_locale():
    return session.get("lang", DEFAULT_LANGUAGE)


def _add_missing_columns(cur):
    """Kolom yang ada di model tapi belum ada di tabel database lama
    ditambahkan lewat ALTER TABLE ADD COLUMN (SQLite mendukung ini tanpa
    rebuild tabel). Kolom NOT NULL wajib punya server_default di model -
    kalau tidak, ditambahkan sebagai kolom yang boleh kosong supaya ALTER-
    nya tidak gagal untuk baris yang sudah ada."""

    for table in db.metadata.sorted_tables:
        existing = {row[1] for row in cur.execute(f'PRAGMA table_info("{table.name}")').fetchall()}
        if not existing:
            continue  # tabel baru - sudah dibuat utuh oleh create_all()

        for column in table.columns:
            if column.name in existing:
                continue

            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column.type.compile(db.engine.dialect)}'
            if column.server_default is not None:
                default_sql = str(column.server_default.arg.compile(dialect=db.engine.dialect)) \
                    if hasattr(column.server_default.arg, "compile") else repr(column.server_default.arg)
                ddl += f" DEFAULT {default_sql}"
                if not column.nullable:
                    ddl += " NOT NULL"
            cur.execute(ddl)


def _ensure_schema():
    """Aplikasi ini tidak pakai migration (lihat DEPLOYMENT.md), jadi
    perubahan skema dirapikan di sini tiap start - aman dipanggil berkali-
    kali, cuma bekerja kalau memang ada yang belum sesuai:

    1. db.create_all() - bikin tabel yang BELUM ADA saja (mis. tabel baru
       order_stock_deductions di database lama). Tabel yang sudah ada tidak
       disentuh sama sekali, KECUALI kolom baru di model yang belum ada
       di tabel lama - ditambahkan lewat _add_missing_columns().
    2. Tabel orders di database lama dibangun ulang sesuai model kalau:
       - kolom table_id masih NOT NULL (database dibuat sebelum fitur
         Bawa Pulang/Ojek Online - semua pesanan tanpa meja gagal disimpan),
         atau
       - belum AUTOINCREMENT (ID pesanan yang dibatalkan bisa dipakai ulang
         pesanan berikutnya).
       SQLite tidak bisa ALTER COLUMN, jadi pakai prosedur "12 langkah"
       resmi SQLite: tabel baru -> salin data -> hapus lama -> rename.
    3. Index di model (mis. kunci 1 pesanan belum lunas per meja) dibuat
       kalau belum ada."""

    from sqlalchemy.schema import CreateIndex, CreateTable

    from .models import Order

    if db.engine.dialect.name != "sqlite":
        db.create_all()
        return

    db.create_all()

    raw = db.engine.raw_connection()
    try:
        cur = raw.cursor()
        _add_missing_columns(cur)
        raw.commit()

        columns = cur.execute("PRAGMA table_info(orders)").fetchall()
        if not columns:
            return

        create_sql = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='orders'"
        ).fetchone()[0] or ""
        table_id_col = next((c for c in columns if c[1] == "table_id"), None)
        needs_rebuild = (
            (table_id_col is not None and table_id_col[3])  # c[3] = notnull
            or "AUTOINCREMENT" not in create_sql.upper()
        )

        # Transaksi manual (bukan implicit BEGIN bawaan pysqlite yang tidak
        # membungkus DDL) supaya rebuild-nya all-or-nothing.
        driver_conn = raw.driver_connection
        old_isolation = driver_conn.isolation_level
        driver_conn.isolation_level = None
        fk_was_on = cur.execute("PRAGMA foreign_keys").fetchone()[0]
        cur.execute("PRAGMA foreign_keys=OFF")
        try:
            cur.execute("BEGIN")
            try:
                if needs_rebuild:
                    model_columns = [c.name for c in Order.__table__.columns]
                    db_columns = {c[1] for c in columns}
                    shared = [name for name in model_columns if name in db_columns]
                    column_list = ", ".join(f'"{name}"' for name in shared)
                    select_list = ", ".join(
                        'COALESCE("is_paid", 0)' if name == "is_paid" else f'"{name}"'
                        for name in shared
                    )

                    new_sql = str(CreateTable(Order.__table__).compile(db.engine))
                    new_sql = new_sql.replace("CREATE TABLE orders", "CREATE TABLE orders__new", 1)

                    cur.execute("DROP TABLE IF EXISTS orders__new")
                    cur.execute(new_sql)
                    cur.execute(f"INSERT INTO orders__new ({column_list}) SELECT {select_list} FROM orders")
                    cur.execute("DROP TABLE orders")
                    cur.execute("ALTER TABLE orders__new RENAME TO orders")

                for index in Order.__table__.indexes:
                    cur.execute(str(CreateIndex(index, if_not_exists=True).compile(db.engine)))

                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
        finally:
            cur.execute(f"PRAGMA foreign_keys={'ON' if fk_was_on else 'OFF'}")
            driver_conn.isolation_level = old_isolation
    finally:
        raw.close()


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    app.config.setdefault("BABEL_DEFAULT_LOCALE", DEFAULT_LANGUAGE)
    app.config.setdefault("BABEL_TRANSLATION_DIRECTORIES", "translations")

    db.init_app(app)
    migrate.init_app(app, db)
    babel.init_app(app, locale_selector=get_locale)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = _l("Silakan login terlebih dahulu.")
    login_manager.login_message_category = "warning"

    from . import models

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    with app.app_context():
        _ensure_schema()

    from .blueprints.auth import auth_bp
    from .blueprints.public import public_bp
    from .blueprints.staff import staff_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(staff_bp)

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        # Token CSRF hilang/tidak cocok (umumnya session/cookie browser
        # sudah terhapus, atau form dibuka dari tab yang sangat lama) -
        # kasih pesan yang bisa dimengerti + balik ke halaman sebelumnya,
        # bukan halaman "400 Bad Request" mentah berbahasa Inggris.
        flash(_l("Sesi halaman ini sudah kedaluwarsa. Silakan muat ulang halaman lalu coba lagi."), "warning")
        return redirect(_same_host_referrer() or url_for("auth.login"))

    @app.errorhandler(413)
    def too_large(error):
        flash(_l("File yang diupload terlalu besar (maksimal 16 MB)."), "danger")
        return redirect(_same_host_referrer() or url_for("staff.dashboard"))

    @app.errorhandler(500)
    def server_error(error):
        # Rollback dulu - kalau error 500 ini kejadian gara-gara transaksi
        # DB yang setengah jalan, sesi yang masih "kotor" bisa bikin
        # render_template("500.html") sendiri ikut gagal (butuh query
        # Settings lewat context processor).
        db.session.rollback()
        return render_template("500.html"), 500

    @app.route("/set-language/<lang>")
    def set_language(lang):
        from flask import redirect, url_for

        if lang in SUPPORTED_LANGUAGES:
            session["lang"] = lang
            session.permanent = True

        # Kalau browser tidak kirim referrer (umum di beberapa browser/
        # WebView mobile), fallback-nya harus disesuaikan status login -
        # jangan langsung ke Dashboard (butuh login), supaya tidak
        # muncul flash "Silakan login terlebih dahulu" yang membingungkan
        # padahal user cuma ganti bahasa di halaman login.
        default_url = url_for("staff.dashboard") if current_user.is_authenticated else url_for("auth.login")
        return redirect(_same_host_referrer() or default_url)

    @app.route("/manifest.webmanifest")
    def web_manifest():
        # Bikin "Add to Home Screen" di Android/iOS jadi kayak aplikasi asli
        # (icon sendiri, buka langsung tanpa address bar) - tanpa perlu
        # bikin/install .apk sama sekali.
        from .blueprints.staff import get_settings

        settings = get_settings()
        shop_name = settings.shop_name or "Cafe POS"

        manifest = {
            "name": shop_name,
            "short_name": shop_name[:15],
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#0B1220",
            "theme_color": "#F07828",
            "icons": [
                {"src": "/pwa-icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/pwa-icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        return jsonify(manifest), 200, {"Content-Type": "application/manifest+json"}

    @app.route("/pwa-icon-<int:size>.png")
    def pwa_icon(size):
        from flask import abort
        import io
        import os
        from PIL import Image
        from .blueprints.staff import get_settings

        if size not in (192, 512):
            abort(404)

        settings = get_settings()
        canvas = Image.new("RGB", (size, size), (255, 255, 255))  # putih, senada logo

        logo_filename = settings.app_logo_filename
        if logo_filename:
            logo_path = os.path.join(app.static_folder, "uploads", "branding", logo_filename)
            if os.path.exists(logo_path):
                try:
                    logo = Image.open(logo_path).convert("RGBA")
                    max_dim = int(size * 0.72)
                    logo.thumbnail((max_dim, max_dim), Image.LANCZOS)
                    offset = ((size - logo.width) // 2, (size - logo.height) // 2)
                    canvas.paste(logo, offset, logo)
                except OSError:
                    pass

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        buffer.seek(0)
        return send_file(buffer, mimetype="image/png", max_age=3600)

    @app.before_request
    def track_last_seen():
        # Ditulis paling banyak sekali per ~20 detik per user, supaya
        # tidak membanjiri database dengan update di tiap request. File
        # statis (CSS/JS/gambar) dilewati - tidak perlu ikut rebutan kunci
        # tulis SQLite.
        if request.endpoint in (None, "static") or not current_user.is_authenticated:
            return

        now = datetime.now()
        last_seen = current_user.last_seen_at

        if not last_seen or (now - last_seen).total_seconds() > 20:
            current_user.last_seen_at = now
            try:
                db.session.commit()
            except OperationalError:
                # "database is locked" sesaat (ada transaksi lain yang lagi
                # nulis) - cuma penanda "terakhir aktif", jangan sampai
                # bikin request yang sebenarnya jadi error 500.
                db.session.rollback()

    @app.before_request
    def enforce_active_user():
        # Kalau akun di-nonaktifkan (Pengaturan > Kelola Staf) SAAT user itu
        # masih login di device lain, sesi lamanya tidak otomatis mati
        # (cookie login masih valid, hanya toggle di DB) - paksa logout di
        # request berikutnya supaya staf yang dinonaktifkan langsung
        # kehilangan akses, bukan baru berhenti setelah dia logout manual.
        if request.endpoint in (None, "static"):
            return

        if current_user.is_authenticated and not current_user.is_active_user:
            logout_user()
            flash(_l("Akun Anda telah dinonaktifkan. Hubungi Owner."), "danger")
            return redirect(url_for("auth.login"))

    @app.before_request
    def check_maintenance_mode():
        # Kill switch Mode Perbaikan (Pengaturan > Sistem) - dicek di sini
        # (bukan per-blueprint) supaya berlaku ke SEMUA request, termasuk
        # yang belum login. Endpoint di bawah ini selalu boleh lewat, apa
        # pun statusnya, supaya orang yang ke-logout saat maintenance masih
        # bisa login lagi buat mematikannya.
        from .models import ROLE_OWNER

        if request.endpoint in (None, "static", "auth.login", "auth.logout", "set_language"):
            return

        if current_user.is_authenticated and current_user.role == ROLE_OWNER:
            return

        from .blueprints.staff import get_settings

        if get_settings().maintenance_mode:
            return render_template("maintenance.html"), 503

    @app.url_defaults
    def add_cache_buster(endpoint, values):
        # Nempelin ?v=<cache_version> ke semua URL static (logo, foto
        # profil, QRIS, QR meja, css) supaya begitu Owner klik "Bersihkan
        # Cache", browser paksa ambil ulang file terbaru, bukan versi
        # lama yang sempat ke-cache.
        if endpoint != "static" or "v" in values:
            return

        from .blueprints.staff import get_settings

        if "cache_version" not in g:
            try:
                g.cache_version = get_settings().cache_version
            except Exception:
                g.cache_version = 1

        values["v"] = g.cache_version

    @app.context_processor
    def inject_globals():
        from .nav import NAV_ITEMS
        from .blueprints.staff import get_settings
        from .models import ROLE_OWNER, floor_display_name
        from .holidays_id import HOLIDAYS_ID

        online_staff = []

        if current_user.is_authenticated:
            nav_items = [
                item
                for item in NAV_ITEMS
                if item["roles"] is None or current_user.role in item["roles"]
            ]

            if current_user.role == ROLE_OWNER:
                online_staff = [
                    user
                    for user in models.User.query.filter(
                        models.User.id != current_user.id
                    ).all()
                    if user.is_online
                ]
        else:
            nav_items = []

        settings = get_settings()

        return {
            "cafe_name": settings.shop_name,
            "site_settings": settings,
            "now": datetime.now,
            "nav_items": nav_items,
            "online_staff": online_staff,
            "current_lang": get_locale(),
            "holidays_id": HOLIDAYS_ID,
            "floor_display_name": floor_display_name,
        }

    return app
