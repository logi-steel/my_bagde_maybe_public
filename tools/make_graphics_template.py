#!/usr/bin/env python3
"""Make the badge graphic template (templates/graphics/badge_template*.png).

  python3 tools/make_graphics_template.py

The template shows only what physically limits a design - nothing else:
  * the size of the screen (250 x 122, or 122 x 250 when the badge is set to portrait)
  * the RED EDGE: the outer 6 px (24 px on the x4 canvas), about 1.2 mm. A safety margin: the case window is only
    0.4 mm larger than the screen per side and its exact position is not verified, so up to ~1 mm (= about 5 px)
    of the edge may end up covered. Do not put anything important there.

Files (landscape; add "_portrait" for the 488 x 1000 version):
  badge_template.png          1000 x 488, opaque, labelled      -> look at it
  badge_template_overlay.png  1000 x 488, TRANSPARENT, no text -> lay it over your design in Canva & co, delete before export
  badge_template_1x.png       250 x 122, opaque, no label       -> for pixel-exact editors

1000 x 488 is the screen times 4: comfortable to work on, and the badge portal shrinks it back.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "templates", "graphics")

S, SAFE = 4, 6
SIZES = {"landscape": (250, 122), "portrait": (122, 250)}
KEEP_FILL = (230, 60, 60)
EDGE = (232, 105, 105)    # outline: light enough (luminance 143) to turn WHITE under a threshold of 128,
                          # so an overlay you forgot to delete does not leave a black frame on the badge
LABEL = (150, 20, 20)     # text of the labelled reference picture (never meant to be exported)

_FONT_PATHS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
               "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf")


def _font(size):
    for p in _FONT_PATHS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def draw_template(orientation="landscape", scale=S, labels=True, overlay=False):
    sw, sh = SIZES[orientation]
    w, h = sw * scale, sh * scale
    s = SAFE * scale
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    alpha = 85 if scale > 1 else 120
    for box in ([0, 0, w, s], [0, h - s, w, h], [0, s, s, h - s], [w - s, s, w, h - s]):
        d.rectangle(box, fill=KEEP_FILL + (alpha,))
    d.rectangle([s, s, w - s - 1, h - s - 1], outline=EDGE + (255,), width=max(1, scale // 2 + 1) if scale > 1 else 1)
    if labels and scale > 1:
        stroke = dict(stroke_width=2, stroke_fill=(255, 255, 255, 255))
        f = _font(14)
        top = "KEEP IMPORTANT THINGS OUT OF THE RED EDGE - the case can hide it"
        while d.textlength(top, font=f) > w - 2 * s and f.size > 9:
            top = "KEEP IMPORTANT THINGS OUT OF THE RED EDGE" if "case" in top else "KEEP OUT OF THE RED EDGE"
            f = _font(max(9, f.size - 1)) if d.textlength(top, font=f) > w - 2 * s else f
        d.text((s + 8, 2), top, fill=LABEL + (255,), font=f, **stroke)
        bottom = "canvas %d x %d px  (badge screen %d x %d, times 4)" % (w, h, sw, sh)
        fb = _font(14)
        while d.textlength(bottom, font=fb) > w - 2 * s and fb.size > 9:
            fb = _font(fb.size - 1)
        d.text((s + 8, h - s + 4), bottom, fill=LABEL + (255,), font=fb, **stroke)
    if overlay:
        return layer
    base = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    base.alpha_composite(layer)
    return base.convert("RGB")


def main():
    os.makedirs(OUT, exist_ok=True)
    for orientation in SIZES:
        suffix = "" if orientation == "landscape" else "_portrait"
        draw_template(orientation, S, True).save(os.path.join(OUT, "badge_template%s.png" % suffix), optimize=True)
        draw_template(orientation, S, False, overlay=True).save(os.path.join(OUT, "badge_template%s_overlay.png" % suffix), optimize=True)
        draw_template(orientation, 1, False).save(os.path.join(OUT, "badge_template%s_1x.png" % suffix), optimize=True)
        print("built", orientation)


if __name__ == "__main__":
    sys.exit(main())
