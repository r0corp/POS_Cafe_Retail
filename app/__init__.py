from datetime import datetime

from flask import Flask, g, jsonify, render_template, request, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_babel import Babel
from flask_babel import lazy_gettext as _l

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
babel = Babel()

SUPPORTED_LANGUAGES = ["id", "en"]
DEFAULT_LANGUAGE = "id"


def get_locale():
    return session.get("lang", DEFAULT_LANGUAGE)


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    app.config.setdefault("BABEL_DEFAULT_LOCALE", DEFAULT_LANGUAGE)
    app.config.setdefault("BABEL_TRANSLATION_DIRECTORIES", "translations")

    db.init_app(app)
    migrate.init_app(app, db)
    babel.init_app(app, locale_selector=get_locale)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = _l("Silakan login terlebih dahulu.")
    login_manager.login_message_category = "warning"

    from . import models

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    from .blueprints.auth import auth_bp
    from .blueprints.public import public_bp
    from .blueprints.staff import staff_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(staff_bp)

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("403.html"), 403

    @app.route("/set-language/<lang>")
    def set_language(lang):
        from flask import redirect, url_for

        if lang in SUPPORTED_LANGUAGES:
            session["lang"] = lang
            session.permanent = True

        next_url = request.referrer or url_for("staff.dashboard")
        return redirect(next_url)

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
            "background_color": "#4E2F1B",
            "theme_color": "#4E2F1B",
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
        canvas = Image.new("RGB", (size, size), (78, 47, 27))  # var(--color-primary-dark)

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
        # tidak membanjiri database dengan update di tiap request.
        if not current_user.is_authenticated:
            return

        now = datetime.now()
        last_seen = current_user.last_seen_at

        if not last_seen or (now - last_seen).total_seconds() > 20:
            current_user.last_seen_at = now
            db.session.commit()

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
        from .models import ROLE_OWNER

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
        }

    return app
