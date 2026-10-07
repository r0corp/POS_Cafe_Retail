"""Cangkang iOS untuk Oru POS GO (uji coba).

Menjalankan aplikasi Flask GO yang sama persis (umkm_app.run) di thread latar
di dalam app, lalu menampilkannya lewat WebView - pola yang sama dengan
MainActivity.java di Android.
"""

import asyncio
import os
import re
import sys
import threading
import traceback
import urllib.request

import toga
from toga.style import Pack

PORT = 8731  # tetap, supaya CI bisa memeriksa dari luar simulator
URL = "http://127.0.0.1:%d" % PORT


class OruPosGo(toga.App):
    def startup(self):
        self.files_dir = str(self.paths.data)
        os.makedirs(self.files_dir, exist_ok=True)
        # Jalur cetak khusus iPhone (tanpa Bluetooth klasik) - lihat _is_ios() di staff.py.
        os.environ["ORULABS_MOBILE_OS"] = "ios"
        os.environ["ORULABS_APP_VERSION"] = str(self.version or "0")
        self.error_file = os.path.join(self.files_dir, "server_error.txt")
        if os.path.exists(self.error_file):
            os.remove(self.error_file)

        # Kode GO (hasil sync_go.py) ada di folder "gopos" - nama modul di
        # dalamnya (app, config, licensing, umkm_app) top-level, jadi folder
        # itu dimasukkan ke sys.path.
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gopos"))

        threading.Thread(target=self._serve, name="flask", daemon=True).start()

        self.web = toga.WebView(style=Pack(flex=1), on_webview_load=self._on_load)
        # Judul spasi: bilah atas iOS tidak perlu menampilkan nama app (warnanya disamakan dengan halaman).
        self.main_window = toga.MainWindow(title=" ")
        self.main_window.content = self.web
        self.main_window.show()
        self.add_background_task(self._open_when_ready)

    async def _on_load(self, widget, **kwargs):
        """Setiap halaman selesai dimuat: samakan warna bilah atas iOS dengan latar halaman
        (gelap atau terang sesuai tema yang dipilih pemakai), supaya tidak ada pita putih."""
        try:
            value = await self.web.evaluate_javascript("getComputedStyle(document.body).backgroundColor")
            self._apply_bar(str(value))
        except Exception:
            traceback.print_exc()

    def _apply_bar(self, css_color):
        nums = [float(x) for x in re.findall(r"[\d.]+", css_color)[:3]]
        if len(nums) < 3:
            return
        r, g, b = (n / 255.0 for n in nums)
        dark = (0.299 * r + 0.587 * g + 0.114 * b) < 0.5
        try:
            from rubicon.objc import ObjCClass

            color = ObjCClass("UIColor").colorWithRed(r, green=g, blue=b, alpha=1.0)
            appearance = ObjCClass("UINavigationBarAppearance").alloc().init()
            appearance.configureWithOpaqueBackground()
            appearance.backgroundColor = color
            appearance.shadowColor = color
            impl = self.main_window._impl
            bar = impl.container.controller.navigationBar
            bar.standardAppearance = appearance
            bar.scrollEdgeAppearance = appearance
            bar.compactAppearance = appearance
            impl.native.backgroundColor = color
            # Judul teks tidak dipakai sama sekali: ganti dengan tampilan kosong (judul " " pun
            # tampil sebagai tanda kutip di iOS).
            top = impl.container.controller.topViewController
            top.navigationItem.titleView = ObjCClass("UIView").alloc().init()
            # 2 = gelap (teks status bar putih), 1 = terang
            impl.native.overrideUserInterfaceStyle = 2 if dark else 1
        except Exception:
            # bukan iOS (mis. uji lokal di Windows/macOS biasa) - abaikan
            pass

    def _serve(self):
        try:
            import licensing

            from . import ios_support

            ios_support.patch_licensing(licensing, self.files_dir)
            import umkm_app

            umkm_app.run(PORT, self.files_dir)
        except BaseException:
            with open(self.error_file, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            traceback.print_exc()

    @staticmethod
    def _ping():
        try:
            with urllib.request.urlopen(URL + "/login", timeout=2) as r:
                return r.status
        except Exception:
            return None

    async def _open_when_ready(self, app, **kwargs):
        loop = asyncio.get_running_loop()
        for _ in range(240):  # maks. ~2 menit (pertama kali: buat database + salin static)
            if os.path.exists(self.error_file):
                break
            if await loop.run_in_executor(None, self._ping):
                self.web.url = URL
                return
            await asyncio.sleep(0.5)
        detail = ""
        if os.path.exists(self.error_file):
            detail = open(self.error_file, encoding="utf-8").read()
        html = "<html><body style='font-family:sans-serif;padding:16px'><h3>Server GO gagal start</h3><pre style='white-space:pre-wrap;font-size:12px'>%s</pre></body></html>" % (
            detail.replace("&", "&amp;").replace("<", "&lt;") or "tidak ada detail (timeout)"
        )
        self.web.set_content(URL, html)


def main():
    return OruPosGo(formal_name="Oru POS GO", app_id="id.orulabs.orupos")
