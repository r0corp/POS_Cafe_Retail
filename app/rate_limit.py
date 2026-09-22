import threading
import time

# Rate limiter sederhana di memori (sliding window per key) - cukup buat
# aplikasi ini karena selalu jalan sebagai 1 proses (waitress, lihat
# serve_production.py: threads=4 tapi 1 proses saja, jadi dict di bawah
# ini aman dipakai bareng semua thread lewat 1 lock yang sama). TIDAK
# akan cocok lagi kalau nanti aplikasi ini dijalankan multi-proses.

_lock = threading.Lock()
_attempts = {}


def is_rate_limited(key, max_attempts, window_seconds):
    """True kalau `key` (mis. gabungan IP + username, atau IP + order_id)
    sudah melebihi `max_attempts` percobaan dalam `window_seconds`
    terakhir - dipakai buat cegah brute-force login staff & PIN tamu.
    Setiap pemanggilan yang TIDAK di-rate-limit otomatis ikut tercatat
    sebagai satu percobaan baru."""

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        # Beres-beres key lain yang sudah lama tidak aktif, supaya dict
        # ini tidak numpuk terus tanpa batas selama aplikasi jalan.
        if len(_attempts) > 1000:
            for other_key in [k for k, v in _attempts.items() if not v or v[-1] < cutoff]:
                del _attempts[other_key]

        timestamps = [t for t in _attempts.get(key, []) if t >= cutoff]

        if len(timestamps) >= max_attempts:
            _attempts[key] = timestamps
            return True

        timestamps.append(now)
        _attempts[key] = timestamps
        return False
