"""Jembatan cetak struk ke printer thermal Bluetooth - CUMA dipakai di
APK UMKM (versi Android standalone, lihat android-app-umkm/). Modul ini
mengimpor kelas Java/Android (lewat Chaquopy) yang cuma ada di
lingkungan Android, jadi JANGAN pernah di-import di server/mini PC -
lihat pengecekan os.environ["ORULABS_PLATFORM"] di
_print_receipt_to_printer (app/blueprints/staff.py) yang menjaga ini.

Printer Bluetooth murah (58mm) yang biasa dipakai UMKM umumnya
"transparan" - begitu dipasangkan (paired) lewat menu Bluetooth Android
biasa, dia langsung siap terima data mentah lewat koneksi SPP (Serial
Port Profile) standar, tanpa perlu app/driver khusus dari pabrikannya.
"""

SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"


def list_paired_printers():
    """Semua device Bluetooth yang SUDAH dipasangkan (paired) lewat
    Pengaturan Android - bukan hasil scan baru. User tetap wajib
    memasangkan printernya sendiri dulu lewat menu Bluetooth Android
    biasa (proses pairing/PIN itu sendiri tidak bisa - dan tidak perlu -
    dilakukan dari dalam aplikasi ini)."""

    from android.bluetooth import BluetoothAdapter

    adapter = BluetoothAdapter.getDefaultAdapter()
    if adapter is None or not adapter.isEnabled():
        return []

    devices = []
    iterator = adapter.getBondedDevices().iterator()
    while iterator.hasNext():
        device = iterator.next()
        devices.append({"name": device.getName() or device.getAddress(), "address": device.getAddress()})
    return devices


def send_escpos(data, device_address):
    """Kirim data mentah (bytes) ke printer Bluetooth lewat koneksi SPP -
    ini yang menggantikan win32print.WritePrinter() di server/mini PC."""

    if not device_address:
        raise RuntimeError("Pilih printer Bluetooth dulu di Pengaturan Toko.")

    from android.bluetooth import BluetoothAdapter
    from java.util import UUID

    adapter = BluetoothAdapter.getDefaultAdapter()
    if adapter is None:
        raise RuntimeError("HP ini tidak punya Bluetooth.")
    if not adapter.isEnabled():
        raise RuntimeError("Bluetooth sedang mati - nyalakan dulu.")

    device = adapter.getRemoteDevice(device_address)
    socket = device.createRfcommSocketToServiceRecord(UUID.fromString(SPP_UUID))
    try:
        # Perangkat lain (HP kasir yang tadi dipakai scan/pilih) bisa
        # masih memegang koneksi lama ke printer yang sama - batalkan
        # discovery dulu (disarankan resmi oleh dokumentasi Android)
        # supaya koneksi baru ini tidak lambat/gagal connect.
        adapter.cancelDiscovery()
        socket.connect()
        stream = socket.getOutputStream()
        stream.write(data)
        stream.flush()
    finally:
        socket.close()
