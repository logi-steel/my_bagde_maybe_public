# cpython
"""QR encoder check: the MicroPython implementation vs. segno (exact modules) and OpenCV (decode)."""
import binascii
import json
import os
import random
import subprocess
import sys
import tempfile

import numpy as np
import segno
import qrcode
from qrcode import constants, util
import cv2

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ENV = dict(os.environ, MICROPYPATH=os.pathsep.join([ROOT + "/firmware", ROOT + "/tests/mocks"]))


def run_mpy(cases):
    with tempfile.TemporaryDirectory() as d:
        cin, cout = os.path.join(d, "in.json"), os.path.join(d, "out.json")
        json.dump(cases, open(cin, "w"))
        r = subprocess.run(["micropython", os.path.join(ROOT, "tests", "qr_dump.py"), cin, cout],
                           env=ENV, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise SystemExit("micropython failed:\n" + r.stdout + r.stderr)
        return json.load(open(cout))


LEVEL = {"L": constants.ERROR_CORRECT_L, "M": constants.ERROR_CORRECT_M,
         "Q": constants.ERROR_CORRECT_Q, "H": constants.ERROR_CORRECT_H}


def ref_matrix(data, ver, ecc, mask):
    """Reference modules from python-qrcode (spec-conform padding, forced byte mode).

    segno is NOT used for this: it appends an extra 0x00 byte after the terminator when the
    terminator ends on a byte boundary (decodes fine, but is not bit-identical to the spec).
    """
    q = qrcode.QRCode(version=ver, error_correction=LEVEL[ecc], border=0, mask_pattern=mask)
    q.add_data(util.QRData(data, mode=util.MODE_8BIT_BYTE))
    q.make(fit=False)
    return [bytes(1 if v else 0 for v in row) for row in q.modules]


def segno_fits(n, ver, ecc):
    try:
        segno.make(b"a" * n, version=ver, error=ecc, mode="byte", micro=False, boost_error=False)
        return True
    except Exception:
        return False


# 1) capacities for every version/level (this validates the ECC tables)
caps = run_mpy([{"capacity": [v, e]} for v in range(1, 11) for e in "LMQH"])
i = 0
for v in range(1, 11):
    for e in "LMQH":
        c = caps[i]["capacity"]
        i += 1
        assert segno_fits(c, v, e), "v%d %s: segno rejects %d bytes" % (v, e, c)
        assert not segno_fits(c + 1, v, e), "v%d %s: segno accepts %d bytes (> mine)" % (v, e, c + 1)
print("capacity tables match segno for v1-v10 x L/M/Q/H")

# 2) exact module equality, every version x level x mask, payload at the capacity limit
rnd = random.Random(7)
cases, meta = [], []
for v in range(1, 11):
    for e in "LMQH":
        cap = caps[(v - 1) * 4 + "LMQH".index(e)]["capacity"]
        for mask in range(8):
            n = cap if mask % 2 == 0 else max(1, cap - rnd.randint(0, 6))
            payload = bytes(rnd.randint(32, 126) for _ in range(n))
            cases.append({"hex": binascii.hexlify(payload).decode(), "ecc": e, "mask": mask})
            meta.append((v, e, mask, payload, cap))
res = run_mpy(cases)
bad = 0
for r, (v, e, mask, payload, cap) in zip(res, meta):
    n = r["n"]
    mine = binascii.unhexlify(r["hex"])
    mine_rows = [mine[y * n:(y + 1) * n] for y in range(n)]
    # a short payload may fit a smaller version than the one the case was built for
    ref = ref_matrix(payload, (n - 17) // 4, e, mask)
    if mine_rows != ref:
        bad += 1
        print("MISMATCH v%d %s mask%d len%d" % (v, e, mask, len(payload)))
assert bad == 0, "%d / %d matrices differ from segno" % (bad, len(res))
print("%d QR matrices identical to python-qrcode (v1-v10 x L/M/Q/H x 8 masks)" % len(res))

# 3) auto mask selection: decodes with OpenCV, incl. UTF-8
payloads = [
    "https://github.com/logi-steel",
    "WIFI:T:WPA;S:BADGE-1234;P:abcd2345;;",
    "BEGIN:VCARD\nVERSION:3.0\nFN:Logi\nTEL:+48123456789\nEMAIL:a@b.pl\nEND:VCARD",
    "Zażółć gęślą jaźń — QR ✓",
    "x" * 100,
    "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz0123456789/:.?=&-_") for _ in range(180)),
]
cap10 = {e: caps[9 * 4 + "LMQH".index(e)]["capacity"] for e in "LMQH"}
cases = [{"hex": binascii.hexlify(p.encode()).decode(), "ecc": e, "mask": None}
         for p in payloads for e in "LMQH"
         if len(p.encode()) <= cap10[e]]
res = run_mpy(cases)
det = cv2.QRCodeDetector()
ok = 0
skipped = 0
for r, c in zip(res, cases):
    n = r["n"]
    m = np.frombuffer(binascii.unhexlify(r["hex"]), dtype=np.uint8).reshape(n, n)
    img = np.pad(1 - m, 4, constant_values=1).astype(np.uint8) * 255
    img = cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
    text, pts, _ = det.detectAndDecode(img)
    want = binascii.unhexlify(c["hex"]).decode()
    if text == want:
        ok += 1
    else:
        # OpenCV can't decode ECC levels whose payload doesn't fit (skipped by encoder) - any
        # other failure is a real bug
        print("DECODE FAIL ecc=%s len=%d got=%r" % (c["ecc"], len(want), text[:40]))
        skipped += 1
assert skipped == 0, "%d codes failed to decode" % skipped
print("%d auto-mask codes decoded by OpenCV" % ok)

# 4) timing as reported by MicroPython (host speed; the C3 is much slower)
res = run_mpy([{"hex": binascii.hexlify(b"https://github.com/logi-steel").decode(), "ecc": "M", "mask": None},
               {"hex": binascii.hexlify(b"x" * 150).decode(), "ecc": "M", "mask": None},
               {"hex": binascii.hexlify(b"x" * 150).decode(), "ecc": "M", "mask": 0}])
print("host time: url v%d %d ms | 150B v%d auto-mask %d ms | fixed mask %d ms" % (
    (res[0]["n"] - 17) // 4, res[0]["ms"], (res[1]["n"] - 17) // 4, res[1]["ms"], res[2]["ms"]))
print("test_qr: OK")
