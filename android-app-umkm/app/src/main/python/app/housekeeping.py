"""Pesanan lunas dari hari bisnis sebelumnya yang tidak pernah ditandai
"Sudah Diantar" di Dapur (mis. Bawa Pulang yang langsung dibawa tamu) tetap
nongol di Dashboard/Dapur sampai kapan pun, dan - yang lebih parah - tetap
"menempati" mejanya (lihat Order.occupying_table_query), jadi meja itu bisa
tidak bisa dipakai besok paginya.

Di sini pesanan seperti itu ditutup otomatis (status -> "served"). Barisnya
TIDAK dihapus: is_paid, paid_at, total, item semuanya utuh, jadi tetap masuk
Laporan harian/mingguan/bulanan dan riwayat kasir seperti biasa."""

from datetime import datetime, time, timedelta

from . import db
from .models import Order

# Pergantian "hari bisnis" jam 04:00, bukan tengah malam - kafe yang buka
# lewat jam 12 malam tidak boleh ditutup pesanannya di tengah shift.
BUSINESS_DAY_STARTS_AT = time(4, 0)


def business_day_start(now=None):
    now = now or datetime.now()
    start = datetime.combine(now.date(), BUSINESS_DAY_STARTS_AT)
    return start if now >= start else start - timedelta(days=1)


def close_stale_paid_orders(now=None):
    """Tutup pesanan yang SUDAH LUNAS sebelum awal hari bisnis ini tapi status
    dapurnya belum "served". Pesanan belum lunas tidak disentuh (urusan uang
    - kasir/owner yang memutuskan). Return jumlah pesanan yang ditutup."""

    result = db.session.execute(
        Order.__table__.update()
        .where(
            Order.is_paid.is_(True),
            Order.status != "served",
            Order.paid_at < business_day_start(now),
        )
        .values(status="served")
    )
    db.session.commit()
    return result.rowcount
