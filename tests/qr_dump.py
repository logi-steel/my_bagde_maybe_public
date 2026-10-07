"""Helper run under MicroPython: encode QR cases from a JSON file, write results as JSON.

usage: micropython tests/qr_dump.py cases.json out.json
case:  {"hex": "<utf8 bytes as hex>", "ecc": "M", "mask": null | 0..7}
       {"capacity": [version, ecc]}
"""
import sys
import json
import time
import binascii
from badge import qr

cases = json.load(open(sys.argv[1]))
out = []
for c in cases:
    if "capacity" in c:
        v, e = c["capacity"]
        out.append({"capacity": qr.capacity(v, e)})
        continue
    data = binascii.unhexlify(c["hex"])
    t0 = time.ticks_ms()
    n, m = qr.encode(data, c["ecc"], mask=c.get("mask"))
    dt = time.ticks_diff(time.ticks_ms(), t0)
    out.append({"n": n, "hex": binascii.hexlify(m).decode(), "ms": dt})
json.dump(out, open(sys.argv[2], "w"))
