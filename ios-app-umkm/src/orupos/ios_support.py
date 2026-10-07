"""Pengganti bagian GO yang khusus Android.

licensing.get_device_id() di Android memakai ANDROID_ID lewat Chaquopy. Di iOS
dipakai identifierForVendor (UIDevice) - stabil selama masih ada app dari vendor
yang sama di perangkat, dan berubah kalau semua app vendor dihapus (mirip
ANDROID_ID yang berubah saat reset pabrik). Kalau tidak bisa dibaca (mis. saat
uji di Windows/macOS biasa), dipakai id acak yang disimpan sekali di folder data.
"""

import hashlib
import os
import uuid


def _vendor_id():
    try:
        from rubicon.objc import ObjCClass

        value = ObjCClass("UIDevice").currentDevice.identifierForVendor
        if value is not None:
            return str(value.UUIDString)
    except Exception:
        pass
    return None


def patch_licensing(licensing, data_dir):
    seed = _vendor_id()
    if not seed:
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
