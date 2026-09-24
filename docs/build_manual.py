"""Generator Buku Panduan Orulabs Cafe POS (PDF) - dibuat pakai reportlab
platypus, bukan disimpan sebagai dokumen statis, supaya gampang dibuat
ulang kapan saja screenshot/fitur berubah:

    python docs/build_manual.py

Hasilnya: docs/BUKU_PANDUAN.pdf. Screenshot yang dipakai ada di
docs/screenshots/ (lihat README.md untuk cara mengambil ulang lewat
Mode Demo kalau perlu di-refresh)."""

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(HERE, "screenshots")
OUT_PATH = os.path.join(HERE, "BUKU_PANDUAN.pdf")

ORANGE = colors.HexColor("#F07828")
ORANGE_DARK = colors.HexColor("#D9601A")
BLUE = colors.HexColor("#1BA0F8")
NAVY = colors.HexColor("#0B1220")
NAVY2 = colors.HexColor("#131C2E")
TEXT_DARK = colors.HexColor("#1A2233")
MUTED = colors.HexColor("#5B6472")
PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

styles = getSampleStyleSheet()

styles.add(ParagraphStyle(
    "H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20,
    textColor=ORANGE_DARK, spaceBefore=6, spaceAfter=14, leading=24,
))
styles.add(ParagraphStyle(
    "H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14,
    textColor=TEXT_DARK, spaceBefore=16, spaceAfter=8, leading=18,
))
styles.add(ParagraphStyle(
    "H3", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=11.5,
    textColor=ORANGE_DARK, spaceBefore=10, spaceAfter=6, leading=15,
))
styles.add(ParagraphStyle(
    "Body", parent=styles["Normal"], fontName="Helvetica", fontSize=10,
    textColor=TEXT_DARK, leading=15, spaceAfter=8, alignment=TA_LEFT,
))
styles.add(ParagraphStyle(
    "BodyBold", parent=styles["Body"], fontName="Helvetica-Bold",
))
styles.add(ParagraphStyle(
    "ManualBullet", parent=styles["Body"], leftIndent=14, bulletIndent=2, spaceAfter=5,
))
styles.add(ParagraphStyle(
    "Caption", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=8.5,
    textColor=MUTED, alignment=TA_CENTER, spaceBefore=4, spaceAfter=14,
))
styles.add(ParagraphStyle(
    "TipBody", parent=styles["Body"], fontSize=9.5, textColor=TEXT_DARK, spaceAfter=0,
))
styles.add(ParagraphStyle(
    "TOCHeading", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=22,
    textColor=ORANGE_DARK, spaceAfter=18,
))
styles.add(ParagraphStyle(
    "TOC1", fontName="Helvetica-Bold", fontSize=11.5, textColor=TEXT_DARK,
    leftIndent=0, firstLineIndent=0, spaceAfter=8, leading=14,
))
styles.add(ParagraphStyle(
    "TOC2", fontName="Helvetica", fontSize=10, textColor=MUTED,
    leftIndent=14, firstLineIndent=0, spaceAfter=4, leading=13,
))


def pic(filename, max_w=CONTENT_W, max_h=9.5 * cm):
    """Flowable Image dari docs/screenshots/<filename>, di-skala biar pas
    lebar konten tanpa gepeng, dibatasi tinggi maksimum supaya screenshot
    yang sangat panjang (mis. riwayat transaksi) tidak menabrak footer -
    dipotong proporsinya, bukan gambarnya sendiri yang di-crop."""

    path = os.path.join(SHOT_DIR, filename)
    reader = ImageReader(path)
    iw, ih = reader.getSize()
    w, h = max_w, max_w * ih / iw
    if h > max_h:
        h = max_h
        w = max_h * iw / ih
    return Image(path, width=w, height=h, hAlign="CENTER")


def figure(filename, caption, max_w=CONTENT_W, max_h=9.5 * cm):
    return KeepTogether([pic(filename, max_w, max_h), Paragraph(caption, styles["Caption"])])


def bullets(items):
    return [Paragraph(f"&bull;&nbsp;&nbsp;{t}", styles["ManualBullet"]) for t in items]


def tip(text):
    t = Table(
        [[Paragraph(f"<b>Tips:</b> {text}", styles["TipBody"])]],
        colWidths=[CONTENT_W],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCE3CB")),
        ("BOX", (0, 0), (-1, -1), 0.6, ORANGE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [KeepTogether([Spacer(1, 4), t, Spacer(1, 10)])]


# ============================================================
# Cover & Table of Contents
# ============================================================

def draw_cover(c, doc):
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(NAVY2)
    c.rect(0, PAGE_H - 8 * cm, PAGE_W, 8 * cm, fill=1, stroke=0)

    # Lencana logo sederhana (lingkaran 2 warna, senada logo aplikasi).
    cx, cy = PAGE_W / 2, PAGE_H - 4.6 * cm
    r = 1.6 * cm
    c.setFillColor(BLUE)
    c.circle(cx, cy, r, fill=1, stroke=0)
    c.setFillColor(NAVY2)
    c.circle(cx, cy, r * 0.55, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.rect(cx, cy, r, r, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 7.1 * cm, "ORULABS CAFE POS")

    c.setFillColor(ORANGE)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 7.85 * cm, "BUKU PANDUAN PENGGUNAAN")

    c.setFillColor(colors.HexColor("#94A3B8"))
    c.setFont("Helvetica", 10.5)
    c.drawCentredString(
        PAGE_W / 2, PAGE_H - 8.35 * cm,
        "Panduan lengkap untuk Owner, Kasir, Dapur, Pelayan, dan Pelanggan",
    )

    # Ringkasan isi di badan cover gelap.
    items = [
        "Login & navigasi dasar aplikasi",
        "Panduan lengkap per peran (Owner / Kasir / Dapur / Pelayan)",
        "Cara pelanggan memesan lewat scan QR di meja",
        "Mode Demo, keamanan, dan tanya-jawab umum",
    ]
    y = PAGE_H - 11 * cm
    c.setFont("Helvetica", 11)
    for it in items:
        c.setFillColor(ORANGE)
        c.circle(MARGIN + 3, y + 3, 2.2, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#E2E8F0"))
        c.drawString(MARGIN + 14, y, it)
        y -= 0.95 * cm

    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_W / 2, 2.2 * cm, "Dibuat dengan Flask + SQLite  ·  Orulabs © 2026")
    c.restoreState()


def draw_normal_page(c, doc):
    c.saveState()
    c.setFillColor(colors.white)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # Header tipis.
    c.setFillColor(ORANGE)
    c.rect(0, PAGE_H - 0.35 * cm, PAGE_W, 0.35 * cm, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(MARGIN, PAGE_H - 1.1 * cm, "ORULABS CAFE POS — BUKU PANDUAN")
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - 1.1 * cm, doc.chapter_title_for_page(c.getPageNumber()))

    # Footer + nomor halaman.
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.setLineWidth(0.6)
    c.line(MARGIN, 1.6 * cm, PAGE_W - MARGIN, 1.6 * cm)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(PAGE_W / 2, 1.1 * cm, f"{c.getPageNumber()}")
    c.restoreState()


class ManualDoc(BaseDocTemplate):
    def __init__(self, *args, **kwargs):
        BaseDocTemplate.__init__(self, *args, **kwargs)
        self.section_title = ""
        # (halaman, judul bab) tempat tiap H1 mulai, dari pass build SEBELUMNYA -
        # dipakai supaya header halaman pertama sebuah bab tidak menampilkan judul
        # bab lama (onPage digambar sebelum heading bab baru sempat "tercatat").
        self._prev_pass_chapter_starts = []
        self._cur_pass_chapter_starts = []

        cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        normal_frame = Frame(MARGIN, 1.9 * cm, CONTENT_W, PAGE_H - 1.9 * cm - 1.8 * cm, id="normal")

        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover_frame], onPage=draw_cover),
            PageTemplate(id="Normal", frames=[normal_frame], onPage=draw_normal_page),
        ])

    def build(self, flowables, **kwargs):
        # multiBuild jalan beberapa pass demi Daftar Isi - reset supaya
        # header halaman awal tidak membawa judul bab dari pass sebelumnya.
        self.section_title = ""
        self._cur_pass_chapter_starts = []
        result = BaseDocTemplate.build(self, flowables, **kwargs)
        self._prev_pass_chapter_starts = self._cur_pass_chapter_starts
        return result

    def chapter_title_for_page(self, page_num):
        title = ""
        for start_page, text in self._prev_pass_chapter_starts:
            if start_page > page_num:
                break
            title = text
        return title

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style_name = flowable.style.name
            text = flowable.getPlainText()
            if style_name == "H1":
                self.section_title = text.upper()
                self._cur_pass_chapter_starts.append((self.page, text.upper()))
                self.notify("TOCEntry", (0, text, self.page))
                key = f"h1-{self.page}-{text[:20]}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0)
            elif style_name == "H2":
                self.notify("TOCEntry", (1, text, self.page))
                key = f"h2-{self.page}-{text[:20]}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=1)


def chapter(title):
    return [NextPageTemplate("Normal"), PageBreak(), Paragraph(title, styles["H1"])]


def section(title):
    return [Paragraph(title, styles["H2"])]


# ============================================================
# Susun isi buku
# ============================================================

story = []

# --- Cover ---
story.append(Paragraph("", styles["Body"]))  # placeholder, konten cover digambar di onPage

# --- Daftar Isi ---
story.append(NextPageTemplate("Normal"))
story.append(PageBreak())
story.append(Paragraph("Daftar Isi", styles["TOCHeading"]))
toc = TableOfContents()
toc.levelStyles = [styles["TOC1"], styles["TOC2"]]
story.append(toc)

# --- 1. Pendahuluan ---
story += chapter("1. Pendahuluan")
story += [Paragraph(
    "Orulabs Cafe POS adalah aplikasi kasir (Point of Sale) untuk kafe/warkop yang "
    "menggabungkan 3 cara pesan sekaligus dalam 1 sistem: pesan sendiri oleh tamu lewat "
    "scan QR code di meja, input manual oleh pelayan/kasir untuk tamu yang tidak nyaman "
    "pesan sendiri, dan pesanan dari platform delivery (GoFood/GrabFood/ShopeeFood, dst). "
    "Semua jenis pesanan itu masuk ke alur kerja yang sama: dapur memproses, pelayan "
    "mengantar, kasir menerima pembayaran, dan laporan penjualan mencatat semuanya "
    "secara otomatis.",
    styles["Body"],
)]
story += [Paragraph(
    "Aplikasi ini dirancang untuk dipakai di jaringan lokal toko (bukan lewat internet "
    "publik) lewat 1 komputer/mini PC yang menyala terus sebagai server, diakses tablet "
    "kasir, HP dapur/pelayan, dan HP tamu lewat WiFi toko yang sama.",
    styles["Body"],
)]
story += section("Untuk siapa buku ini?")
story += bullets([
    "<b>Owner</b> — pemilik toko, akses penuh ke semua menu termasuk Pengaturan, Laporan, dan Kelola User.",
    "<b>Kasir</b> — menerima pembayaran, input pesanan manual, cetak/cetak ulang struk.",
    "<b>Dapur</b> — memproses pesanan yang masuk sampai siap diantar.",
    "<b>Pelayan</b> — mengantar pesanan yang sudah siap, dan bisa input pesanan manual juga.",
    "<b>Pelanggan/Tamu</b> — memesan sendiri lewat scan QR code yang ditempel di meja.",
])
story += tip(
    "Tiap akun staf cuma bisa membuka halaman sesuai perannya masing-masing — kalau "
    "sebuah menu tidak muncul di HP Anda, kemungkinan besar memang bukan bagian dari "
    "tugas peran Anda, bukan aplikasi yang error."
)

# --- 2. Memulai ---
story += chapter("2. Memulai — Login & Navigasi Dasar")
story += [Paragraph(
    "Buka alamat aplikasi (diberikan oleh developer/owner, biasanya berupa alamat IP "
    "mini PC toko, contoh: <font face='Courier'>http://192.168.1.10:8000</font>) lewat "
    "browser HP/tablet/komputer yang sudah tersambung ke WiFi toko. Halaman Login akan "
    "muncul otomatis.",
    styles["Body"],
)]
story.append(figure("owner-00-login.png", "Halaman Login — mode gelap", max_w=8 * cm, max_h=9 * cm))
story += [Paragraph(
    "Masukkan Username & Password yang sudah diberikan, lalu tekan tombol LOGIN. Di "
    "bagian bawah form ada 2 preferensi tampilan yang tersimpan otomatis per perangkat:",
    styles["Body"],
)]
story += bullets([
    "<b>Bahasa</b> — bendera Indonesia/Inggris, mengubah seluruh teks aplikasi termasuk struk.",
    "<b>Mode Terang/Gelap</b> — ikon matahari/bulan, mengubah tema warna seluruh halaman.",
])
story += tip(
    "Lupa password? Cuma Owner yang bisa mengatur ulang password akun lain, lewat menu "
    "Kelola User. Kalau akun Owner sendiri yang lupa, hubungi developer aplikasi."
)
story += section("Setelah login")
story += [Paragraph(
    "Semua akun akan diarahkan ke halaman <b>Dashboard</b> — titik awal untuk membuka "
    "semua fitur lain lewat kartu menu di tengah halaman. Navbar di paling atas cuma "
    "berisi jam berjalan (klik untuk lihat kalender) dan foto profil (klik untuk lihat "
    "menu ganti bahasa/tema, dan tombol Logout).",
    styles["Body"],
)]

# --- 3. Owner ---
story += chapter("3. Panduan untuk Owner")
story += [Paragraph(
    "Owner punya akses ke semua halaman aplikasi, termasuk beberapa menu yang tidak "
    "kelihatan sama sekali oleh peran lain: Kelola Menu, Inventory, Kelola User, "
    "Pengaturan, dan Laporan Penjualan.",
    styles["Body"],
)]

story += section("3.1  Dashboard")
story += [Paragraph(
    "Ringkasan kondisi toko hari ini dalam 4 angka: jumlah pesanan yang masih aktif, "
    "total penjualan hari ini, jumlah transaksi hari ini, dan jumlah pesanan yang masih "
    "menunggu dibayar. Di bawahnya ada kartu menu ke semua fitur — tiap kartu bisa "
    "menampilkan lencana angka kecil (badge) yang menunjukkan berapa hal yang perlu "
    "diperhatikan di fitur itu (misalnya jumlah pesanan yang menunggu di dapur).",
    styles["Body"],
)]
story.append(figure("owner-01-dashboard.png", "Dashboard — ringkasan hari ini & kartu menu"))

story += section("3.2  Denah Meja & Lantai")
story += [Paragraph(
    "Halaman ini menampilkan semua meja dalam bentuk kartu, mirip pemilihan kursi "
    "bioskop — <font color='#1BA0F8'><b>biru</b></font> berarti meja kosong, "
    "<font color='#F07828'><b>oranye</b></font> berarti meja sedang terisi pesanan yang "
    "belum lunas. Meja otomatis kembali biru (kosong) begitu pesanannya dibayar lunas di "
    "Kasir — tidak perlu direset manual.",
    styles["Body"],
)]
story.append(figure("owner-02-meja.png", "Denah Meja — kartu biru (kosong) & oranye (terisi)"))
story += [Paragraph("Khusus di halaman ini, Owner bisa:", styles["Body"])]
story += bullets([
    "<b>Tambah Meja Baru</b> — isi label meja, pilih lantai, dan kode unik (dipakai untuk URL QR code-nya).",
    "<b>Tambah Lantai</b> — kalau toko punya lebih dari 1 lantai/area.",
    "<b>Lihat/cetak QR</b> — ikon QR kecil di tiap kartu meja, buat lihat & cetak QR code satuan.",
    "<b>Cetak Semua QR</b> — tombol di header tiap lantai, mengunduh 1 file PDF berisi kartu QR semua meja di lantai itu sekaligus — tinggal print & gunting, tempel di tiap meja.",
])
story += tip(
    "Isi Nama & Password WiFi toko di Pengaturan → Aplikasi supaya info WiFi ikut "
    "tercetak di kartu QR — tamu jadi tahu harus konek ke WiFi mana dulu sebelum "
    "scan, karena aplikasi ini jalan di jaringan lokal, bukan internet."
)

story += section("3.3  Kelola Menu & Resep Bahan Baku")
story += [Paragraph(
    "Tempat mengatur kategori dan item menu yang dijual. Tiap item menu wajib punya "
    "nama, harga, dan kategori — foto & resep bahan baku sifatnya opsional tapi "
    "sangat disarankan diisi.",
    styles["Body"],
)]
story.append(figure("owner-06-kelola-menu.png", "Kelola Menu — tambah kategori/menu & filter kategori"))
story += [Paragraph(
    "Klik foto sebuah item menu untuk membuka detailnya, lalu buka bagian “Resep "
    "Bahan Baku” — pilih bahan apa saja & berapa jumlah pemakaiannya untuk 1 porsi. "
    "Setelah resep diatur, stok bahan baku akan <b>otomatis berkurang</b> setiap ada "
    "pesanan menu itu masuk, dari sumber mana pun (tamu scan QR, kasir, maupun pelayan).",
    styles["Body"],
)]
story += tip(
    "Item menu yang bahannya sudah habis otomatis hilang dari daftar yang bisa dipesan "
    "(baik di halaman tamu maupun Input Pesanan Manual) — tidak perlu ditandai "
    "“Habis” secara manual satu-satu."
)

story += section("3.4  Inventory Bahan Baku")
story += [Paragraph(
    "Daftar semua bahan baku beserta stok saat ini, satuan (gram/ml/pcs/dll), dan batas "
    "“stok menipis” — bahan yang stoknya sudah di bawah batas itu ditandai "
    "lencana peringatan merah di daftar.",
    styles["Body"],
)]
story.append(figure("owner-07-inventory.png", "Inventory Bahan Baku — tambah bahan & tambah stok"))
story += bullets([
    "<b>Tambah Bahan Baku</b> — form di sisi kiri, isi nama/satuan/stok awal/batas menipis.",
    "<b>Tambah Stok</b> — kolom angka di tiap baris bahan, buat catat restock/belanja bahan baru.",
    "<b>Ekspor Excel/PDF</b> — tombol di kanan atas daftar, unduh semua bahan atau cuma yang stoknya menipis.",
])

story += section("3.5  Kelola User & Hak Akses")
story.append(figure("owner-08-pengguna.png", "Kelola User — daftar akun, status online, & log aktivitas"))
story += [Paragraph(
    "Tambah akun staf baru lewat form di kiri (isi username, password, dan pilih role). "
    "Tiap baris user di daftar kanan menampilkan titik hijau kalau sedang online, dan "
    "tombol <b>Nonaktifkan</b> untuk mengunci akses staf yang resign/cuti tanpa harus "
    "menghapus akunnya (riwayat pesanan yang pernah dia proses tetap tersimpan). Di "
    "bagian bawah ada Log Aktivitas Login — catatan siapa login/logout dan kapan.",
    styles["Body"],
)]
story += tip(
    "Akun yang dinonaktifkan langsung kehilangan akses di HP-nya pada request "
    "berikutnya — tidak perlu menunggu staf itu logout sendiri dulu."
)

story += section("3.6  Pengaturan Toko")
story += [Paragraph(
    "Halaman Pengaturan terbagi jadi beberapa tab. Tab <b>Aplikasi</b> berisi identitas "
    "toko (nama, alamat, kontak, sosial media), info WiFi, dan daftar lantai toko.",
    styles["Body"],
)]
story.append(figure("owner-10-pengaturan-aplikasi.png", "Pengaturan → Aplikasi — identitas, kontak, WiFi, & lantai"))
story += [Paragraph(
    "Tab <b>Notifikasi</b> mengatur bunyi peringatan pesanan baru di halaman Dapur & "
    "Kasir — bisa diatur nada yang berbeda untuk tiap peran staf (Dapur/Kasir/"
    "Pelayan), jadi kalau beberapa device menyala bareng di satu ruangan, staf bisa "
    "langsung tahu notifikasi itu untuk device siapa cuma dari bunyinya.",
    styles["Body"],
)]
story.append(figure("owner-11-pengaturan-notifikasi.png", "Pengaturan → Notifikasi — nada berbeda per peran staf"))
story += [Paragraph(
    "Tab <b>Platform Delivery</b> untuk mendaftarkan platform pesan-antar yang dipakai "
    "toko (GoFood/GrabFood/ShopeeFood, dst) — tiap platform bisa diatur markup harga "
    "otomatis (persentase dari harga toko biasa) atau harga manual per item menu, sesuai "
    "kesepakatan komisi dengan platform itu.",
    styles["Body"],
)]
story.append(figure("owner-12-pengaturan-platform.png", "Pengaturan → Platform Delivery"))
story += [Paragraph(
    "Tab <b>Sistem</b> berisi tombol Bersihkan Cache, Backup Database, Mode Perbaikan "
    "(kunci sementara akses non-Owner saat sedang maintenance), dan Mode Demo.",
    styles["Body"],
)]
story.append(figure("owner-13-pengaturan-sistem.png", "Pengaturan → Sistem"))

story += section("3.7  Laporan Penjualan")
story += [Paragraph(
    "Laporan dibagi 4 tab periode: Harian, Mingguan, Bulanan, dan Tahunan. Tiap tab "
    "menampilkan 4 angka ringkasan (total penjualan, jumlah transaksi, rata-rata per "
    "transaksi, item terjual), daftar 10 item paling laris di periode itu, dan daftar "
    "pesanan yang dibatalkan (kalau ada). Ada juga tombol unduh Excel & PDF di kanan "
    "atas untuk tiap periode.",
    styles["Body"],
)]
story.append(figure("owner-09-laporan.png", "Laporan Penjualan — 4 tab periode + item terlaris"))

story += section("3.8  Mode Demo")
story += [Paragraph(
    "Fitur khusus untuk mengisi aplikasi dengan data contoh yang realistis (menu "
    "lengkap dengan foto, bahan baku, meja, sampai riwayat transaksi & laporan "
    "penjualan) — berguna untuk latihan staf baru tanpa risiko mengotori data toko "
    "yang sungguhan. Semua data contoh ditandai tersendiri dan dihapus bersih begitu "
    "Mode Demo dimatikan lagi, data asli toko tidak pernah tersentuh.",
    styles["Body"],
)]
story += tip(
    "Mode Demo dikunci PIN khusus yang cuma diketahui developer aplikasi — ini "
    "sengaja, supaya Owner (siapa pun yang memegang login Owner) tidak bisa "
    "mengaktifkannya sendiri secara tidak sengaja."
)

# --- 4. Kasir ---
story += chapter("4. Panduan untuk Kasir")
story += section("4.1  Input Pesanan Manual")
story += [Paragraph(
    "Dipakai untuk mencatat pesanan tamu yang tidak scan QR sendiri, atau pesanan dari "
    "platform delivery. Langkah pertama pilih <b>Jenis Pesanan</b>: Makan di Tempat "
    "(lanjut pilih nomor meja), Bawa Pulang (tanpa meja), atau salah satu platform "
    "delivery yang aktif (harga menu otomatis menyesuaikan markup platform itu). "
    "Setelah itu tinggal klik tombol + pada tiap item menu yang dipesan, lalu tekan "
    "Buat Pesanan di bagian bawah.",
    styles["Body"],
)]
story.append(figure("owner-03-pesanan.png", "Input Pesanan Manual — pilih jenis pesanan, lalu menu"))

story += section("4.2  Proses Pembayaran")
story += [Paragraph(
    "Halaman Kasir menampilkan semua pesanan yang belum dibayar sebagai kartu, lengkap "
    "dengan rincian item & total. Pilih metode bayar (Cash/QRIS) lalu tekan Bayar — "
    "untuk Cash, isi “Uang Diterima” dan kembalian akan dihitung otomatis.",
    styles["Body"],
)]
story.append(figure("owner-05-kasir.png", "Kasir — antrian pesanan menunggu bayar"))
story += tip(
    "Salah input pesanan? Tekan tombol “Batalkan Pesanan” pada kartu itu — "
    "batalannya tercatat siapa & kapan di Laporan, jadi tetap ada jejaknya untuk audit."
)

story += section("4.3  Riwayat & Cetak Ulang Struk")
story += [Paragraph(
    "Di bagian bawah halaman Kasir ada “Riwayat Hari Ini” — daftar semua "
    "transaksi yang sudah lunas hari ini, lengkap dengan tombol Cetak Ulang di tiap "
    "baris. Berguna kalau kertas printer habis di tengah jalan, struk kusut/hilang, "
    "atau tamu minta struknya lagi.",
    styles["Body"],
)]
story.append(figure("owner-05b-riwayat.png", "Riwayat Hari Ini — cari & cetak ulang struk kapan saja", max_h=11 * cm))
story.append(figure("owner-14-struk.png", "Contoh struk pembayaran siap cetak", max_w=7 * cm, max_h=8 * cm))

# --- 5. Dapur ---
story += chapter("5. Panduan untuk Dapur")
story += section("5.1  Antrian Dapur")
story += [Paragraph(
    "Menampilkan semua pesanan yang masuk (dari tamu scan QR, kasir, maupun pelayan) "
    "dalam bentuk kartu, urut dari yang paling lama menunggu. Tiap kartu punya tombol "
    "untuk memajukan status pesanan: <b>Diterima → Diproses → Siap Diantar</b>.",
    styles["Body"],
)]
story.append(figure("owner-04-dapur.png", "Antrian Dapur — kartu pesanan urut waktu"))
story += [Paragraph(
    "Setiap ada pesanan baru masuk, halaman ini akan berbunyi otomatis (bisa dimatikan "
    "sementara lewat ikon speaker di kanan atas) — jadi dapur tidak perlu terus-"
    "menerus melihat layar untuk tahu ada pesanan baru.",
    styles["Body"],
)]
story += tip(
    "Pesanan dari platform delivery ditandai lencana kecil logo platform-nya di pojok "
    "kartu, supaya dapur bisa langsung tahu itu pesanan ojol tanpa harus baca detail."
)

# --- 6. Pelayan ---
story += chapter("6. Panduan untuk Pelayan")
story += section("6.1  Siap Diantar")
story += [Paragraph(
    "Menampilkan pesanan yang sudah ditandai “Siap” oleh Dapur dan menunggu "
    "diantar ke meja. Setelah pesanan sampai di meja tamu, tekan tombol “Tandai "
    "Sudah Diantar” pada kartu itu.",
    styles["Body"],
)]
story += [Paragraph(
    "Sama seperti Dapur, halaman ini berbunyi otomatis tiap ada pesanan baru berstatus "
    "Siap — jadi Pelayan tidak perlu bolak-balik cek halaman Dapur.",
    styles["Body"],
)]
story += section("6.2  Input Pesanan Manual")
story += [Paragraph(
    "Pelayan juga punya akses ke halaman Input Pesanan Manual (lihat bagian 4.1) untuk "
    "mencatat pesanan tamu yang minta dibantu, tanpa perlu memanggil kasir.",
    styles["Body"],
)]

# --- 7. Tamu ---
story += chapter("7. Panduan untuk Pelanggan/Tamu")
story += section("7.1  Scan QR & Pesan Sendiri")
story += [Paragraph(
    "Di tiap meja ada kartu QR code yang bisa di-scan langsung lewat kamera HP (tidak "
    "perlu aplikasi tambahan). Karena aplikasi ini jalan di jaringan WiFi toko (bukan "
    "internet), tamu wajib konek ke WiFi toko dulu — nama & password WiFi biasanya "
    "sudah tercantum di kartu QR yang sama.",
    styles["Body"],
)]
story.append(figure("customer-light-menu.png", "Menu tamu — mode terang", max_w=9 * cm, max_h=6.2 * cm))
story.append(figure("customer-dark-menu.png", "Menu tamu — mode gelap (ikut preferensi HP tamu)", max_w=9 * cm, max_h=6.2 * cm))
story += [Paragraph(
    "Pilih menu & jumlah lewat tombol +/-, lalu tekan “Kirim Pesanan” di bagian "
    "bawah layar. Pesanan langsung masuk ke Dapur tanpa perantara staf.",
    styles["Body"],
)]
story += tip(
    "Tampilan menu tamu otomatis mengikuti pengaturan mode terang/gelap bawaan HP "
    "masing-masing tamu — tidak perlu diatur manual."
)

story += section("7.2  Cek Status Pesanan")
story += [Paragraph(
    "Setelah pesanan terkirim, tamu bisa membuka lagi halaman yang sama untuk melihat "
    "status pesanannya secara real-time lewat garis waktu: Diterima → Diproses → "
    "Siap → Diantar. Halaman ini memperbarui diri sendiri secara berkala, tidak "
    "perlu ditekan refresh manual.",
    styles["Body"],
)]
story.append(figure("customer-light-status.png", "Status Pesanan — garis waktu Diterima s/d Diantar", max_w=10 * cm))
story += [Paragraph(
    "Kalau tamu ingin menambah menu ke pesanan yang sama (belum dibayar), tekan tombol "
    "“Tambah/Edit Menu” di halaman status ini.",
    styles["Body"],
)]

# --- 8. Keamanan ---
story += chapter("8. Keamanan & Mode Perbaikan")
story += [Paragraph(
    "Beberapa hal yang sudah dijaga otomatis oleh sistem, tidak perlu diatur manual "
    "oleh staf sehari-hari:",
    styles["Body"],
)]
story += bullets([
    "Password staf disimpan terenkripsi, tidak pernah bisa dilihat siapa pun termasuk Owner (kalau lupa, harus diatur ulang, bukan “dilihat lagi”).",
    "Sesi login otomatis berakhir kalau tidak ada aktivitas dalam waktu tertentu — keamanan tambahan kalau device staf tertinggal menyala.",
    "Percobaan login yang gagal berkali-kali dalam waktu singkat akan ditahan sementara — mencegah orang lain menebak-nebak password.",
    "Pesanan tamu lewat QR dilindungi kode PIN 4 digit per pesanan, supaya tamu meja lain tidak bisa menambah/menghapus pesanan yang bukan miliknya.",
])
story += section("Mode Perbaikan (Maintenance Mode)")
story += [Paragraph(
    "Kalau Owner sedang melakukan perubahan besar (mis. ganti banyak menu sekaligus) "
    "dan ingin memastikan tidak ada staf lain yang memakai aplikasi sementara waktu, "
    "aktifkan Mode Perbaikan lewat Pengaturan → Sistem. Selama aktif, cuma akun "
    "Owner yang masih bisa mengakses aplikasi — akun lain akan melihat halaman "
    "pemberitahuan sampai Mode Perbaikan dimatikan lagi.",
    styles["Body"],
)]

# --- 9. FAQ ---
story += chapter("9. Tips & Pertanyaan Umum")
faq = [
    ("Aplikasi tidak bisa dibuka sama sekali dari HP staf, padahal biasanya bisa.",
     "Pastikan HP sudah konek ke WiFi toko yang benar (bukan paket data pribadi). Kalau "
     "sudah konek WiFi tapi tetap tidak bisa, kemungkinan komputer/mini PC server sedang "
     "mati atau belum menyala — hubungi Owner/developer."),
    ("Menu yang baru ditambahkan tidak muncul di halaman tamu.",
     "Cek dulu apakah stok bahan baku resepnya masih cukup (kalau ada resep yang "
     "diatur) — item dengan bahan habis otomatis disembunyikan. Kalau tidak ada "
     "resep sama sekali, coba paksa refresh halaman (tarik ke bawah di HP, atau tekan "
     "reload di browser)."),
    ("Pesanan yang salah masuk ke Dapur, bagaimana cara membatalkannya?",
     "Pembatalan pesanan dilakukan dari halaman Kasir (tombol “Batalkan Pesanan” "
     "di kartu pesanan itu), bukan dari halaman Dapur — supaya pembatalan tetap "
     "tercatat dengan rapi di laporan."),
    ("Notifikasi suara tidak berbunyi di HP dapur/kasir.",
     "Cek ikon speaker di pojok kanan atas halaman itu — mungkin sedang di-mute. "
     "Kalau sudah tidak di-mute tapi tetap tidak bunyi, cek juga volume notifikasi di "
     "Pengaturan → Notifikasi (khusus Owner)."),
    ("Bagaimana cara mengganti password akun sendiri?",
     "Untuk sekarang, penggantian password staf dilakukan Owner lewat halaman Kelola "
     "User. Segera minta Owner ganti password default begitu akun pertama kali dipakai."),
    ("Printer struk tidak mencetak / kertas macet di tengah transaksi.",
     "Transaksi tetap tersimpan lunas walau gagal cetak — cari transaksinya di "
     "“Riwayat Hari Ini” pada halaman Kasir, lalu tekan “Cetak Ulang” "
     "setelah printer/kertas beres."),
]
for q, a in faq:
    story += [Paragraph(q, styles["H3"]), Paragraph(a, styles["Body"])]

# --- 10. Penutup ---
story += chapter("10. Penutup")
story += [Paragraph(
    "Buku panduan ini mencakup penggunaan sehari-hari aplikasi Orulabs Cafe POS untuk "
    "semua peran. Untuk hal-hal teknis di luar cakupan buku ini — instalasi awal, "
    "pemindahan ke komputer/mini PC baru, atau masalah yang tidak kunjung selesai "
    "setelah mengikuti langkah di atas — silakan hubungi developer aplikasi.",
    styles["Body"],
)]
story += [Spacer(1, 20), Paragraph("Selamat menggunakan Orulabs Cafe POS!", styles["H3"])]


def build():
    doc = ManualDoc(
        OUT_PATH, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=1.9 * cm, bottomMargin=1.8 * cm,
        title="Buku Panduan Orulabs Cafe POS",
        author="Orulabs",
    )
    # multiBuild: perlu 2+ pass supaya nomor halaman di Daftar Isi akurat.
    doc.multiBuild(story)


if __name__ == "__main__":
    build()
    print("Selesai:", OUT_PATH)
