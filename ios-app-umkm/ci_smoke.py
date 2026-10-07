"""Uji asap alur kasir GO terhadap server yang jalan di dalam app (CI iOS simulator
atau lokal). Tidak butuh paket tambahan - hanya pustaka standar.

    python ci_smoke.py [http://127.0.0.1:8731]

Alur: login -> kategori + menu -> pesanan -> bayar tunai -> struk (+PDF) -> pesanan QRIS
-> batal pesanan -> laporan (+Excel/PDF) -> ganti password -> backup.
Mengisi smoke-result.json dan keluar dengan kode 1 bila ada langkah gagal.
"""

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
IOS = "--ios" in sys.argv[1:]
BASE = (ARGS[0] if ARGS else "http://127.0.0.1:8731").rstrip("/")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
results = []


def fetch(path, data=None):
    url = BASE + path
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        with opener.open(urllib.request.Request(url, data=body), timeout=60) as r:
            return r.status, r.read(), r.geturl(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), url, e.headers.get("Content-Type", "")


def text(raw):
    return raw.decode("utf-8", "replace")


def token(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html) or re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
    return m.group(1) if m else ""


def post_form(page, action, data):
    """Ambil token CSRF dari halaman `page`, lalu POST ke `action`."""
    _, raw, _, _ = fetch(page)
    payload = dict(data)
    payload["csrf_token"] = token(text(raw))
    return fetch(action, payload)


def step(name, ok, detail=""):
    results.append({"langkah": name, "ok": bool(ok), "detail": detail})
    print(("OK    " if ok else "GAGAL ") + name + (" - " + detail if detail and not ok else ""), flush=True)
    return ok


def guard(name, fn):
    try:
        return fn()
    except Exception as e:  # satu langkah rusak tidak boleh menghentikan sisanya
        step(name, False, "%s: %s" % (type(e).__name__, e))
        return None


def money(n):
    return "{:,}".format(n).replace(",", ".")


# --------------------------------------------------------------------------- 1. login
def login():
    status, raw, _, _ = fetch("/login")
    step("halaman login tampil", status == 200 and token(text(raw)), "status %s" % status)
    status, raw, url, _ = post_form("/login", "/login", {"username": "owner", "password": "owner123"})
    html = text(raw)
    step("login owner berhasil", status == 200 and "/login" not in url, "url %s" % url)
    # password bawaan (owner123) wajib diganti dulu: semua halaman staf dialihkan ke Ganti Password
    status, raw, url, _ = fetch("/orders/new")
    step("password bawaan: halaman staf dialihkan ke Ganti Password", "/account/password" in url, "url %s" % url)
    status, raw, url, _ = post_form("/account/password", "/account/password", {"current_password": "owner123", "new_password": "passbaru123", "confirm_password": "passbaru123"})
    step("ganti password bawaan -> akses terbuka", status == 200 and "/account/password" not in url and "berhasil diganti" in text(raw).lower(), "url %s" % url)
    status, raw, url, _ = fetch("/orders/new")
    step("setelah ganti: halaman pesanan terbuka", "/account/password" not in url and status == 200, "url %s" % url)


guard("login", login)

# --------------------------------------------------------------------------- 2. menu
def menu():
    post_form("/admin/menu", "/admin/menu", {"form_type": "category", "name": "Makanan"})
    _, raw, _, _ = fetch("/admin/menu")
    html = text(raw)
    m = re.search(r'<option value="(\d+)"[^>]*>\s*Makanan', html)
    step("kategori ditambahkan", bool(m))
    cat = m.group(1) if m else "1"
    post_form("/admin/menu", "/admin/menu", {"form_type": "menu_item", "name": "Nasi Goreng", "price": "15000", "category_id": cat})
    post_form("/admin/menu", "/admin/menu", {"form_type": "menu_item", "name": "Es Teh", "price": "4000", "category_id": cat})
    _, raw, _, _ = fetch("/admin/menu")
    html = text(raw)
    step("dua menu tersimpan", "Nasi Goreng" in html and "Es Teh" in html)


guard("menu", menu)

# --------------------------------------------------------------------------- 3. pesanan + bayar tunai
ids = []


def item_ids():
    _, raw, _, _ = fetch("/orders/new")
    html = text(raw)
    found = sorted({int(x) for x in re.findall(r'name="qty_(\d+)"', html)})
    step("menu tampil di halaman pesanan", len(found) >= 2, "id: %s" % found)
    return found


def make_order(qty, order_type="takeaway"):
    data = {"order_type": order_type}
    for item_id, q in qty.items():
        data["qty_%d" % item_id] = str(q)
    status, raw, url, _ = post_form("/orders/new", "/orders/new", data)
    return status


def cashier_order_ids():
    _, raw, _, _ = fetch("/cashier")
    return sorted({int(x) for x in re.findall(r"/orders/(\d+)/pay", text(raw))}), text(raw)


def cash_flow():
    global ids
    ids = guard("id menu", item_ids) or []
    if len(ids) < 2:
        return
    nasi, teh = ids[0], ids[1]
    make_order({nasi: 2, teh: 1})  # 2x15000 + 4000 = 34000
    orders, html = cashier_order_ids()
    step("pesanan muncul di Kasir (Rp 34.000)", len(orders) == 1 and money(34000) in html, "pesanan %s" % orders)
    if not orders:
        return
    oid = orders[0]
    status, raw, url, _ = post_form("/cashier", "/orders/%d/pay" % oid, {"payment_method": "cash", "cash_received": "50000", "expected_total": "34000"})
    html = text(raw)
    step("bayar tunai + kembalian Rp 16.000 di struk", status == 200 and money(16000) in html, "url %s" % url)
    status, raw, _, ctype = fetch("/orders/%d/receipt.pdf" % oid)
    step("struk PDF (reportlab + Pillow)", status == 200 and raw[:4] == b"%PDF", "status %s, %s byte" % (status, len(raw)))
    if IOS:
        # iPhone tidak punya printer Bluetooth klasik: Cetak Struk harus mengarahkan ke PDF, bukan error.
        status, raw, _, _ = post_form("/cashier", "/orders/%d/print" % oid, {})
        try:
            data = json.loads(text(raw))
        except ValueError:
            data = {}
        step("iPhone: Cetak Struk diarahkan ke PDF (bukan Bluetooth)", status == 200 and data.get("unsupported") is True and str(data.get("pdf_url", "")).endswith("/receipt.pdf"), "status %s, %s" % (status, str(data)[:120]))
        status, raw, _, _ = fetch("/admin/settings/bluetooth-printers")
        step("iPhone: daftar printer Bluetooth disembunyikan", status == 200 and json.loads(text(raw)).get("supported") is False)


guard("alur tunai", cash_flow)


# --------------------------------------------------------------------------- 4. QRIS + batal
def qris_and_cancel():
    if len(ids) < 2:
        return
    make_order({ids[1]: 3}, "dine_in")  # 12000
    orders, html = cashier_order_ids()
    step("pesanan kedua muncul di Kasir", len(orders) == 1 and money(12000) in html, "pesanan %s" % orders)
    if orders:
        status, raw, _, _ = post_form("/cashier", "/orders/%d/pay" % orders[0], {"payment_method": "qris", "expected_total": "12000"})
        step("bayar QRIS", status == 200 and "Struk" in text(raw), "status %s" % status)
    make_order({ids[0]: 1})
    orders, _ = cashier_order_ids()
    step("pesanan ketiga ada untuk dibatalkan", len(orders) == 1, "pesanan %s" % orders)
    if orders:
        post_form("/cashier", "/orders/%d/cancel" % orders[0], {})
        left, _ = cashier_order_ids()
        step("batalkan pesanan", orders[0] not in left, "sisa %s" % left)


guard("QRIS dan batal", qris_and_cancel)


# --------------------------------------------------------------------------- 5. laporan
def reports():
    _, raw, _, _ = fetch("/reports")
    html = text(raw)
    step("laporan harian: total Rp 46.000", money(46000) in html)
    step("laporan harian: 2 transaksi, tunai dan QRIS", "Bayar Tunai" in html and money(34000) in html and money(12000) in html)
    status, raw, _, _ = fetch("/reports/export/daily.xlsx")
    step("ekspor Excel (openpyxl)", status == 200 and raw[:2] == b"PK", "status %s, %s byte" % (status, len(raw)))
    status, raw, _, _ = fetch("/reports/export/daily.pdf")
    step("ekspor PDF laporan", status == 200 and raw[:4] == b"%PDF", "status %s, %s byte" % (status, len(raw)))


guard("laporan", reports)


# --------------------------------------------------------------------------- 6. ganti password + backup
def password_and_backup():
    status, raw, url, _ = post_form("/account/password", "/account/password", {"current_password": "passbaru123", "new_password": "passbaru456", "confirm_password": "passbaru456"})
    step("ganti password (kedua kali)", status == 200 and "berhasil diganti" in text(raw).lower(), "url %s" % url)
    status, raw, url, _ = post_form("/admin/settings", "/admin/system/backup/create", {})
    step("buat backup (zip)", status == 200, "status %s" % status)


guard("password dan backup", password_and_backup)


# --------------------------------------------------------------------------- 7. ubah menu + pulihkan backup
def edit_and_restore():
    if not ids:
        return
    # perubahan SETELAH backup dibuat: nanti harus hilang lagi saat backup dipulihkan
    post_form("/admin/menu", "/admin/menu/%d/edit" % ids[0], {"name": "Nasi Goreng Spesial", "price": "17.000"})
    _, raw, _, _ = fetch("/admin/menu")
    html = text(raw)
    step("ubah nama dan harga menu", "Nasi Goreng Spesial" in html and "17.000" in html)

    _, raw, _, _ = fetch("/admin/settings")
    m = re.search(r"/admin/system/backup/restore/([^\"'\s]+)", text(raw))
    step("backup tampil di daftar dengan tombol Pulihkan", bool(m))
    if not m:
        return
    status, raw, url, _ = post_form("/admin/settings", "/admin/system/backup/restore/" + m.group(1), {})
    step("pulihkan backup: logout dan diarahkan ke login", status == 200 and "/login" in url and "dipulihkan" in text(raw), "url %s" % url)
    # setelah restore, password dari data backup (passbaru456) berlaku
    status, raw, url, _ = post_form("/login", "/login", {"username": "owner", "password": "passbaru456"})
    step("login setelah pulihkan", status == 200 and "/login" not in url, "url %s" % url)
    _, raw, _, _ = fetch("/admin/menu")
    html = text(raw)
    step("menu kembali ke isi backup", "Nasi Goreng" in html and "Spesial" not in html)
    _, raw, _, _ = fetch("/reports")
    step("laporan kembali (Rp 46.000)", money(46000) in text(raw))


guard("ubah menu dan pulihkan", edit_and_restore)

# --------------------------------------------------------------------------- ringkasan
failed = [r for r in results if not r["ok"]]
with open("smoke-result.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\n%d langkah, %d gagal" % (len(results), len(failed)))
sys.exit(1 if failed else 0)
