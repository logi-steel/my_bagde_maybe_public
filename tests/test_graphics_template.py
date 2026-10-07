# cpython
"""The "make your own graphics" template: right sizes, only the red edge is drawn, and an overlay you forget in the
export does not turn into black ink on the badge. Also checks the finished example.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV = dict(os.environ, MICROPYPATH=os.pathsep.join([ROOT + "/firmware", ROOT + "/tests/mocks"]))
T = os.path.join(ROOT, "templates", "graphics")
EX = os.path.join(T, "example")
EDGE = 24          # 6 badge pixels, x4
OUTLINE = 3        # the thin line just inside the red band
py = [sys.executable, "-I"]


def expect(cond, msg):
    if not cond:
        raise SystemExit("FAIL: " + msg)
    print("ok:", msg)


def ink(im, threshold=128):
    """Black pixels after a plain threshold on a white background (what the portal does with dither off)."""
    g = Image.new("RGBA", im.size, (255, 255, 255, 255))
    g.alpha_composite(im.convert("RGBA"))
    return sum(1 for v in g.convert("L").tobytes() if v < threshold)


for suffix, (w, h) in (("", (1000, 488)), ("_portrait", (488, 1000))):
    full = Image.open(os.path.join(T, "badge_template%s.png" % suffix))
    ov = Image.open(os.path.join(T, "badge_template%s_overlay.png" % suffix))
    one = Image.open(os.path.join(T, "badge_template%s_1x.png" % suffix))
    name = suffix.strip("_") or "landscape"
    expect(full.size == (w, h), "%s: labelled template is %dx%d" % (name, w, h))
    expect(ov.size == (w, h) and ov.mode == "RGBA", "%s: overlay is %dx%d with an alpha channel" % (name, w, h))
    expect(one.size == (w // 4, h // 4), "%s: 1x template is %dx%d (the real screen)" % (name, w // 4, h // 4))

    a = ov.getchannel("A")
    inner = a.crop((EDGE + OUTLINE, EDGE + OUTLINE, w - EDGE - OUTLINE, h - EDGE - OUTLINE))
    expect(inner.getextrema() == (0, 0), "%s: the whole inside of the overlay is transparent" % name)
    band = [a.crop((0, 0, w, EDGE)), a.crop((0, h - EDGE, w, h)), a.crop((0, 0, EDGE, h)), a.crop((w - EDGE, 0, w, h))]
    expect(all(b.getextrema()[0] > 0 for b in band), "%s: the red edge is drawn all the way round" % name)
    expect(ink(ov) == 0, "%s: an overlay forgotten in the export vanishes with dither OFF (hard threshold)" % name)
    expect(ink(one) == 0, "%s: the 1x template vanishes with dither OFF too" % name)

# the labelled picture really is labelled, the overlay is not
lab = Image.open(os.path.join(T, "badge_template.png")).convert("RGB")
mid = (EDGE + OUTLINE, EDGE + OUTLINE, 1000 - EDGE - OUTLINE, 488 - EDGE - OUTLINE)
expect(lab.crop(mid).getextrema() == ((255, 255), (255, 255), (255, 255)), "the labelled picture is plain white inside the edge")

# the generator reproduces the committed files byte for byte (so nobody edits a PNG by hand and forgets the script)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_graphics_template as G  # noqa: E402
for orientation in G.SIZES:
    suffix = "" if orientation == "landscape" else "_portrait"
    for scale, labels, overlay, fname in ((4, True, False, "badge_template%s.png"), (4, False, True, "badge_template%s_overlay.png"),
                                          (1, False, False, "badge_template%s_1x.png")):
        fresh = G.draw_template(orientation, scale, labels, overlay)
        old = Image.open(os.path.join(T, fname % suffix))
        same = fresh.convert("RGBA").tobytes() == old.convert("RGBA").tobytes()
        expect(same, "%s is what tools/make_graphics_template.py makes" % (fname % suffix))

# -- the worked example --
design = Image.open(os.path.join(EX, "cat_design.png"))
expect(design.size == (1000, 488), "cat_design.png is 1000x488")
with tempfile.TemporaryDirectory() as d:
    out = os.path.join(d, "cat.pbm")
    subprocess.run(py + [os.path.join(ROOT, "tools", "img2pbm.py"), os.path.join(EX, "cat_design.png"), out, "--width", "250"],
                   check=True, cwd=ROOT, capture_output=True)
    expect(open(out, "rb").read() == open(os.path.join(EX, "cat.pbm"), "rb").read(), "cat.pbm is what the portal / img2pbm produce")
r = subprocess.run(["micropython", "-c",
                    "from badge.layout import read_pbm\n"
                    "w, h, d = read_pbm('%s/cat.pbm')\nprint(w, h, len(d))" % EX], cwd=ROOT, env=ENV, capture_output=True, text=True)
expect(r.stdout.split() == ["250", "122", str(32 * 122)], "the firmware reads cat.pbm as 250x122 (%s%s)" % (r.stdout.strip(), r.stderr.strip()))
for f in ("cat_on_badge.png", "flow.png"):
    expect(os.path.getsize(os.path.join(EX, f)) > 1000, "%s exists" % f)
print("ALL OK")
