"""Pengganti bagian GO yang khusus Android (uji coba iOS).

licensing.get_device_id() di Android memakai ANDROID_ID lewat Chaquopy. Di iOS
dipakai id acak yang disimpan sekali di folder data app. (Versi produksi
sebaiknya memakai identifierForVendor lewat rubicon-objc; id acak ini hilang
kalau app dihapus-pasang ulang, seperti ANDROID_ID yang berubah saat reset.)
"""

import hashlib
import os
import uuid


def patch_licensing(licensing, data_dir):
    seed_file = os.path.join(data_dir, "device_seed.txt")
    if os.path.exists(seed_file):
        seed = open(seed_file, encoding="utf-8").read().strip()
    else:
        seed = uuid.uuid4().hex
        with open(seed_file, "w", encoding="utf-8") as f:
            f.write(seed)

    digest = hashlib.sha256(licensing._DEVICE_ID_SALT + seed.encode()).digest()[:10]
    # get_device_id() membaca cache ini lebih dulu, jadi jalur Android tidak pernah dipanggil.
    licensing._device_id_cache["id"] = licensing._b32encode(digest)
