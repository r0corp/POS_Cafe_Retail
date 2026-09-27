"""RSA murni Python (tanpa dependency pip) - dipakai buat generate
keypair dan generate kode aktivasi APK UMKM.

Sengaja pure Python (bukan pakai library `cryptography`/`rsa` dari
pip) supaya alat ini tidak butuh apa-apa selain Python biasa - berguna
karena cuma dipakai sesekali (bikin keypair sekali, generate kode tiap
ada penjualan baru), jadi tidak perlu maintain venv terpisah.

CATATAN KEAMANAN: ini "textbook RSA" (hash di-modpow langsung, tanpa
padding OAEP/PSS penuh) - cukup untuk kasus anti-pembajakan APK skala
kecil (bukan buat lindungi rahasia bernilai tinggi), karena pesan yang
ditandatangani SELALU hash SHA-256 (bukan nilai bebas pilihan
penyerang), jadi serangan malleability RSA klasik tidak berlaku di
sini.
"""

import secrets


def _is_probable_prime(n, rounds=40):
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False

    # n - 1 = d * 2^r
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1

    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits):
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def _egcd(a, b):
    if a == 0:
        return b, 0, 1
    g, x1, y1 = _egcd(b % a, a)
    return g, y1 - (b // a) * x1, x1


def _modinv(a, m):
    g, x, _ = _egcd(a, m)
    if g != 1:
        raise ValueError("modinv tidak ada (harusnya tidak mungkin kejadian)")
    return x % m


def generate_keypair(bits=2048):
    """Return ((n, e), (n, d)) - (public, private). e selalu 65537
    (standar, cepat buat verifikasi)."""

    e = 65537
    while True:
        p = _generate_prime(bits // 2)
        q = _generate_prime(bits // 2)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if _egcd(e, phi)[0] == 1:
            d = _modinv(e, phi)
            return (n, e), (n, d)


def sign(message_int, private_key):
    n, d = private_key
    return pow(message_int % n, d, n)


def verify(message_int, signature_int, public_key):
    n, e = public_key
    return pow(signature_int, e, n) == message_int % n
