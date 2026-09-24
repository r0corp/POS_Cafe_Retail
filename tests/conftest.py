"""Fixture bersama buat semua test - lihat README.md di folder ini
untuk cara jalanin test-nya.

PENTING: env var di bawah harus di-set SEBELUM `app`/`config` pernah
di-import di mana pun (termasuk oleh pytest plugin lain), soalnya
config.py baca os.environ SEKALI SAJA di level modul, bukan di dalam
fungsi. DATABASE_URL khususnya wajib sudah menunjuk ke file test
SEBELUM create_app() dipanggil pertama kali - kalau telat, aplikasi
bisa mulai nyambung ke database production yang beneran."""

import os
import tempfile

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("CAFE_NAME", "Test Cafe")
os.environ.setdefault("BASE_URL", "http://testserver")

import pytest

from app import create_app
from app import db as _db
from app.models import (
    ROLE_OWNER,
    ROLE_KASIR,
    Category,
    Ingredient,
    MenuItem,
    MenuItemIngredient,
    Table,
    User,
)


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    flask_app = create_app(config_overrides={
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })

    yield flask_app

    with flask_app.app_context():
        # Tutup semua koneksi dulu - kalau tidak, Windows menolak hapus
        # file .db-nya karena masih dianggap "in use" oleh proses ini.
        _db.session.remove()
        _db.engine.dispose()
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def db(app):
    # test_request_context (bukan cuma app_context) supaya kode yang
    # butuh `session`/`request` Flask (mis. flask_babel gettext() lewat
    # get_locale() di app/__init__.py) tidak meledak "Working outside
    # of request context" saat dipanggil langsung dari test tanpa lewat
    # test client sungguhan.
    with app.test_request_context():
        yield _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def owner_user(db):
    user = User(username="owner", role=ROLE_OWNER, is_active_user=True)
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def kasir_user(db):
    user = User(username="kasir", role=ROLE_KASIR, is_active_user=True)
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username, password="secret123"):
    return client.post(
        "/login", data={"username": username, "password": password}, follow_redirects=True
    )


@pytest.fixture
def make_menu_item(db):
    """Factory: bikin 1 kategori + 1 menu item siap pesan, opsional
    dengan resep bahan baku (recipe=[(ingredient, qty_per_porsi), ...])."""

    def _make(name="Kopi Susu", price=15000, recipe=None):
        category = Category(name="Minuman", order=1)
        db.session.add(category)
        db.session.flush()

        item = MenuItem(category_id=category.id, name=name, price=price, is_available=True)
        db.session.add(item)
        db.session.flush()

        for ingredient, qty in (recipe or []):
            db.session.add(
                MenuItemIngredient(menu_item_id=item.id, ingredient_id=ingredient.id, quantity_used=qty)
            )

        db.session.commit()
        return item

    return _make


@pytest.fixture
def make_ingredient(db):
    def _make(name="Kopi Bubuk", unit="gram", stock=1000.0, threshold=100.0):
        ingredient = Ingredient(name=name, unit=unit, stock_quantity=stock, low_stock_threshold=threshold)
        db.session.add(ingredient)
        db.session.commit()
        return ingredient

    return _make


@pytest.fixture
def make_table(db):
    def _make(label="Meja 1", code="postab-1", floor=1):
        table = Table(label=label, code=code, floor=floor)
        db.session.add(table)
        db.session.commit()
        return table

    return _make
