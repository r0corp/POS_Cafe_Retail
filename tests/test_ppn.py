"""calculate_ppn() dipakai buat hitung PPN di kasir DAN buat snapshot
struk permanen begitu order dibayar - kalau ini salah, semua nominal
yang dibayar tamu ikut salah."""

from app.models import calculate_ppn


def test_ppn_basic_11_percent():
    assert calculate_ppn(100000, 11.0) == 11000


def test_ppn_rounds_half_up_not_banker_rounding():
    # 16.5 harus jadi 17 (bulat ke atas), BUKAN 16 (round() bawaan
    # Python pakai banker's rounding yang bisa membulatkan ke bawah).
    assert calculate_ppn(150, 11.0) == 17


def test_ppn_zero_subtotal():
    assert calculate_ppn(0, 11.0) == 0


def test_ppn_zero_percentage():
    assert calculate_ppn(100000, 0) == 0


def test_ppn_none_subtotal():
    assert calculate_ppn(None, 11.0) == 0


def test_ppn_none_percentage():
    assert calculate_ppn(100000, None) == 0


def test_ppn_no_floating_point_drift():
    # 11% dari 150 lewat float biasa (150 * 0.11) bisa jadi
    # 16.500000000000002 - calculate_ppn pakai Decimal supaya bersih.
    assert calculate_ppn(150, 11) == 17


def test_ppn_large_total():
    assert calculate_ppn(1_000_000, 11.0) == 110000


def test_ppn_fractional_percentage():
    assert calculate_ppn(100000, 2.5) == 2500
