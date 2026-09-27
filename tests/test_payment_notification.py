"""Tes endpoint notifikasi "uang QRIS masuk" dari listener BCA Merchant
di tablet kasir - lihat receive_payment_notification()/
payment_notification_status() di app/blueprints/staff.py."""

from app.blueprints.staff import get_payment_notify_token
from app.models import PaymentNotification

from .conftest import login


def test_wrong_token_rejected(client, db):
    resp = client.post(
        "/api/payment-notification",
        json={"raw_text": "QRIS diterima Rp 50.000"},
        headers={"X-Payment-Token": "token-salah"},
    )
    assert resp.status_code == 403
    assert PaymentNotification.query.count() == 0


def test_valid_token_qris_amount_parsed(client, db):
    token = get_payment_notify_token()

    resp = client.post(
        "/api/payment-notification",
        json={"raw_text": "Pembayaran QRIS diterima Rp50.000"},
        headers={"X-Payment-Token": token},
    )
    assert resp.status_code == 200
    assert resp.get_json()["amount"] == 50000

    notif = PaymentNotification.query.one()
    assert notif.amount == 50000
    assert "QRIS" in notif.raw_text


def test_non_qris_notification_amount_not_parsed(client, db):
    """Notifikasi BCA lain yang kebetulan menyebut "Rp" (mis. mutasi
    transfer biasa) TIDAK boleh ke-anggap uang QRIS masuk - itu sebabnya
    kata "qris" wajib ada di teksnya (lihat _parse_qris_amount)."""

    token = get_payment_notify_token()

    resp = client.post(
        "/api/payment-notification",
        json={"raw_text": "Transfer masuk Rp50.000 dari John Doe"},
        headers={"X-Payment-Token": token},
    )
    assert resp.status_code == 200
    assert resp.get_json()["amount"] is None

    notif = PaymentNotification.query.one()
    assert notif.amount is None


def test_missing_raw_text_rejected(client, db):
    token = get_payment_notify_token()

    resp = client.post(
        "/api/payment-notification",
        json={"raw_text": ""},
        headers={"X-Payment-Token": token},
    )
    assert resp.status_code == 400


def test_status_endpoint_requires_owner_or_kasir(client, db, kasir_user, owner_user):
    token = get_payment_notify_token()
    client.post(
        "/api/payment-notification",
        json={"raw_text": "QRIS diterima Rp25.000"},
        headers={"X-Payment-Token": token},
    )

    login(client, "kasir")
    resp = client.get("/payment-notifications/status")
    assert resp.status_code == 200
    payments = resp.get_json()["payments"]
    assert len(payments) == 1
    assert payments[0]["amount"] == 25000


def test_status_endpoint_forbidden_for_dapur(client, db):
    from app.models import ROLE_DAPUR, User

    user = User(username="dapur1", role=ROLE_DAPUR, is_active_user=True)
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()

    login(client, "dapur1")
    resp = client.get("/payment-notifications/status")
    assert resp.status_code == 403
