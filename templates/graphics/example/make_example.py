#!/usr/bin/env python3
"""Builds the worked example: "a cat" from template to badge.  Run from the repo root:

    python3 templates/graphics/example/make_example.py

  cat_design.png   what you would export from Canva (1000 x 488, made here by a script so the example is
                   reproducible - the cat is drawn procedurally, it is not a real photo)
  cat.pbm          the file the badge portal's Image tab would upload (made with tools/img2pbm.py)
  cat_on_badge.png what the badge shows (rendered by the real firmware renderer)
  flow.png         the three steps side by side (used in the README)
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_graphics_template as T  # noqa: E402

S = T.S
SW, SH = T.SIZES["landscape"]

# This layout is just ONE possible design (photo left, three text lines right). The template does not
# prescribe it - anything inside the red edge is fair game. Numbers are pixels of the 1000 x 488 canvas.
LAYOUT = {
    "photo": (24, 24, 416, 440),
    "title": (472, 32, 504, 136),
    "text": (472, 192, 504, 144),
    "small": (472, 368, 504, 96),
}


def zone(kind, name):
    return LAYOUT[name]


def draw_cat(w, h, seed=7):
    """A shaded, photo-like cat (greys + noise) so that dithering has something to show."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    # background: flat and light - a plain backdrop is what keeps a dithered photo readable
    img = np.zeros((h, w, 3)) + np.array([255.0, 255.0, 255.0])

    def blob(cx, cy, rx, ry, base, shade=70, tint=(1.0, 0.72, 0.42)):
        d = np.hypot((xx - cx) / rx, (yy - cy) / ry)
        m = np.clip(1.5 - d * 1.5, 0, 1)                  # soft-edged mask
        m = (d < 1).astype(float) * np.clip((1 - d) * 6, 0, 1)
        light = base - shade * np.clip(d, 0, 1) ** 1.6 + 25 * np.clip(1 - np.hypot((xx - cx + rx * .3) / rx, (yy - cy + ry * .35) / ry), 0, 1)
        col = np.stack([light * tint[0], light * tint[1], light * tint[2]], axis=-1)
        return col, m

    cx, cy = w * 0.5, h * 0.58
    for ex, flip in ((cx - w * 0.27, -1), (cx + w * 0.27, 1)):            # ears
        ear = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(ear)
        d.polygon([(ex - flip * w * 0.12, cy - h * 0.12), (ex + flip * w * 0.02, cy - h * 0.42),
                   (ex + flip * w * 0.14, cy - h * 0.10)], fill=255)
        m = np.asarray(ear.filter(ImageFilter.GaussianBlur(1.5)), float)[..., None] / 255
        img = img * (1 - m) + np.array([190, 135, 80]) * m
        inner = Image.new("L", (w, h), 0)
        ImageDraw.Draw(inner).polygon([(ex - flip * w * 0.06, cy - h * 0.14), (ex + flip * w * 0.02, cy - h * 0.33),
                                       (ex + flip * w * 0.09, cy - h * 0.13)], fill=255)
        mi = np.asarray(inner.filter(ImageFilter.GaussianBlur(1.5)), float)[..., None] / 255
        img = img * (1 - mi) + np.array([235, 170, 160]) * mi
    col, m = blob(cx, cy, w * 0.36, h * 0.30, 205, 95)                     # head
    img = img * (1 - m[..., None]) + col * m[..., None]
    # tabby stripes on the forehead
    st = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(st)
    for k in (-1, 0, 1):
        sd.line([(cx + k * w * 0.07, cy - h * 0.27), (cx + k * w * 0.05, cy - h * 0.12)], fill=255, width=max(3, w // 55))
    ms = np.asarray(st.filter(ImageFilter.GaussianBlur(2)), float)[..., None] / 255 * 0.55
    img = img * (1 - ms) + np.array([110, 70, 40]) * ms
    # muzzle
    col, m = blob(cx, cy + h * 0.09, w * 0.15, h * 0.10, 245, 40, (1.0, 0.95, 0.88))
    img = img * (1 - m[..., None] * .9) + col * m[..., None] * .9
    # eyes
    for ex in (cx - w * 0.15, cx + w * 0.15):
        col, m = blob(ex, cy - h * 0.03, w * 0.075, h * 0.055, 215, 130, (0.75, 1.0, 0.45))
        img = img * (1 - m[..., None]) + col * m[..., None]
        pup = Image.new("L", (w, h), 0)
        ImageDraw.Draw(pup).ellipse([ex - w * 0.018, cy - h * 0.065, ex + w * 0.018, cy + h * 0.005], fill=255)
        mp = np.asarray(pup.filter(ImageFilter.GaussianBlur(1)), float)[..., None] / 255
        img = img * (1 - mp) + np.array([15, 15, 15]) * mp
        hl = Image.new("L", (w, h), 0)
        ImageDraw.Draw(hl).ellipse([ex + w * 0.012, cy - h * 0.06, ex + w * 0.03, cy - h * 0.04], fill=255)
        mh = np.asarray(hl.filter(ImageFilter.GaussianBlur(1)), float)[..., None] / 255
        img = img * (1 - mh) + 255 * mh
    # nose, mouth, whiskers
    det = Image.new("L", (w, h), 0)
    dd = ImageDraw.Draw(det)
    dd.polygon([(cx - w * 0.03, cy + h * 0.045), (cx + w * 0.03, cy + h * 0.045), (cx, cy + h * 0.08)], fill=255)
    dd.line([(cx, cy + h * 0.08), (cx, cy + h * 0.11), (cx - w * 0.05, cy + h * 0.135)], fill=255, width=max(2, w // 120))
    dd.line([(cx, cy + h * 0.11), (cx + w * 0.05, cy + h * 0.135)], fill=255, width=max(2, w // 120))
    for sx in (-1, 1):
        for dy, tilt in ((-0.01, -0.035), (0.03, 0.0), (0.065, 0.04)):
            dd.line([(cx + sx * w * 0.10, cy + h * (0.075 + dy)), (cx + sx * w * 0.42, cy + h * (0.075 + dy + tilt * 2))],
                    fill=255, width=max(2, w // 200))
    md = np.asarray(det.filter(ImageFilter.GaussianBlur(0.8)), float)[..., None] / 255
    img = img * (1 - md * .85) + np.array([60, 40, 40]) * md * .85
    # sticker-style dark outline around everything that is not background (helps a lot after dithering)
    bgmask = (np.abs(img - np.array([255.0, 255.0, 255.0])).sum(axis=-1) > 24).astype("uint8") * 255
    fg = Image.fromarray(bgmask).filter(ImageFilter.MaxFilter(3))
    edge = np.asarray(fg.filter(ImageFilter.MaxFilter(9)), float) - np.asarray(fg, float)
    me = np.clip(edge / 255, 0, 1)[..., None]
    img = img * (1 - me) + np.array([35.0, 25.0, 20.0]) * me
    # fur noise (kept soft so the PNG stays small)
    noise = rng.normal(0, 7, (h, w))
    noise = np.asarray(Image.fromarray(np.clip(noise + 128, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(1.2)), float) - 128
    fgm = (np.asarray(fg, float) / 255)[..., None]          # fur noise only on the cat, the backdrop stays pure white
    img = np.clip(img + noise[..., None] * 1.0 * fgm, 0, 255)
    img = 255 * (img / 255) ** 1.35            # a little more contrast: midtones darker
    return Image.fromarray(np.clip(img, 0, 255).astype("uint8"), "RGB")


def make_design(path):
    from PIL import ImageFont
    im = Image.new("RGB", (SW * S, SH * S), (255, 255, 255))
    px, py, pw, ph = zone("photo", "photo")
    im.paste(draw_cat(pw, ph), (px, py))
    d = ImageDraw.Draw(im)
    black = (0, 0, 0)

    def fit(text, w, h, size):
        while size > 10:
            f = T._font(size)
            bb = d.textbbox((0, 0), text, font=f)
            if bb[2] - bb[0] <= w and bb[3] - bb[1] <= h:
                return f, bb
            size -= 2
        return T._font(10), (0, 0, 0, 0)

    x, y, w, h = zone("text", "title")
    f, bb = fit("Mruczek", w - 16, h - 12, 120)
    d.text((x + 8 - bb[0], y + (h - (bb[3] - bb[1])) // 2 - bb[1]), "Mruczek", font=f, fill=black)
    x, y, w, h = zone("text", "text")
    f, _ = fit("Professional", w - 16, (h - 12) // 2, 64)
    d.text((x + 8, y + 4), "Professional", font=f, fill=black)
    d.text((x + 8, y + 4 + f.size + 6), "napper", font=f, fill=black)
    x, y, w, h = zone("text", "small")
    f, bb = fit("@mruczek.cat", w - 16, h - 12, 56)
    d.text((x + 8 - bb[0], y + (h - (bb[3] - bb[1])) // 2 - bb[1]), "@mruczek.cat", font=f, fill=black)
    im.save(path, optimize=True)


def main():
    design = os.path.join(HERE, "cat_design.png")
    pbm = os.path.join(HERE, "cat.pbm")
    make_design(design)
    subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "img2pbm.py"), design, pbm, "--width", "250"], check=True)
    # what the badge shows: real firmware renderer on a scratch copy of firmware/ that holds the image
    with tempfile.TemporaryDirectory() as d:
        fw = os.path.join(d, "fw")
        subprocess.run(["cp", "-r", os.path.join(ROOT, "firmware"), fw], check=True)
        os.makedirs(os.path.join(fw, "img"), exist_ok=True)
        subprocess.run(["cp", pbm, os.path.join(fw, "img", "cat.pbm")], check=True)
        cfg = os.path.join(d, "cfg.json")
        open(cfg, "w").write('{"pages":[{"items":[{"type":"image","src":"img/cat.pbm","x":0,"y":0}]}]}')
        out = os.path.join(d, "out")
        os.makedirs(out)
        subprocess.run(["micropython", os.path.join(ROOT, "tools", "render_pages.py"), fw, cfg, out], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "pbm2png.py"), os.path.join(out, "page0.pbm"),
                        os.path.join(HERE, "cat_on_badge.png"), "4", "--bezel"], check=True)
    flow()
    print("example built")


def flow():
    from PIL import ImageFont
    tmpl = Image.open(os.path.join(ROOT, "templates", "graphics", "badge_template.png")).convert("RGB")
    design = Image.open(os.path.join(HERE, "cat_design.png")).convert("RGB")
    badge = Image.open(os.path.join(HERE, "cat_on_badge.png")).convert("RGB")
    tw = 520
    th = round(tmpl.height * tw / tmpl.width)
    panes = [("1. Pick a template", tmpl.resize((tw, th), Image.LANCZOS)),
             ("2. Design anything on top of it", design.resize((tw, th), Image.LANCZOS)),
             ("3. This is what the badge shows", badge.resize((tw, th), Image.LANCZOS))]
    pad = 26
    sheet = Image.new("RGB", (3 * tw + 4 * pad, th + 90), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (title, im) in enumerate(panes):
        x = pad + i * (tw + pad)
        d.text((x, 14), title, fill=(30, 30, 30), font=T._font(22))
        sheet.paste(im, (x, 54))
        d.rectangle([x - 1, 53, x + tw, 54 + th], outline=(100, 100, 100))
        if i < 2:
            ax = x + tw + 3
            d.polygon([(ax, 54 + th // 2 - 14), (ax + pad - 6, 54 + th // 2), (ax, 54 + th // 2 + 14)], fill=(60, 60, 60))
    sheet.save(os.path.join(HERE, "flow.png"), optimize=True)


if __name__ == "__main__":
    main()
