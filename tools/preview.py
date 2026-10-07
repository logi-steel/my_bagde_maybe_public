#!/usr/bin/env python3
"""Preview your badge pages on the PC - same renderer as the device, no hardware needed.

  python3 tools/preview.py                       # firmware/config.json -> docs/img/preview.png
  python3 tools/preview.py my.json out.png --rotation 90 --scale 3

Needs: `micropython` (unix port) on PATH (or $MICROPYTHON) and Pillow.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from pbm2png import read_pbm  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", nargs="?", default=os.path.join(ROOT, "firmware", "config.json"))
    ap.add_argument("out", nargs="?", default=os.path.join(ROOT, "docs", "img", "preview.png"))
    ap.add_argument("--rotation", type=int)
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--cols", type=int, default=2)
    a = ap.parse_args()
    mpy = os.environ.get("MICROPYTHON") or shutil.which("micropython")
    if not mpy:
        sys.exit("micropython not found (apt install micropython, or set $MICROPYTHON)")
    with tempfile.TemporaryDirectory() as d:
        cmd = [mpy, os.path.join(HERE, "render_pages.py"), os.path.abspath(os.path.join(ROOT, "firmware")),
               os.path.abspath(a.config), d]
        if a.rotation is not None:
            cmd.append(str(a.rotation))
        r = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode:
            sys.exit(r.stderr)
        n = 0
        imgs = []
        while os.path.exists(os.path.join(d, "page%d.pbm" % n)):
            im = read_pbm(os.path.join(d, "page%d.pbm" % n)).convert("RGB")
            imgs.append(im.resize((im.width * a.scale, im.height * a.scale), Image.NEAREST))
            n += 1
    if not imgs:
        sys.exit("no pages rendered")
    pad = 10 * a.scale
    cw, ch = imgs[0].size
    cols = min(a.cols, len(imgs))
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + pad) + pad, rows * (ch + pad) + pad), (52, 56, 64))
    dr = ImageDraw.Draw(sheet)
    for i, im in enumerate(imgs):
        x = pad + (i % cols) * (cw + pad)
        y = pad + (i // cols) * (ch + pad)
        dr.rectangle([x - 3, y - 3, x + cw + 2, y + ch + 2], outline=(15, 15, 15), width=3)
        sheet.paste(im, (x, y))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
