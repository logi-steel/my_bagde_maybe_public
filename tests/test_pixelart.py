# cpython
"""tools/pixelart.py end to end through the firmware's own PBM reader and widget validator."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV = dict(os.environ, MICROPYPATH=os.pathsep.join([ROOT + "/firmware", ROOT + "/tests/mocks"]))
py = [sys.executable, "-I"]


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=ENV, **kw)
    if r.returncode:
        raise SystemExit("FAIL: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout


def expect(cond, msg):
    if not cond:
        raise SystemExit("FAIL: " + msg)
    print("ok:", msg)


# firmware side: read a PBM with badge.layout.read_pbm and print it as text
READER = (
    "import sys\nfrom badge import layout, util\nutil.ROOT = ''\n"
    "w, h, d = layout.read_pbm(sys.argv[1])\nbpr = (w + 7) // 8\n"
    "for y in range(h):\n"
    "    print(''.join('#' if d[y*bpr + (x >> 3)] & (0x80 >> (x & 7)) else '.' for x in range(w)))\n")

HEART = """; a heart, 9x8
.##...##.
####.####
#########
#########
.#######.
..#####..
...###...
....#....
"""

with tempfile.TemporaryDirectory() as d:
    reader = os.path.join(d, "read.py")
    open(reader, "w").write(READER)

    def fw_read(pbm):
        return run(["micropython", reader, pbm]).split()

    heart = os.path.join(d, "heart.txt")
    open(heart, "w").write(HEART)
    want = [l for l in HEART.split("\n") if l and not l.startswith(";")]

    # -- text -> PBM -> firmware ----------------------------------------------------------
    pbm = os.path.join(d, "heart.pbm")
    out = run(py + ["tools/pixelart.py", "to-pbm", heart, pbm])
    expect("9x8 px, " in out, "to-pbm reports the size (%s)" % out.strip())
    expect(fw_read(pbm) == want, "firmware reads the PBM back exactly as drawn")
    raw = open(pbm, "rb").read()
    expect(raw.startswith(b"P4\n9 8\n") and len(raw) == 7 + 2 * 8, "binary P4, 2 bytes per row (9 px)")

    # -- scale ------------------------------------------------------------------------------
    pbm3 = os.path.join(d, "heart3.pbm")
    run(py + ["tools/pixelart.py", "to-pbm", heart, pbm3, "--scale", "3"])
    got = fw_read(pbm3)
    expect(len(got) == 24 and len(got[0]) == 27 and got[0] == "".join(c * 3 for c in want[0]),
           "--scale 3 enlarges to 27x24")

    # -- PBM -> text round trip -----------------------------------------------------------------
    txt = os.path.join(d, "back.txt")
    run(py + ["tools/pixelart.py", "to-ascii", pbm, txt])
    expect(open(txt).read().split() == want, "to-ascii returns the original drawing")
    pbm2 = os.path.join(d, "again.pbm")
    run(py + ["tools/pixelart.py", "to-pbm", txt, pbm2])
    expect(open(pbm2, "rb").read() == raw, "text -> PBM -> text -> PBM is byte-identical")

    # -- widget JSON is valid and renders the same as the file -----------------------------------
    j = run(py + ["tools/pixelart.py", "to-json", heart, "--x", "7", "--y", "5", "--scale", "2"])
    widget = json.loads(j)
    expect(widget["type"] == "art" and widget["rows"] == want and widget["scale"] == 2 and widget["x"] == 7,
           "to-json emits an art widget")
    cfgp = os.path.join(d, "cfg.json")
    json.dump({"pages": [{"items": [widget]}]}, open(cfgp, "w"))
    chk = os.path.join(d, "chk.py")
    open(chk, "w").write(
        "import sys, json\nfrom badge import config, layout, util\nfrom badge.canvas import Canvas\n"
        "cfg = config.parse(open(sys.argv[1]).read())\nprint(config.validate(cfg))\n"
        "c = Canvas(0)\nctx = layout.render_page(c, cfg, 0, log=False)\nprint(ctx.errors)\n"
        "for y in range(5, 5 + 16):\n    print(''.join('#' if c.get(x, y) == 0 else '.' for x in range(7, 7 + 18)))\n")
    lines = run(["micropython", chk, cfgp]).splitlines()
    expect(lines[0] == "([], [])" and lines[1] == "[]", "the widget validates and renders without errors")
    expect(lines[2] == "".join(ch * 2 for ch in want[0]) and lines[3] == lines[2],
           "widget pixels equal the drawing scaled x2")
    p = run(py + ["tools/pixelart.py", "to-json", heart, "--pretty", "--ink", "white", "--on", "#o"])
    expect(json.loads(p)["ink"] == "white" and json.loads(p)["on"] == "#o", "--ink / --on are carried into the widget")

    # -- photo/PNG -> text for touching up -----------------------------------------------------------
    src = os.path.join(d, "face.png")
    im = Image.new("L", (60, 40), 255)
    dr = ImageDraw.Draw(im)
    dr.ellipse([5, 4, 55, 36], outline=0, width=3)
    dr.rectangle([20, 14, 26, 20], fill=0)
    dr.rectangle([34, 14, 40, 20], fill=0)
    im.save(src)
    face = os.path.join(d, "face.txt")
    out = run(py + ["tools/pixelart.py", "from-image", src, face, "--width", "30", "--threshold"])
    rows = open(face).read().split("\n")[:-1]
    expect(len(rows) == 20 and all(len(r) == 30 for r in rows) and "#" in "".join(rows) and "." in "".join(rows),
           "from-image -> 30x20 characters (%s)" % out.strip())
    prev = os.path.join(d, "prev.png")
    run(py + ["tools/pixelart.py", "preview", face, prev, "--scale", "4"])
    expect(Image.open(prev).size == (120, 80), "preview PNG is 4x the drawing")

    # -- foreign PBMs: ASCII (P1) is normalised to binary (P4) ---------------------------------------------
    p1 = os.path.join(d, "p1.pbm")
    open(p1, "w").write("P1\n# made by hand\n3 2\n1 0 1\n0 1 0\n")
    p4 = os.path.join(d, "p4.pbm")
    run(py + ["tools/pixelart.py", "normalize", p1, p4])
    expect(fw_read(p4) == ["#.#", ".#."], "normalize turns P1 into a P4 the firmware accepts")
    r = subprocess.run(["micropython", reader, p1], capture_output=True, text=True, cwd=ROOT, env=ENV)
    expect(r.returncode != 0 and "binary PBM" in r.stdout + r.stderr, "the firmware itself rejects P1 with a clear message")

    # -- bad input is refused politely ------------------------------------------------------------------------
    empty = os.path.join(d, "empty.txt")
    open(empty, "w").write("; nothing here\n\n")
    r = subprocess.run(py + ["tools/pixelart.py", "to-pbm", empty, os.path.join(d, "x.pbm")], capture_output=True, text=True, cwd=ROOT)
    expect(r.returncode != 0 and "empty" in r.stderr, "an empty drawing is an error, not an empty file")

    # -- ImageMagick (if present): its PBM output must have the polarity the firmware expects --------------------
    if shutil.which("convert"):
        sq = os.path.join(d, "sq.png")
        im = Image.new("L", (16, 8), 255)
        ImageDraw.Draw(im).rectangle([0, 0, 7, 3], fill=0)   # black block top-left
        im.save(sq)
        out = os.path.join(d, "im.pbm")
        subprocess.run(["convert", sq, "-threshold", "50%", "pbm:" + out], check=True)
        head = open(out, "rb").read(12)
        expect(head.startswith(b"P4"), "ImageMagick writes binary P4 (%r)" % head[:8])
        got = fw_read(out)
        expect(got[0].startswith("########") and got[0][8:] == "........" and got[7] == "." * 16,
               "ImageMagick black pixels become ink (bit = 1)")
    else:
        print("skip: ImageMagick not installed")
print("test_pixelart: OK")
