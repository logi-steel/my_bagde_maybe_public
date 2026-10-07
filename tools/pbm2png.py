#!/usr/bin/env python3
"""Convert a PBM (P4) produced by the firmware into a scaled PNG.

  python3 tools/pbm2png.py in.pbm out.png [scale] [--bezel]
"""
import sys

from PIL import Image, ImageDraw


def read_pbm(path):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"P4"):
        raise SystemExit("not a P4 PBM: " + path)
    # header: P4 \n w h \n  (comments allowed)
    pos = 2
    tokens = []
    while len(tokens) < 2:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while data[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        tokens.append(int(data[start:pos]))
    pos += 1
    w, h = tokens
    bpr = (w + 7) // 8
    im = Image.new("L", (w, h), 255)
    px = im.load()
    for y in range(h):
        row = data[pos + y * bpr: pos + (y + 1) * bpr]
        for x in range(w):
            if row[x >> 3] & (0x80 >> (x & 7)):
                px[x, y] = 0
    return im


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    bezel = "--bezel" in sys.argv
    src, dst = args[0], args[1]
    scale = int(args[2]) if len(args) > 2 else 4
    im = read_pbm(src).convert("RGB")
    im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    if bezel:
        pad = 14 * scale // 2
        out = Image.new("RGB", (im.width + 2 * pad, im.height + 2 * pad), (40, 40, 44))
        ImageDraw.Draw(out).rectangle([pad - 3, pad - 3, pad + im.width + 2, pad + im.height + 2],
                                      outline=(10, 10, 10), width=3)
        out.paste(im, (pad, pad))
        im = out
    im.save(dst)


if __name__ == "__main__":
    main()
