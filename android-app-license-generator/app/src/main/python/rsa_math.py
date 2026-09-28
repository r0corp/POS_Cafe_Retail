"""Cuma bagian TANDA TANGAN dari skema RSA yang sama dipakai
licensing_tool/rsa_util.py (laptop) - lihat komentar di sana buat
penjelasan lengkap kenapa "textbook RSA" ini cukup buat kasus
anti-pembajakan skala kecil begini. App ini yang PEGANG private key,
jadi cuma perlu sign(), tidak perlu verify()/generate_keypair()."""


def sign(message_int, private_key):
    n, d = private_key
    return pow(message_int % n, d, n)
