#!/usr/bin/env python3
"""Rasterise a TTF/OTF into the badge's compact bitmap font format (.fnt).

  python3 tools/make_font.py --ttf SomeFont.ttf --size 24 --out firmware/fonts/my24.fnt
  python3 tools/make_font.py --all          # rebuild the fonts shipped in firmware/fonts

Rendering is strictly 1-bit (no anti-aliasing) - that is what looks crisp on e-ink.
Format (little endian), read by badge.canvas.Font:
  "BF1" height ascent count(u16) pad(u8)
  count * (codepoint u16, width u8, advance u8, xoffset i8, data-offset u16)  sorted by codepoint
  glyph rows: ceil(width/8) bytes per row, `height` rows, MSB = leftmost, bit set = ink
"""
import argparse
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "firmware", "fonts")

DEJAVU = "/usr/share/fonts/truetype/dejavu/"
UNIFONT = "/usr/share/fonts/opentype/unifont/unifont.otf"


def rng(a, b):
    return list(range(a, b + 1))


POLISH = [ord(c) for c in "ĄĆĘŁŃÓŚŹŻąćęłńóśźż"]
PUNCT = [ord(c) for c in "°·•–—…€™‘’“”«»±×÷§©®¿¡"]
SYMBOLS = [ord(c) for c in "←↑→↓✓✗★☆♥♪☺☎✉⚙⚡⌂"]

BASIC = rng(0x20, 0x7E) + POLISH + [ord(c) for c in "°·•–—…€’“”→✓★♥"]
FULL = rng(0x20, 0x7E) + rng(0xA0, 0xFF) + rng(0x100, 0x17F) + PUNCT + SYMBOLS

SHIPPED = [
    # name,   file,                              size, charset
    ("s12", DEJAVU + "DejaVuSans.ttf", 12, FULL),
    ("s16", DEJAVU + "DejaVuSans.ttf", 16, FULL),
    ("b16", DEJAVU + "DejaVuSans-Bold.ttf", 16, FULL),
    ("b24", DEJAVU + "DejaVuSans-Bold.ttf", 24, BASIC),
    ("b36", DEJAVU + "DejaVuSans-Bold.ttf", 36, BASIC),
    ("m12", DEJAVU + "DejaVuSansMono.ttf", 12, BASIC),
    ("px16", UNIFONT, 16, BASIC),
]


def build(ttf, size, charset, out):
    font = ImageFont.truetype(ttf, size)
    cmap = TTFont(ttf, fontNumber=0).getBestCmap()
    asc, desc = font.getmetrics()
    height = asc + desc
    glyphs = []
    for cp in sorted(set(charset)):
        if cp not in cmap and cp != 0x20:
            continue
        ch = chr(cp)
        adv = int(round(font.getlength(ch)))
        l, t, r, b = font.getbbox(ch, anchor="ls")
        blank = (r <= l) or (b <= t)
        x0 = min(0, l) if not blank else 0
        w = max(adv, r) - x0 if not blank else max(adv, 1)
        w = min(max(w, 1), 255)
        im = Image.new("1", (w, height), 0)
        d = ImageDraw.Draw(im)
        d.fontmode = "1"
        d.text((-x0, asc), ch, font=font, fill=1, anchor="ls")
        bpr = (w + 7) // 8
        rows = bytearray()
        for y in range(height):
            row = bytearray(bpr)
            for x in range(w):
                if im.getpixel((x, y)):
                    row[x >> 3] |= 0x80 >> (x & 7)
            rows += row
        glyphs.append((cp, w, min(adv, 255), x0, bytes(rows)))
    index = bytearray()
    blob = bytearray()
    for cp, w, adv, xoff, data in glyphs:
        index += struct.pack("<HBBbH", cp, w, adv, xoff, len(blob))
        blob += data
    if len(blob) > 0xFFFF:
        raise SystemExit("%s: glyph data %d bytes > 65535, use a smaller charset" % (out, len(blob)))
    head = b"BF1" + struct.pack("<BBH", height, asc, len(glyphs)) + b"\x00"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "wb") as f:
        f.write(head + index + blob)
    return height, len(glyphs), len(head) + len(index) + len(blob)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ttf")
    ap.add_argument("--size", type=int)
    ap.add_argument("--out")
    ap.add_argument("--charset", choices=("basic", "full"), default="basic")
    ap.add_argument("--all", action="store_true", help="rebuild the shipped fonts")
    a = ap.parse_args()
    if a.all:
        for name, ttf, size, cs in SHIPPED:
            out = os.path.join(OUT_DIR, name + ".fnt")
            h, n, total = build(ttf, size, cs, out)
            print("%-5s %2dpx  height=%2d glyphs=%3d  %6d bytes" % (name, size, h, n, total))
        return
    if not (a.ttf and a.size and a.out):
        ap.error("need --ttf, --size and --out (or --all)")
    h, n, total = build(a.ttf, a.size, FULL if a.charset == "full" else BASIC, a.out)
    print("height=%d glyphs=%d bytes=%d" % (h, n, total))


if __name__ == "__main__":
    sys.exit(main())
