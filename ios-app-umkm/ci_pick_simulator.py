"""Cetak UDID simulator iPhone yang tersedia (runtime iOS terbaru) - dipakai CI."""

import json
import re
import subprocess
import sys

data = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))["devices"]


def version_of(runtime):
    m = re.search(r"iOS-(\d+)-(\d+)", runtime)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


runtimes = sorted((r for r in data if "iOS" in r and data[r]), key=version_of, reverse=True)
for runtime in runtimes:
    iphones = [d for d in data[runtime] if d["name"].startswith("iPhone")]
    # utamakan model reguler (bukan Pro Max / Plus) supaya layar mirip HP umum
    iphones.sort(key=lambda d: ("Pro" in d["name"] or "Plus" in d["name"] or "Air" in d["name"] or "e" == d["name"][-1], d["name"]))
    if iphones:
        print(iphones[0]["udid"])
        sys.exit(0)
sys.exit("tidak ada simulator iPhone")
