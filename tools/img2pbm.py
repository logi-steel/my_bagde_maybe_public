#!/usr/bin/env python3
"""Convert any image to a 1-bit PBM the badge can draw (type "image" widget).

  python3 tools/img2pbm.py photo.jpg firmware/img/me.pbm --width 64
  python3 tools/img2pbm.py logo.png firmware/img/logo.pbm --width 48 --threshold   # no dithering

PBM P4: bit 1 = black ink. Floyd-Steinberg dithering is on by default (good for photos).
"""
import argparse

from PIL import Image, ImageOps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int)
    ap.add_argument("--threshold", nargs="?", const=128, type=int, help="hard threshold instead of dithering")
    ap.add_argument("--invert", action="store_true")
    a = ap.parse_args()
    im = Image.open(a.src)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im.convert("RGBA"))
        im = bg
    im = im.convert("L")
    h = a.height or max(1, round(im.height * a.width / im.width))
    im = im.resize((a.width, h), Image.LANCZOS)
    if a.invert:
        im = ImageOps.invert(im)
    if a.threshold is not None:
        im = im.point(lambda v: 255 if v >= a.threshold else 0).convert("1", dither=Image.NONE)
    else:
        im = im.convert("1")  # Floyd-Steinberg
    w, h = im.size
    bpr = (w + 7) // 8
    out = bytearray(b"P4\n%d %d\n" % (w, h))
    for y in range(h):
        row = bytearray(bpr)
        for x in range(w):
            if im.getpixel((x, y)) == 0:  # black pixel -> ink bit 1
                row[x >> 3] |= 0x80 >> (x & 7)
        out += row
    with open(a.dst, "wb") as f:
        f.write(out)
    print("%s: %dx%d, %d bytes" % (a.dst, w, h, len(out)))


if __name__ == "__main__":
    main()
