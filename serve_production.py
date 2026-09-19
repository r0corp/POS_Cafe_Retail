"""
Menjalankan Cafe POS dengan WSGI server produksi (waitress), bukan
development server Flask.

Development server Flask (run.py, debug=True) TIDAK aman dipakai
selain di komputer sendiri untuk coding - debugger bawaannya bisa
dipakai orang lain untuk menjalankan kode sembarang di server kalau
aplikasi ini bisa diakses dari luar (jaringan kafe).

Cara pakai:
    python serve_production.py

Secara default listen di semua network interface (0.0.0.0) port 8000,
supaya bisa diakses tablet/HP lain (kasir, dapur, pelayan, dan tamu
lewat QR code) di jaringan WiFi yang sama. Ubah HOST/PORT di bawah
kalau perlu.

PENTING: setelah pindah ke port/IP ini, update BASE_URL di file .env
supaya QR code meja mengarah ke alamat yang benar, misalnya:
    BASE_URL=http://192.168.1.10:8000
lalu generate ulang QR code tiap meja lewat halaman Denah Meja (hapus
meja lama, tambah lagi dengan kode yang sama - QR otomatis dibuat ulang).
"""

from waitress import serve

from app import create_app


HOST = "0.0.0.0"
PORT = 8000

app = create_app()

app.config["DEBUG"] = False


if __name__ == "__main__":

    print(f"Cafe POS berjalan di http://{HOST}:{PORT}")
    print("(atau http://<ip-komputer-ini>:8000 dari tablet/HP lain di jaringan yang sama)")

    serve(
        app,
        host=HOST,
        port=PORT,
        threads=4,
    )
