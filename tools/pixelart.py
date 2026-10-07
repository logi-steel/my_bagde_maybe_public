#!/usr/bin/env python3
"""Pixel art for the badge, drawn in any text editor.

Draw with characters: '#' = ink (black on a normal page), '.' or space = nothing.
Lines starting with ';' are comments. That is the same convention as the "art" widget.

  python3 tools/pixelart.py to-pbm    heart.txt heart.pbm [--scale 2]    # -> file for the "image" widget
  python3 tools/pixelart.py to-json   heart.txt --x 10 --y 8 --scale 3   # -> paste into config.json
  python3 tools/pixelart.py to-ascii  logo.pbm [logo.txt]                 # edit an existing image as text
  python3 tools/pixelart.py from-image photo.png face.txt --width 40      # photo -> text, then touch it up
  python3 tools/pixelart.py preview   heart.txt heart.png [--scale 8]     # look at it on your PC
  python3 tools/pixelart.py normalize in.pbm out.pbm                      # any PBM (P1/P4) -> binary P4

Everything the firmware reads is binary PBM (P4, 1 = ink). The size of a PBM file is
ceil(width/8) * height bytes + a ~12 byte header, e.g. a full 250x122 screen is 3.9 KB.
"""
import argparse
import json
import sys

ON_DEFAULT = "#X@*1"


# ---------------------------------------------------------------- reading / writing
def read_art(path_or_text, on=ON_DEFAULT, from_text=False):
    """Return a list of equally long rows of 0/1 (1 = ink)."""
    text = path_or_text if from_text else open(path_or_text, encoding="utf-8").read()
    rows = [ln.rstrip("\r\n") for ln in text.split("\n") if not ln.startswith(";")]
    while rows and not rows[-1].strip():
        rows.pop()
    while rows and not rows[0].strip():
        rows.pop(0)
    if not rows:
        raise SystemExit("the drawing is empty")
    width = max(len(r) for r in rows)
    return [[1 if i < len(r) and r[i] in on else 0 for i in range(width)] for r in rows]


def scale_rows(rows, n):
    if n <= 1:
        return rows
    out = []
    for r in rows:
        wide = [v for v in r for _ in range(n)]
        out.extend([list(wide) for _ in range(n)])
    return out


def to_pbm(rows):
    h, w = len(rows), len(rows[0])
    bpr = (w + 7) // 8
    out = bytearray(b"P4\n%d %d\n" % (w, h))
    for r in rows:
        row = bytearray(bpr)
        for x, v in enumerate(r):
            if v:
                row[x >> 3] |= 0x80 >> (x & 7)
        out += row
    return bytes(out)


def read_pbm(path):
    """P4 or P1 PBM -> rows of 0/1 (1 = ink)."""
    data = open(path, "rb").read()
    magic = data[:2]
    if magic not in (b"P4", b"P1"):
        raise SystemExit("%s is not a PBM (P1/P4)" % path)
    pos, nums = 2, []
    while len(nums) < 2:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            while data[pos:pos + 1] != b"\n":
                pos += 1
            continue
        start = pos
        while not data[pos:pos + 1].isspace():
            pos += 1
        nums.append(int(data[start:pos]))
    w, h = nums
    if magic == b"P4":
        pos += 1
        bpr = (w + 7) // 8
        body = data[pos:pos + bpr * h]
        if len(body) < bpr * h:
            raise SystemExit("%s is truncated" % path)
        return [[(body[y * bpr + (x >> 3)] >> (7 - (x & 7))) & 1 for x in range(w)] for y in range(h)]
    digits = [c for c in data[pos:].decode() if c in "01"]
    if len(digits) < w * h:
        raise SystemExit("%s is truncated" % path)
    return [[int(digits[y * w + x]) for x in range(w)] for y in range(h)]


def rows_to_text(rows, on="#", off="."):
    return "\n".join("".join(on if v else off for v in r) for r in rows) + "\n"


def widget_json(rows_text, x, y, scale, ink, extra=None):
    w = {"type": "art", "x": x, "y": y, "rows": rows_text}
    if scale != 1:
        w["scale"] = scale
    if ink != "black":
        w["ink"] = ink
    if extra:
        w.update(extra)
    return w


# ---------------------------------------------------------------- commands
def cmd_to_pbm(a):
    rows = scale_rows(read_art(a.src, a.on), a.scale)
    data = to_pbm(rows)
    open(a.dst, "wb").write(data)
    print("%s: %dx%d px, %d bytes" % (a.dst, len(rows[0]), len(rows), len(data)))


def cmd_to_json(a):
    rows = read_art(a.src, a.on)
    text = [r for r in rows_to_text(rows).split("\n") if r]
    extra = {"on": a.on} if a.on != ON_DEFAULT else None
    widget = widget_json(text, a.x, a.y, a.scale, a.ink, extra)
    if a.pretty:
        print(json.dumps(widget, indent=2))
    else:
        print(json.dumps(widget))


def cmd_to_ascii(a):
    text = rows_to_text(read_pbm(a.src))
    if a.dst:
        open(a.dst, "w", encoding="utf-8").write(text)
        print("%s written" % a.dst)
    else:
        sys.stdout.write(text)


def cmd_from_image(a):
    from PIL import Image, ImageOps
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
        im = im.convert("1")
    rows = [[1 if im.getpixel((x, y)) == 0 else 0 for x in range(a.width)] for y in range(h)]
    open(a.dst, "w", encoding="utf-8").write(rows_to_text(rows))
    print("%s: %dx%d characters" % (a.dst, a.width, h))


def cmd_preview(a):
    from PIL import Image
    rows = read_art(a.src, a.on)
    h, w = len(rows), len(rows[0])
    im = Image.new("L", (w, h), 255)
    for y, r in enumerate(rows):
        for x, v in enumerate(r):
            if v:
                im.putpixel((x, y), 0)
    im.resize((w * a.scale, h * a.scale), Image.NEAREST).save(a.dst)
    print("%s: %dx%d px" % (a.dst, w * a.scale, h * a.scale))


def cmd_normalize(a):
    rows = read_pbm(a.src)
    open(a.dst, "wb").write(to_pbm(rows))
    print("%s: binary PBM %dx%d" % (a.dst, len(rows[0]), len(rows)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *args):
        p = sub.add_parser(name)
        for spec, kw in args:
            p.add_argument(*spec, **kw)
        p.set_defaults(fn=fn)
        return p

    on = (("--on",), dict(default=ON_DEFAULT, help="characters that mean ink (default %s)" % ON_DEFAULT))
    add("to-pbm", cmd_to_pbm, (("src",), {}), (("dst",), {}), (("--scale",), dict(type=int, default=1)), on)
    add("to-json", cmd_to_json, (("src",), {}), (("--x",), dict(type=int, default=0)),
        (("--y",), dict(type=int, default=0)), (("--scale",), dict(type=int, default=1)),
        (("--ink",), dict(choices=("black", "white"), default="black")),
        (("--pretty",), dict(action="store_true")), on)
    add("to-ascii", cmd_to_ascii, (("src",), {}), (("dst",), dict(nargs="?")))
    add("from-image", cmd_from_image, (("src",), {}), (("dst",), {}),
        (("--width",), dict(type=int, required=True)), (("--height",), dict(type=int)),
        (("--threshold",), dict(type=int, nargs="?", const=128)), (("--invert",), dict(action="store_true")))
    add("preview", cmd_preview, (("src",), {}), (("dst",), {}), (("--scale",), dict(type=int, default=8)), on)
    add("normalize", cmd_normalize, (("src",), {}), (("dst",), {}))
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
