"""Ganti password sendiri + Owner mengatur ulang password staf."""

import pytest

from app import rate_limit
from app.models import ROLE_KASIR, User

from .conftest import login


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    # Penghitung percobaan gagal ada di memori proses; id user di tiap test
    # sama (database baru), jadi bersihkan supaya antar-test tidak saling kunci.
    rate_limit._attempts.clear()
    yield
    rate_limit._attempts.clear()


def _change(client, current, new, confirm=None):
    return client.post(
        "/account/password",
        data={"current_password": current, "new_password": new, "confirm_password": new if confirm is None else confirm},
        follow_redirects=True,
    )


def test_requires_login(client):
    resp = client.get("/account/password")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_page_and_profile_link(client, owner_user):
    login(client, "owner")
    assert b"Password lama" in client.get("/account/password").data
    assert b"/account/password" in client.get("/").data


def test_change_password_success(client, owner_user, db):
    login(client, "owner")
    resp = _change(client, "secret123", "rahasiabaru")
    assert b"Password berhasil diganti" in resp.data
    db.session.refresh(owner_user)
    assert owner_user.check_password("rahasiabaru")
    assert not owner_user.check_password("secret123")

    other = client.application.test_client()
    assert login(other, "owner", "secret123").status_code == 200  # balik ke halaman login
    resp = other.post("/login", data={"username": "owner", "password": "rahasiabaru"})
    assert resp.status_code == 302


@pytest.mark.parametrize(
    "current,new,confirm,message",
    [
        ("salah", "rahasiabaru", None, b"Password saat ini salah"),
        ("secret123", "abc", None, b"minimal 6"),
        ("secret123", "rahasiabaru", "beda12345", b"Konfirmasi password baru tidak sama"),
        ("secret123", "secret123", None, b"harus berbeda"),
    ],
)
def test_change_password_rejected(client, owner_user, db, current, new, confirm, message):
    login(client, "owner")
    resp = _change(client, current, new, confirm)
    assert message in resp.data
    db.session.refresh(owner_user)
    assert owner_user.check_password("secret123")


def test_change_password_blocked_after_repeated_failures(client, owner_user):
    login(client, "owner")
    for _ in range(rate_limit_attempts()):
        _change(client, "salah", "rahasiabaru")
    resp = _change(client, "secret123", "rahasiabaru")
    assert b"Terlalu banyak percobaan" in resp.data


def rate_limit_attempts():
    from app.blueprints.staff import PASSWORD_CHANGE_ATTEMPTS

    return PASSWORD_CHANGE_ATTEMPTS


def test_owner_resets_staff_password(client, owner_user, kasir_user, db):
    login(client, "owner")
    resp = client.post(f"/admin/users/{kasir_user.id}/password", data={"new_password": "kasirbaru"}, follow_redirects=True)
    assert b"berhasil diatur ulang" in resp.data
    db.session.refresh(kasir_user)
    assert kasir_user.check_password("kasirbaru")


def test_reset_rejects_short_password(client, owner_user, kasir_user, db):
    login(client, "owner")
    resp = client.post(f"/admin/users/{kasir_user.id}/password", data={"new_password": "123"}, follow_redirects=True)
    assert b"minimal 6" in resp.data
    db.session.refresh(kasir_user)
    assert kasir_user.check_password("secret123")


def test_staff_cannot_reset_passwords(client, owner_user, kasir_user, db):
    login(client, "kasir")
    resp = client.post(f"/admin/users/{owner_user.id}/password", data={"new_password": "retas12345"})
    assert resp.status_code in (302, 403)
    db.session.refresh(owner_user)
    assert owner_user.check_password("secret123")


def test_owner_cannot_reset_own_password_through_admin_route(client, owner_user, db):
    login(client, "owner")
    client.post(f"/admin/users/{owner_user.id}/password", data={"new_password": "lewatadmin"})
    db.session.refresh(owner_user)
    assert owner_user.check_password("secret123")


def test_add_user_requires_minimum_length(client, owner_user):
    login(client, "owner")
    resp = client.post("/admin/users", data={"username": "baru", "password": "123", "role": ROLE_KASIR}, follow_redirects=True)
    assert b"minimal 6" in resp.data
    assert User.query.filter_by(username="baru").first() is None
