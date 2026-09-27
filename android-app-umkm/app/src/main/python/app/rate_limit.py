import threading
import time

# Rate limiter sederhana di memori (sliding window per key) - cukup buat
# aplikasi ini karena selalu jalan sebagai 1 proses (waitress, lihat
# serve_production.py: threads=4 tapi 1 proses saja, jadi dict di bawah
# ini aman dipakai bareng semua thread lewat 1 lock yang sama). TIDAK
# akan cocok lagi kalau nanti aplikasi ini dijalankan multi-proses.
#
# Yang dihitung cuma percobaan GAGAL (record_failure) - percobaan yang
# benar tidak menghabiskan jatah, jadi staf yang login-logout berkali-
# kali saat ganti shift, atau tamu yang tahu PIN-nya, tidak ikut terkunci
# gara-gara orang iseng spam percobaan ngawur.

_lock = threading.Lock()
_attempts = {}

# Window terpanjang yang dipakai pemanggil mana pun - key yang percobaan
# terakhirnya lebih lama dari ini pasti sudah tidak relevan untuk semua
# pemakai, jadi aman dibuang saat beres-beres (tidak ikut membuang key
# milik pemakai lain yang window-nya lebih panjang).
MAX_WINDOW_SECONDS = 60 * 60

# Batas jumlah key yang disimpan - kalau terlampaui (mis. ada yang spam
# ribuan username berbeda), key paling lama dibuang supaya memori tetap
# terbatas.
MAX_KEYS = 5000


def is_blocked(key, max_attempts, window_seconds):
    """True kalau `key` (mis. gabungan IP + username, atau order_id) sudah
    punya >= `max_attempts` percobaan gagal dalam `window_seconds`
    terakhir - dipakai buat cegah brute-force login staff, PIN tamu, dan
    PIN developer. Tidak mencatat apa-apa; pasangannya record_failure()."""

    cutoff = time.monotonic() - window_seconds
    with _lock:
        timestamps = [t for t in _attempts.get(key, []) if t >= cutoff]
        if timestamps:
            _attempts[key] = timestamps
        else:
            _attempts.pop(key, None)
        return len(timestamps) >= max_attempts


def record_failure(key, window_seconds):
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        if len(_attempts) >= MAX_KEYS:
            stale_before = now - MAX_WINDOW_SECONDS
            for other_key in [k for k, v in _attempts.items() if not v or v[-1] < stale_before]:
                del _attempts[other_key]
            while len(_attempts) >= MAX_KEYS:
                oldest_key = min(_attempts, key=lambda k: _attempts[k][-1] if _attempts[k] else 0)
                del _attempts[oldest_key]

        timestamps = [t for t in _attempts.get(key, []) if t >= cutoff]
        timestamps.append(now)
        _attempts[key] = timestamps


def clear_failures(key):
    with _lock:
        _attempts.pop(key, None)
