"""Edisi produk Oru POS pada satu basis kode ini (APK/iPhone):

  go    Oru POS GO    gerobak/warung, 1 perangkat, tanpa meja/dapur/WiFi (bawaan)
  cafe  Oru POS Cafe  mini cafe: meja, dapur, sampai 3 pengguna, beberapa HP/tablet satu WiFi

Oru POS PRO adalah aplikasi server terpisah (folder app/ di akar repo) dan tidak memakai modul ini.

Edisi ditentukan saat build (Gradle -Pedition=cafe) dan diteruskan Java ke umkm_app.run(). Kode Aktivasi
terikat ke edisi (lihat licensing._hash_to_int): kode GO tidak bisa mengaktifkan Cafe, begitu sebaliknya.
"""

import socket

EDITIONS = {
    "go": {
        "label": "Oru POS GO",
        "short": "GO",
        "logo": "img/go-logo.png",
        "lan_server": False,        # hanya 127.0.0.1: satu HP
        "max_users": None,          # tidak dibatasi (menu Pengguna disembunyikan; akun lama tetap jalan)
        "uses_tables_default": False,
        "quick_sale": True,         # tombol Bayar Tunai/QRIS langsung di layar pesanan (jual satu layar)
        "hidden_nav": ("staff.kitchen", "staff.admin_users"),
    },
    "cafe": {
        "label": "Oru POS Cafe",
        "short": "Cafe",
        "logo": "img/cafe-logo.png",
        "lan_server": True,         # dibuka ke WiFi toko supaya tablet dapur/kasir lain bisa terhubung
        "max_users": 3,             # pemilik + 2 akun
        "uses_tables_default": True,
        "quick_sale": False,
        "hidden_nav": (),
    },
}

DEFAULT = "go"
_state = {"code": DEFAULT}


def set_edition(code):
    _state["code"] = code if code in EDITIONS else DEFAULT
    return _state["code"]


def current():
    return _state["code"]


def info(code=None):
    return EDITIONS[code or _state["code"]]


def lan_ip():
    """Alamat IP HP di jaringan WiFi/hotspot (tanpa mengirim paket apa pun), atau None bila tidak tersambung."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))     # UDP: hanya memilih antarmuka keluar, tidak ada lalu lintas
        ip = sock.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        sock.close()
