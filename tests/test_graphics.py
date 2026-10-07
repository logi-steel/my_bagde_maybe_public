"""ASCII art widget, scaled bitmaps, ctx.image() - checked pixel by pixel."""
import json
from helpers import fresh_root, black_pixels
from badge import util, config, layout
from badge.canvas import Canvas, BLACK, WHITE

root = fresh_root()


def grid(c, x0, y0, w, h, ink=BLACK):
    return ["".join("#" if c.get(x0 + x, y0 + y) == ink else "." for x in range(w)) for y in range(h)]


def write_pbm(path, rows):
    w, h = len(rows[0]), len(rows)
    bpr = (w + 7) // 8
    out = bytearray(b"P4\n%d %d\n" % (w, h))
    for r in rows:
        row = bytearray(bpr)
        for x, ch in enumerate(r):
            if ch == "#":
                row[x >> 3] |= 0x80 >> (x & 7)
        out += row
    util.makedirs(util.parent(path))
    with open(util.p(path), "wb") as f:
        f.write(out)


# -- Canvas.art ----------------------------------------------------------------------------
c = Canvas(0)
assert c.art(5, 7, ["#.#", ".#.", "#.#"]) == (3, 3)
assert grid(c, 5, 7, 3, 3) == ["#.#", ".#.", "#.#"]
assert black_pixels(c) == 5, "nothing outside the art may be touched"

c = Canvas(0)
assert c.art(2, 3, ["#.", ".#"], scale=3) == (6, 6)
assert grid(c, 2, 3, 6, 6) == ["###...", "###...", "###...", "...###", "...###", "...###"]
assert black_pixels(c) == 18

c = Canvas(0)                                   # ink characters, ragged rows, unknown chars are 'off'
c.art(0, 0, ["#X@*1", "ab#", "", "  #"])
assert grid(c, 0, 0, 5, 4) == ["#####", "..#..", ".....", "..#.."]

c = Canvas(0)
c.art(0, 0, ["+.+", ".+."], on="+")
assert grid(c, 0, 0, 3, 2) == ["#.#", ".#."]

c = Canvas(0)                                   # white ink on black paper, transparent holes keep the black
c.clear(BLACK)
c.art(0, 0, ["#.#", ".#."], ink=WHITE)
assert grid(c, 0, 0, 3, 2, ink=WHITE) == ["#.#", ".#."]
assert c.get(1, 0) == BLACK and c.get(50, 50) == BLACK

c = Canvas(0)                                   # opaque erases what was below (inside the box only)
c.rect(0, 0, 10, 10, BLACK, True)
c.art(2, 2, ["#.#", "...", "#.#"], ink=BLACK, opaque=True)
assert grid(c, 0, 0, 7, 7) == ["#######", "#######", "###.###", "##...##", "###.###", "#######", "#######"]
assert c.get(3, 2) == WHITE and c.get(2, 2) == BLACK and c.get(0, 0) == BLACK and c.get(9, 9) == BLACK
assert c.get(3, 3) == WHITE, "opaque paper inside the box"

c = Canvas(0)                                   # invert: '.' becomes ink; short rows are padded
c.art(0, 0, ["#.", "#"], invert=True)
assert grid(c, 0, 0, 2, 2) == [".#", ".#"]

c = Canvas(0)                                   # degenerate inputs must not crash
assert c.art(0, 0, []) == (0, 0)
assert c.art(0, 0, [""]) == (0, 1)
assert c.art(0, 0, [12, None, "#"]) == (4, 3)   # non-strings are str()-ed ("12", "None")
try:
    c.art(0, 0, ["#" * 2001])
    raise AssertionError("absurd sizes must be refused")
except ValueError:
    pass
# off-screen / negative coordinates are clipped by the framebuffer, not an error
c = Canvas(0)
c.art(-2, -2, ["####", "####"], scale=2)
c.art(240, 115, ["#" * 40] * 20)
print("Canvas.art ok")

# art + rotation: logical coordinates stay logical
for rot in (90, 180, 270):
    c = Canvas(rot)
    c.art(1, 2, ["#.#", ".#."])
    assert grid(c, 1, 2, 3, 2) == ["#.#", ".#."], rot
print("art on all rotations ok")

# -- Canvas.bits(scale=) vs. manual expansion ------------------------------------------------
rows = ["#.#.##.#.#...", ".#..#..#.##.#", "#####........", ".............", "#.........#.#", "##.#.#.#.#.#.", "#...........#"]
write_pbm("/img/t.pbm", rows)
w, h, data = layout.read_pbm("/img/t.pbm")
assert (w, h) == (13, 7)
for scale in (1, 2, 3):
    for ink in (BLACK, WHITE):
        c = Canvas(0)
        if ink == WHITE:
            c.clear(BLACK)
        c.bits(4, 5, w, h, data, ink, scale)
        want = []
        for r in rows:
            wide = "".join(ch * scale for ch in r)
            want.extend([wide] * scale)
        assert grid(c, 4, 5, w * scale, h * scale, ink=ink) == want, (scale, ink)
print("bits(scale) ok")

# -- ctx.image(): scale / invert / opaque -----------------------------------------------------
cfg = config.parse("{}")
c = Canvas(0)
ctx = layout.Ctx(cfg, c)
assert ctx.image("img/t.pbm", 0, 0, scale=2) == (26, 14)
assert black_pixels(c) == 4 * sum(r.count("#") for r in rows)
c = Canvas(0)
ctx = layout.Ctx(cfg, c)
ctx.image("img/t.pbm", 0, 0, invert=True)           # inverted = ink drawn white; on a white page = invisible
assert black_pixels(c) == 0
c = Canvas(0)
c.rect(0, 0, 30, 30, BLACK, True)
ctx = layout.Ctx(cfg, c)
ctx.image("img/t.pbm", 0, 0, opaque=True)
assert c.get(0, 0) == BLACK and c.get(1, 0) == WHITE, "opaque clears the box, ink pixels stay ink"
print("ctx.image ok")

# -- read_pbm hardening --------------------------------------------------------------------
with open(util.p("/img/trunc.pbm"), "wb") as f:
    f.write(b"P4\n64 64\n\x00\x00")
with open(util.p("/img/p1.pbm"), "wb") as f:
    f.write(b"P1\n2 2\n1 0 0 1\n")
with open(util.p("/img/huge.pbm"), "wb") as f:
    f.write(b"P4\n100000 100000\n")
for name, frag in (("trunc", "truncated"), ("p1", "binary PBM"), ("huge", "unsupported size")):
    try:
        layout.read_pbm("/img/%s.pbm" % name)
        raise AssertionError(name + " should have been rejected")
    except ValueError as e:
        assert frag in str(e), (name, str(e))
# comments in the header are fine (GIMP / ImageMagick write them)
with open(util.p("/img/cm.pbm"), "wb") as f:
    f.write(b"P4\n# Created by something\n8 1\n\xaa")
assert layout.read_pbm("/img/cm.pbm") == (8, 1, b"\xaa")
print("read_pbm hardening ok")

# -- widgets through the layout engine ---------------------------------------------------------
page = {"items": [
    {"type": "art", "x": 4, "y": 4, "rows": ["#.#", ".#."], "scale": 4},
    {"type": "art", "x": 40, "y": 4, "data": "##|#.|##"},                      # '|' separated string
    {"type": "art", "x": 60, "y": 4, "rows": ["o.o", ".o."], "on": "o", "ink": "black"},
    {"type": "image", "src": "img/t.pbm", "x": 100, "y": 4, "scale": 2},
]}
cfg = config.parse(json.dumps({"pages": [page]}))
errs, warns = config.validate(cfg)
assert not errs and not warns, (errs, warns)
c = Canvas(0)
ctx = layout.render_page(c, cfg, 0, log=False)
assert not ctx.errors, ctx.errors
assert grid(c, 4, 4, 12, 8) == ["####....####"] * 4 + ["....####...."] * 4
assert grid(c, 40, 4, 2, 3) == ["##", "#.", "##"]
assert grid(c, 60, 4, 3, 2) == ["#.#", ".#."]

# invert page: art defaults to white ink
cfg = config.parse(json.dumps({"pages": [{"invert": True, "items": [{"type": "art", "x": 1, "y": 1, "rows": ["#"]}]}]}))
c = Canvas(0)
layout.render_page(c, cfg, 0, log=False)
assert c.get(1, 1) == WHITE and c.get(2, 2) == BLACK

# a broken art widget is isolated (marker drawn, others survive), validation says why
bad = {"pages": [{"items": [{"type": "art", "x": 0, "y": 0}, {"type": "text", "text": "ok", "x": 40, "y": 40, "font": "b16"}]}]}
cfg = config.parse(json.dumps(bad))
errs, _ = config.validate(cfg)
assert errs and "rows" in errs[0], errs
c = Canvas(0)
ctx = layout.render_page(c, cfg, 0, log=False)
assert len(ctx.errors) == 1 and "rows" in ctx.errors[0], ctx.errors

# validation catches mistakes and warns about off-screen art
for widget, frag in (({"type": "art", "rows": [1, 2]}, "list of strings"),
                     ({"type": "art", "rows": ["#"], "on": 5}, '"on"'),
                     ({"type": "art", "rows": ["#" * 400], "scale": 4}, "too big")):
    errs, _ = config.validate(config.parse(json.dumps({"pages": [{"items": [widget]}]})))
    assert errs and any(frag in e for e in errs), (widget, errs)
_, warns = config.validate(config.parse(json.dumps({"pages": [{"items": [
    {"type": "art", "x": 200, "y": 100, "rows": ["#" * 80] * 40}]}]})))
assert any("outside" in w for w in warns), warns
print("art/image widgets ok")
print("test_graphics: OK")
