#!/usr/bin/env python3
"""Build and verify the 3D-printable case.

  python3 tools/check_case.py            # verify + export STL into case/stl
  python3 tools/check_case.py --renders  # also (re)render the preview PNGs into docs/img (needs xvfb)

What is checked (all must pass):
  * OpenSCAD asserts in case/badge_case.scad (columns vs panel, battery vs XIAO, ...)
  * interference: stand-ins for panel / driver board / XIAO / battery / switch must not overlap
    the shell or the bezel, the bezel must not overlap the shell, the button cap must clear its hole
    (touching faces are fine, so the test looks at the *volume* of the intersection)
  * every exported STL is a closed, consistently wound solid with positive volume
  * variants (FPC on the right, magnet pockets) pass the same checks
  * a negative test: an oversized battery MUST trip an assert (proves the asserts are live)
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import trimesh

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCAD = os.path.join(ROOT, "case", "badge_case.scad")
STL_DIR = os.path.join(ROOT, "case", "stl")
IMG_DIR = os.path.join(ROOT, "docs", "img")
PARTS = ["shell", "bezel", "cap", "fit_test", "gauge"]
CHECKS = ["check_shell", "check_bezel", "check_fit", "check_cap"]


def openscad(part, out, defs=(), extra=()):
    cmd = ["openscad", "-o", out, "-D", 'part="%s"' % part]
    for d in defs:
        cmd += ["-D", d]
    cmd += list(extra) + [SCAD]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode, r.stderr


def interference_ok(path):
    """True when the intersection is empty or has (almost) no volume."""
    if not os.path.exists(path) or os.path.getsize(path) < 100:
        return True, "empty"
    m = trimesh.load(path, force="mesh")
    if len(m.faces) == 0:
        return True, "empty"
    ext = m.extents
    if min(ext) < 0.01:
        return True, "touching faces only (%.2f x %.2f x %.2f mm)" % tuple(ext)
    return False, "OVERLAP %.2f x %.2f x %.2f mm at %s" % (ext[0], ext[1], ext[2], np.round(m.bounds[0], 1))


def check_variant(name, defs, tmp, export=None):
    ok = True
    print("--", name)
    for c in CHECKS:
        out = os.path.join(tmp, "%s_%s.stl" % (name, c))
        rc, err = openscad(c, out, defs)
        if "top level object is empty" in err:   # OpenSCAD exits non-zero for an EMPTY result = no overlap
            print("   %-12s ok  empty" % c)
            continue
        if rc != 0 or "ERROR" in err or "Assertion" in err:
            print("   %-12s FAILED to render: %s" % (c, err.strip().splitlines()[-1] if err.strip() else rc))
            ok = False
            continue
        good, msg = interference_ok(out)
        print("   %-12s %s %s" % (c, "ok " if good else "BAD", msg))
        ok &= good
    for p in PARTS:
        out = os.path.join(export or tmp, "%s.stl" % p if export else "%s_%s.stl" % (name, p))
        rc, err = openscad(p, out, defs)
        if rc != 0:
            print("   %-12s FAILED: %s" % (p, err.strip().splitlines()[-1]))
            ok = False
            continue
        m = trimesh.load(out, force="mesh")
        good = m.is_watertight and m.is_winding_consistent and m.volume > 0
        e = m.extents
        print("   %-12s %s  %5.1f x %5.1f x %5.1f mm  %6.2f cm3  %s" % (
            p + ".stl", "ok " if good else "BAD", e[0], e[1], e[2], m.volume / 1000.0,
            "" if good else "(not a closed solid!)"))
        ok &= good
    return ok


def renders():
    os.makedirs(IMG_DIR, exist_ok=True)
    views = [
        ("case_assembly.png", "assembly", "0,0,6,58,0,28,175"),
        ("case_exploded.png", "exploded", "0,0,18,62,0,28,235"),
        ("case_back.png", "assembly", "0,0,-2,-122,0,200,160"),
        ("case_parts.png", "plate", "6,14,4,50,0,18,215"),
        ("case_inside.png", "shell", "0,0,6,48,0,18,150"),
    ]
    for fname, part, cam in views:
        out = os.path.join(IMG_DIR, fname)
        r = subprocess.run(["xvfb-run", "-a", "openscad", "-o", out, "--imgsize=1400,900", "--camera=" + cam,
                            "--projection=p", "-D", 'part="%s"' % part, SCAD], capture_output=True, text=True)
        print("render", fname, "ok" if r.returncode == 0 else "FAILED: " + r.stderr[-200:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--renders", action="store_true")
    a = ap.parse_args()
    if not shutil.which("openscad"):
        sys.exit("openscad not found (apt install openscad)")
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(STL_DIR, exist_ok=True)
        ok &= check_variant("default", [], tmp, export=STL_DIR)
        ok &= check_variant("fpc_right", ["fpc_left=false"], tmp)
        ok &= check_variant("magnets", ["magnets=true"], tmp)
        print("-- negative test (must fail)")
        rc, err = openscad("shell", os.path.join(tmp, "neg.stl"), ["bat=[52,21.5,6.5]"])
        tripped = "do not fit" in err or "Assertion" in err
        print("   oversized battery trips an assert:", "ok" if tripped else "NO - asserts are not working!")
        ok &= tripped
    if a.renders:
        renders()
    print("CASE CHECK:", "OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
