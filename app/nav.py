from flask_babel import lazy_gettext as _l

from .models import ROLE_OWNER, ROLE_KASIR, ROLE_DAPUR, ROLE_PELAYAN

# roles=None berarti semua role yang sudah login boleh lihat menu ini.
NAV_ITEMS = [
    {
        "endpoint": "staff.dashboard",
        "icon": "bi-speedometer2",
        "label": _l("Dashboard"),
        "roles": None,
    },
    {
        "endpoint": "staff.table_map",
        "icon": "bi-grid-3x3-gap-fill",
        "label": _l("Meja"),
        "roles": None,
    },
    {
        "endpoint": "staff.new_order",
        "icon": "bi-plus-circle",
        "label": _l("Pesanan"),
        "roles": [ROLE_OWNER, ROLE_KASIR, ROLE_PELAYAN],
    },
    {
        "endpoint": "staff.kitchen",
        "icon": "bi-egg-fried",
        "label": _l("Dapur"),
        "roles": [ROLE_OWNER, ROLE_DAPUR],
    },
    {
        "endpoint": "staff.waiter",
        "icon": "bi-bell",
        "label": _l("Siap Diantar"),
        "roles": [ROLE_PELAYAN],
    },
    {
        "endpoint": "staff.cashier",
        "icon": "bi-cash-coin",
        "label": _l("Kasir"),
        "roles": [ROLE_OWNER, ROLE_KASIR],
    },
    {
        "endpoint": "staff.admin_menu",
        "icon": "bi-list-ul",
        "label": _l("Menu"),
        "roles": [ROLE_OWNER],
    },
    {
        "endpoint": "staff.admin_inventory",
        "icon": "bi-boxes",
        "label": _l("Inventory"),
        "roles": [ROLE_OWNER],
    },
    {
        "endpoint": "staff.admin_users",
        "icon": "bi-people",
        "label": _l("Pengguna"),
        "roles": [ROLE_OWNER],
    },
    {
        "endpoint": "staff.reports",
        "icon": "bi-bar-chart",
        "label": _l("Laporan"),
        "roles": [ROLE_OWNER],
    },
    {
        "endpoint": "staff.admin_settings",
        "icon": "bi-gear",
        "label": _l("Pengaturan"),
        "roles": [ROLE_OWNER],
    },
]
