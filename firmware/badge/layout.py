"""Turn the JSON `pages` into pixels.

Every widget is drawn inside its own try/except: one broken widget (or plugin) shows a
small error marker instead of killing the whole badge.
"""
import sys
import math
from .canvas import BLACK, WHITE, Font
from . import util


class Font8:
    """Fallback / built-in 8x8 font, integer scaled (font name "8x8")."""

    def __init__(self, scale=1):
        self.h = 8 * scale
        self.scale = scale
        self.asc = self.h

    def adv(self, ch):
        return 8 * self.scale

    def width(self, s):
        return 8 * self.scale * len(s)

    def draw(self, canvas, s, x, y, ink=BLACK):
        canvas.text8(s, x, y, ink, self.scale)
        return x + self.width(s)


def fmt(s, vars):
    """Replace {name} with vars[name]; unknown names stay as they are."""
    out = ""
    i = 0
    while True:
        a = s.find("{", i)
        if a < 0:
            return out + s[i:]
        b = s.find("}", a)
        if b < 0:
            return out + s[i:]
        key = s[a + 1:b]
        out += s[i:a]
        out += str(vars[key]) if key in vars else s[a:b + 1]
        i = b + 1


def wrap(text, font, width, max_lines=None):
    """Greedy word wrap (explicit \\n respected, over-long words are split)."""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = word if not cur else cur + " " + word
            if font.width(cand) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            while font.width(word) > width and len(word) > 1:  # hard split
                k = len(word)
                while k > 1 and font.width(word[:k]) > width:
                    k -= 1
                lines.append(word[:k])
                word = word[k:]
            cur = word
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and font.width(last + "…") > width:
            last = last[:-1]
        lines[-1] = last + "…"
    return lines


def read_pbm(path):
    """Parse a binary PBM (P4). Returns (w, h, data) with 1 = ink."""
    with open(util.p(path), "rb") as f:
        d = f.read()
    if d[:2] != b"P4":
        raise ValueError("%s is not a binary PBM (P4)" % path)
    pos = 2
    nums = []
    while len(nums) < 2:
        while d[pos] in b" \t\r\n":
            pos += 1
        if d[pos] == 35:  # '#' comment
            while d[pos] != 10:
                pos += 1
            continue
        start = pos
        while d[pos] not in b" \t\r\n":
            pos += 1
        nums.append(int(d[start:pos]))
    pos += 1
    w, h = nums
    return w, h, d[pos:pos + ((w + 7) >> 3) * h]


class Ctx:
    """What widgets and plugins get to see."""

    def __init__(self, cfg, canvas, page_index=0, battery=None, reload_plugins=False):
        self.cfg = cfg
        self.canvas = canvas
        self.page_index = page_index
        self.reload_plugins = reload_plugins
        self.errors = []
        self.default_ink = BLACK
        self._fonts = {}
        v = dict(cfg.get("vars", {}))
        v["page"] = page_index + 1
        v["pages"] = len(cfg.get("pages", []))
        if battery is not None:
            v["battery"] = battery
        else:
            v.setdefault("battery", "?")
        self.vars = v

    def fmt(self, s):
        return fmt(str(s), self.vars)

    def font(self, name):
        name = name or "s16"
        f = self._fonts.get(name)
        if f is None:
            if name.startswith("8x8"):
                scale = 1
                if "x" in name[3:]:
                    scale = int(name.split("x")[-1])
                f = Font8(scale)
            else:
                try:
                    f = Font(util.p("/fonts/%s.fnt" % name))
                except OSError:
                    self.errors.append("font %s missing" % name)
                    f = Font8(2)
            self._fonts[name] = f
        return f

    def ink(self, item):
        v = item.get("ink")
        if v == "white":
            return WHITE
        if v == "black":
            return BLACK
        return self.default_ink

    def error(self, msg):
        self.errors.append(msg)


def _num(item, key, default=0):
    v = item.get(key, default)
    return int(v) if isinstance(v, (int, float)) else default


# -- widgets ---------------------------------------------------------------
def w_text(c, it, ctx):
    txt = ctx.fmt(it.get("text", ""))
    font = ctx.font(it.get("font"))
    ink = ctx.ink(it)
    x, y = _num(it, "x"), _num(it, "y")
    align = it.get("align", "left")
    box = it.get("w")
    if box is None and align != "left":
        box = c.w - x  # centre / right-align across the rest of the screen
    box = int(box) if box is not None else None
    if box and it.get("wrap", True):
        lines = wrap(txt, font, box, it.get("lines"))
    else:
        lines = txt.split("\n")
        if it.get("lines"):
            lines = lines[:int(it["lines"])]
    gap = _num(it, "gap", 0)
    for ln in lines:
        dx = 0
        if box:
            lw = font.width(ln)
            if align == "center":
                dx = (box - lw) // 2
            elif align == "right":
                dx = box - lw
        font.draw(c, ln, x + dx, y, ink)
        y += font.h + gap


def _corner_points(r):
    """Quarter-circle offsets (dx, dy) from the corner centre, midpoint algorithm (no gaps)."""
    pts = []
    x, y, e = r, 0, 1 - r
    while x >= y:
        pts.append((x, y))
        if x != y:
            pts.append((y, x))
        y += 1
        if e < 0:
            e += 2 * y + 1
        else:
            x -= 1
            e += 2 * (y - x) + 1
    return pts


def _rrect(c, x, y, w, h, r, ink, fill):
    r = max(0, min(r, w // 2, h // 2))
    if r == 0:
        c.rect(x, y, w, h, ink, fill)
        return
    if fill:
        for i in range(r):
            dy = r - 1 - i
            dx = r - int(math.sqrt(r * r - dy * dy) + 0.5)
            c.hline(x + dx, y + i, w - 2 * dx, ink)
            c.hline(x + dx, y + h - 1 - i, w - 2 * dx, ink)
        c.rect(x, y + r, w, h - 2 * r, ink, True)
        return
    c.hline(x + r, y, w - 2 * r, ink)
    c.hline(x + r, y + h - 1, w - 2 * r, ink)
    c.vline(x, y + r, h - 2 * r, ink)
    c.vline(x + w - 1, y + r, h - 2 * r, ink)
    for dx, dy in _corner_points(r):
        c.pixel(x + r - dx, y + r - dy, ink)
        c.pixel(x + w - 1 - r + dx, y + r - dy, ink)
        c.pixel(x + r - dx, y + h - 1 - r + dy, ink)
        c.pixel(x + w - 1 - r + dx, y + h - 1 - r + dy, ink)


def w_rect(c, it, ctx):
    _rrect(c, _num(it, "x"), _num(it, "y"), _num(it, "w", 10), _num(it, "h", 10),
           _num(it, "r"), ctx.ink(it), bool(it.get("fill")))


def w_line(c, it, ctx):
    ink = ctx.ink(it)
    t = max(1, _num(it, "thickness", 1))
    x1, y1, x2, y2 = _num(it, "x1"), _num(it, "y1"), _num(it, "x2"), _num(it, "y2")
    for k in range(t):
        if abs(x2 - x1) >= abs(y2 - y1):
            c.line(x1, y1 + k, x2, y2 + k, ink)
        else:
            c.line(x1 + k, y1, x2 + k, y2, ink)


def w_circle(c, it, ctx):
    r = _num(it, "r", 5)
    c.ellipse(_num(it, "x") + r, _num(it, "y") + r, r, r, ctx.ink(it), bool(it.get("fill")))


def w_image(c, it, ctx):
    w, h, data = read_pbm("/" + str(it["src"]).lstrip("/"))
    ink = ctx.ink(it)
    if it.get("invert"):
        ink = 1 - ink
    c.bits(_num(it, "x"), _num(it, "y"), w, h, data, ink)


def w_qr(c, it, ctx):
    from . import qr
    text = ctx.fmt(it["data"])
    ecc = it.get("ecc", "M")
    border = _num(it, "border", 2)
    n, m = qr.encode(text, ecc)
    scale = _num(it, "scale", 0)
    if scale <= 0:
        size = _num(it, "size", 100)
        scale = max(1, size // (n + 2 * border))
    qr.draw_modules(c, n, m, _num(it, "x"), _num(it, "y"), scale, border, ctx.ink(it))


def w_chips(c, it, ctx):
    font = ctx.font(it.get("font", "s12"))
    ink = ctx.ink(it)
    padx, pady = _num(it, "padx", 5), _num(it, "pady", 2)
    gap = _num(it, "gap", 4)
    r = _num(it, "r", 4)
    x0, y = _num(it, "x"), _num(it, "y")
    right = x0 + (_num(it, "w") if it.get("w") else c.w - x0)
    x = x0
    ch = font.h + 2 * pady
    fill = bool(it.get("fill"))
    for label in it.get("items", []):
        label = ctx.fmt(label)
        cw = font.width(label) + 2 * padx
        if x + cw > right and x > x0:
            x = x0
            y += ch + gap
        _rrect(c, x, y, cw, ch, r, ink, fill)
        font.draw(c, label, x + padx, y + pady, (1 - ink) if fill else ink)
        x += cw + gap


def w_battery(c, it, ctx):
    pct = ctx.vars.get("battery")
    x, y = _num(it, "x"), _num(it, "y")
    ink = ctx.ink(it)
    if not isinstance(pct, int):
        return
    c.rect(x, y, 22, 11, ink)
    c.rect(x + 22, y + 3, 2, 5, ink, True)
    fillw = max(0, min(18, pct * 18 // 100))
    if fillw:
        c.rect(x + 2, y + 2, fillw, 7, ink, True)
    if it.get("text", True):
        f = ctx.font(it.get("font", "s12"))
        f.draw(c, "%d%%" % pct, x + 28, y + 5 - f.h // 2, ink)


def w_plugin(c, it, ctx):
    name = it.get("name", "")
    mod_name = "plugins." + name
    if ctx.reload_plugins and mod_name in sys.modules:
        del sys.modules[mod_name]
    __import__(mod_name)
    sys.modules[mod_name].draw(c, it, ctx)


_WIDGETS = {
    "text": w_text, "rect": w_rect, "line": w_line, "circle": w_circle, "image": w_image,
    "qr": w_qr, "chips": w_chips, "battery": w_battery, "plugin": w_plugin,
}


def _log(msg):
    try:
        path = "/error.log"
        size = 0
        try:
            import os
            size = os.stat(util.p(path))[6]
        except OSError:
            pass
        with open(util.p(path), "a" if size < 4096 else "w") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def render_page(canvas, cfg, index, battery=None, reload_plugins=False, log=True):
    """Draw page `index` of cfg onto canvas. Returns the Ctx (ctx.errors lists problems)."""
    pages = cfg.get("pages", [])
    ctx = Ctx(cfg, canvas, index, battery, reload_plugins)
    if not pages:
        canvas.clear(WHITE)
        canvas.text8("no pages", 4, 4)
        return ctx
    page = pages[index % len(pages)]
    if page.get("invert"):
        canvas.clear(BLACK)
        ctx.default_ink = WHITE
    else:
        canvas.clear(WHITE)
    for n, it in enumerate(page.get("items", [])):
        fn = _WIDGETS.get(it.get("type"))
        if fn is None:
            continue
        try:
            fn(canvas, it, ctx)
        except Exception as e:  # keep going, mark the spot
            msg = "page %d item %d (%s): %s: %s" % (index, n, it.get("type"), type(e).__name__, e)
            ctx.errors.append(msg)
            if log:
                _log(msg)
            x, y = _num(it, "x"), _num(it, "y")
            canvas.rect(x, y, 14, 12, BLACK, True)
            canvas.text8("!", x + 3, y + 2, WHITE)
    return ctx
