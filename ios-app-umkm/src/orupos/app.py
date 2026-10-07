"""Cangkang iOS untuk Oru POS GO (uji coba).

Menjalankan aplikasi Flask GO yang sama persis (umkm_app.run) di thread latar
di dalam app, lalu menampilkannya lewat WebView - pola yang sama dengan
MainActivity.java di Android.
"""

import asyncio
import os
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
        self.error_file = os.path.join(self.files_dir, "server_error.txt")
        if os.path.exists(self.error_file):
            os.remove(self.error_file)

        # Kode GO (hasil sync_go.py) ada di folder "gopos" - nama modul di
        # dalamnya (app, config, licensing, umkm_app) top-level, jadi folder
        # itu dimasukkan ke sys.path.
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "gopos"))

        threading.Thread(target=self._serve, name="flask", daemon=True).start()

        self.web = toga.WebView(style=Pack(flex=1))
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = self.web
        self.main_window.show()
        self.add_background_task(self._open_when_ready)

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
