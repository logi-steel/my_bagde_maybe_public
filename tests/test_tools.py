# cpython
"""Host tools: img2pbm -> firmware PBM reader, make_font -> firmware Font, deploy command, preview."""
import os
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


with tempfile.TemporaryDirectory() as d:
    # -- img2pbm: hard threshold must equal PIL's own threshold, read back by the firmware reader --
    src = os.path.join(d, "t.png")
    im = Image.new("L", (37, 21), 255)           # 37 wide: not a multiple of 8 on purpose
    dr = ImageDraw.Draw(im)
    dr.rectangle([2, 3, 20, 10], fill=0)
    dr.ellipse([22, 2, 34, 18], fill=60)
    dr.line([0, 20, 36, 0], fill=0)
    im.save(src)
    pbm = os.path.join(d, "t.pbm")
    run(py + ["tools/img2pbm.py", src, pbm, "--width", "37", "--threshold"])
    reader = os.path.join(d, "read.py")
    open(reader, "w").write(
        "import sys\nfrom badge import layout, util\nutil.ROOT = ''\n"
        "w, h, data = layout.read_pbm(sys.argv[1])\n"
        "print(w, h)\n"
        "bpr = (w + 7) // 8\n"
        "for y in range(h):\n"
        "    print(''.join('#' if data[y * bpr + (x >> 3)] & (0x80 >> (x & 7)) else '.' for x in range(w)))\n")
    out = run(["micropython", reader, pbm]).splitlines()
    expect(out[0] == "37 21", "firmware reads the PBM header (%s)" % out[0])
    ref = im.point(lambda v: 255 if v >= 128 else 0)
    bad = 0
    for y in range(21):
        for x in range(37):
            if (out[1 + y][x] == "#") != (ref.getpixel((x, y)) == 0):
                bad += 1
    expect(bad == 0, "img2pbm output is pixel-identical to the PIL threshold (%d diffs)" % bad)

    # -- make_font: a font built from a TTF is loadable and measures like PIL ----------------------
    fnt = os.path.join(d, "t.fnt")
    run(py + ["tools/make_font.py", "--ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "--size", "20", "--out", fnt])
    probe = os.path.join(d, "probe.py")
    open(probe, "w").write(
        "import sys\nfrom badge.canvas import Font\nf = Font(sys.argv[1])\n"
        "print(f.h, f.width('Hello'), f.width('Łódź'), f.adv('?'), f.glyph('€') is not None)\n")
    h, w_hello, w_pl, adv_q, euro = run(["micropython", probe, fnt]).split()
    from PIL import ImageFont
    pf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    asc, desc = pf.getmetrics()
    expect(int(h) == asc + desc, "font height matches the TTF metrics (%s)" % h)
    expect(int(w_hello) == sum(int(round(pf.getlength(c))) for c in "Hello"), "advance widths match (%s px)" % w_hello)
    expect(int(w_pl) > 0 and euro == "True", "Polish letters and the euro sign are present")

    # -- the shipped fonts all load and cover Polish -------------------------------------------------
    allf = os.path.join(d, "all.py")
    open(allf, "w").write(
        "import os\nfrom badge.canvas import Font\n"
        "for n in sorted(os.listdir('firmware/fonts')):\n"
        "    if not n.endswith('.fnt'): continue\n"
        "    f = Font('firmware/fonts/' + n)\n"
        "    missing = [c for c in 'ąćęłńóśźżĄĆĘŁŃÓŚŹŻ' if f._find(ord(c)) < 0]\n"
        "    print(n, f.h, f.n, 'MISSING ' + ''.join(missing) if missing else 'pl-ok')\n")
    out = run(["micropython", allf])
    expect(out.count("pl-ok") == 7, "all 7 shipped fonts contain the Polish letters")

    # -- deploy builds a sane mpremote command ---------------------------------------------------------
    full = run(py + ["tools/deploy.py", "--dry-run", "--port", "/dev/ttyACM0", "--reset"])
    code = run(py + ["tools/deploy.py", "--dry-run", "--code-only"])
    expect("fs cp -r " + ROOT + "/firmware/badge :" in full and "fs cp " + ROOT + "/firmware/main.py :main.py" in full,
           "deploy copies badge/ recursively and main.py explicitly")
    expect("config.json" in full and "config.json" not in code and "/plugins" not in code,
           "--code-only keeps config.json and plugins/")
    expect(full.strip().endswith("+ reset"), "--reset appends a reset")

    # -- preview tool ---------------------------------------------------------------------------------------------
    outpng = os.path.join(d, "p.png")
    run(py + ["tools/preview.py", "firmware/config.json", outpng, "--scale", "2"])
    img = Image.open(outpng)
    expect(img.width > 500 and img.height > 250, "preview PNG written (%dx%d)" % img.size)
    portrait = os.path.join(d, "p90.png")
    run(py + ["tools/preview.py", "firmware/config.json", portrait, "--scale", "2", "--rotation", "90", "--cols", "4"])
    expect(Image.open(portrait).height > Image.open(portrait).width // 4, "portrait preview renders too")
print("test_tools: OK")
