"""Salin kode GO (android-app-umkm/app/src/main/python) ke src/orupos/gopos.

Kode GO TIDAK diduplikasi di git - folder gopos di-ignore dan dibuat ulang
oleh skrip ini (dijalankan lokal dan oleh CI sebelum build).
"""

import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "android-app-umkm", "app", "src", "main", "python"))
DST = os.path.join(HERE, "src", "orupos", "gopos")

if os.path.exists(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "*.db"))
count = sum(len(files) for _, _, files in os.walk(DST))
print("gopos disalin dari", SRC, "->", count, "berkas")
