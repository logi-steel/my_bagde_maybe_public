"""Logical drawing surface + conversion to the panel's native RAM layout.

Colors: BLACK = 0, WHITE = 1 (same as the panel RAM: 1 = white).

rotation 0/180 -> 250x122 landscape, 90/270 -> 122x250 portrait.
Landscape uses a MONO_VLSB framebuffer of 250x128 (so one byte = 8 vertical
pixels = 8 native source columns), portrait uses MONO_HLSB of 128x250 (bit 7 = leftmost pixel) which is
already the native layout. 128 > 122 leaves 6 padding lines that never show.
"""
import framebuf
import struct

BLACK = 0
WHITE = 1

_REV = None


def _rev_table():
    global _REV
    if _REV is None:
        t = bytearray(256)
        for i in range(256):
            r = 0
            for bit in range(8):
                if i & (1 << bit):
                    r |= 0x80 >> bit
            t[i] = r
        _REV = bytes(t)
    return _REV


class Canvas:
    def __init__(self, rotation=0):
        self.rotation = rotation % 360
        self.buf = bytearray(4000)
        if self.rotation in (0, 180):
            self.w, self.h = 250, 122
            self.fb = framebuf.FrameBuffer(self.buf, 250, 128, framebuf.MONO_VLSB)
            self.ox, self.oy = 0, (6 if self.rotation == 180 else 0)
        else:
            self.w, self.h = 122, 250
            self.fb = framebuf.FrameBuffer(self.buf, 128, 250, framebuf.MONO_HLSB)
            self.ox, self.oy = (6 if self.rotation == 270 else 0), 0
        self.fb.fill(WHITE)

    # -- primitives (logical coordinates) --------------------------------
    def clear(self, color=WHITE):
        self.fb.fill(color)

    def pixel(self, x, y, c=BLACK):
        self.fb.pixel(x + self.ox, y + self.oy, c)

    def hline(self, x, y, w, c=BLACK):
        self.fb.hline(x + self.ox, y + self.oy, w, c)

    def vline(self, x, y, h, c=BLACK):
        self.fb.vline(x + self.ox, y + self.oy, h, c)

    def line(self, x1, y1, x2, y2, c=BLACK):
        self.fb.line(x1 + self.ox, y1 + self.oy, x2 + self.ox, y2 + self.oy, c)

    def rect(self, x, y, w, h, c=BLACK, fill=False):
        if fill:
            self.fb.fill_rect(x + self.ox, y + self.oy, w, h, c)
        else:
            self.fb.rect(x + self.ox, y + self.oy, w, h, c)

    def ellipse(self, x, y, rx, ry, c=BLACK, fill=False):
        self.fb.ellipse(x + self.ox, y + self.oy, rx, ry, c, fill)

    def text8(self, s, x, y, c=BLACK, scale=1):
        """Built-in 8x8 font, integer scaled. Fallback when no .fnt is available."""
        if scale == 1:
            self.fb.text(s, x + self.ox, y + self.oy, c)
            return
        tmp = bytearray(8)
        g = framebuf.FrameBuffer(tmp, 8, 8, framebuf.MONO_HLSB)
        key = 1 if c == BLACK else 0
        for i, ch in enumerate(s):
            g.fill(key)
            g.text(ch, 0, 0, 1 - key)
            for gy in range(8):
                for gx in range(8):
                    if g.pixel(gx, gy) != key:
                        self.fb.fill_rect(x + self.ox + (i * 8 + gx) * scale,
                                          y + self.oy + gy * scale, scale, scale, c)

    def bits(self, x, y, w, h, data, ink=BLACK, scale=1):
        """Draw a packed 1-bit bitmap (MSB first, ink = bit set, rows padded to bytes).

        scale > 1 enlarges it by whole pixels (nearest neighbour, crisp on e-paper).
        """
        if scale > 1:
            bpr = (w + 7) >> 3
            fill = self.fb.fill_rect
            ox, oy = x + self.ox, y + self.oy
            for ry in range(h):
                base = ry * bpr
                cx = 0
                while cx < w:
                    if data[base + (cx >> 3)] & (0x80 >> (cx & 7)):
                        start = cx
                        while cx < w and data[base + (cx >> 3)] & (0x80 >> (cx & 7)):
                            cx += 1
                        fill(ox + start * scale, oy + ry * scale, (cx - start) * scale, scale, ink)
                    else:
                        cx += 1
            return
        stride = ((w + 7) >> 3) << 3
        if ink == BLACK:
            data = bytearray(b ^ 255 for b in data)
            key = 1
        else:
            data = bytearray(data)
            key = 0
        g = framebuf.FrameBuffer(data, w, h, framebuf.MONO_HLSB, stride)
        self.fb.blit(g, x + self.ox, y + self.oy, key)

    def art(self, x, y, rows, scale=1, ink=BLACK, on="#X@*1", opaque=False, invert=False):
        """Draw ASCII pixel art: every character in `on` is an ink pixel, all others are
        transparent (paper when opaque=True; invert=True swaps the two roles).

            c.art(10, 10, ["..##..",
                           ".####.",
                           "######"], scale=3)

        Returns (width, height) in screen pixels, handy for placing things next to it.
        """
        scale = max(1, int(scale))
        rows = [str(r) for r in rows]
        h = len(rows)
        w = max([len(r) for r in rows] or [0])
        if w * scale > 2000 or h * scale > 2000:
            raise ValueError("art is too big (%dx%d px)" % (w * scale, h * scale))
        if opaque and w and h:
            self.rect(x, y, w * scale, h * scale, 1 - ink, True)
        for ry in range(h):
            row = rows[ry]
            if invert and len(row) < w:
                row = row + "." * (w - len(row))  # missing cells count as "off", i.e. ink when inverted
            n = len(row)
            cx = 0
            while cx < n:
                if (row[cx] in on) != invert:
                    start = cx
                    while cx < n and (row[cx] in on) != invert:
                        cx += 1
                    self.rect(x + start * scale, y + ry * scale, (cx - start) * scale, scale, ink, True)
                else:
                    cx += 1
        return w * scale, h * scale

    def get(self, x, y):
        return self.fb.pixel(x + self.ox, y + self.oy)

    # -- output ----------------------------------------------------------
    def native(self):
        """Return 4000 bytes in the panel's RAM order for the current rotation."""
        b = self.buf
        r = self.rotation
        if r == 90:
            return b
        out = bytearray(4000)
        if r == 0:
            # nx = y, ny = 249 - x ; page c of column x holds nx = 8c..8c+7 (bit0 = 8c)
            rev = _rev_table()
            o = 0
            for ny in range(250):
                x = 249 - ny
                for c in range(16):
                    out[o] = rev[b[c * 250 + x]]
                    o += 1
        elif r == 180:
            # nx = 121 - y (oy = 6 -> nx = 127 - buffer_row), ny = x
            for ny in range(250):
                o = ny * 16
                for c in range(16):
                    out[o + c] = b[(15 - c) * 250 + ny]
        else:  # 270: nx = 121 - x (ox = 6), ny = 249 - y
            rev = _rev_table()
            for ny in range(250):
                y = 249 - ny
                o = ny * 16
                for c in range(16):
                    out[o + c] = rev[b[y * 16 + (15 - c)]]
        return out

    def pbm(self):
        """Logical image as PBM P4 (1 = black) - used for the web preview."""
        w, h = self.w, self.h
        bpr = (w + 7) >> 3
        out = bytearray(b"P4\n%d %d\n" % (w, h)) + bytearray(bpr * h)
        base = len(out) - bpr * h
        px = self.fb.pixel
        ox, oy = self.ox, self.oy
        for y in range(h):
            row = base + y * bpr
            yy = y + oy
            for x in range(w):
                if px(x + ox, yy) == 0:
                    out[row + (x >> 3)] |= 0x80 >> (x & 7)
        return out


# -- bitmap fonts ---------------------------------------------------------
# File layout: "BF1" height ascent count(u16) pad | count * (cp u16, w u8, adv u8,
# xoff i8, off u16) | glyph rows (ceil(w/8) bytes per row, `height` rows)
_HDR = 8
_ENT = 7


class Font:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.d = f.read()
        if self.d[:3] != b"BF1":
            raise ValueError("bad font file: " + path)
        self.h, self.asc, self.n = struct.unpack_from("<BBH", self.d, 3)
        self.base = _HDR + self.n * _ENT

    def _find(self, cp):
        lo, hi = 0, self.n - 1
        d = self.d
        while lo <= hi:
            mid = (lo + hi) >> 1
            pos = _HDR + mid * _ENT
            c = d[pos] | (d[pos + 1] << 8)
            if c == cp:
                return pos
            if c < cp:
                lo = mid + 1
            else:
                hi = mid - 1
        return -1

    def glyph(self, ch):
        pos = self._find(ord(ch))
        if pos < 0:
            pos = self._find(63)  # '?'
            if pos < 0:
                return None
        cp, w, adv, xoff, off = struct.unpack_from("<HBBbH", self.d, pos)
        n = ((w + 7) >> 3) * self.h
        return w, adv, xoff, self.d[self.base + off:self.base + off + n]

    def adv(self, ch):
        g = self.glyph(ch)
        return g[1] if g else 0

    def width(self, s):
        return sum(self.adv(ch) for ch in s)

    def draw(self, canvas, s, x, y, ink=BLACK):
        for ch in s:
            g = self.glyph(ch)
            if not g:
                continue
            w, adv, xoff, data = g
            if w and any(data):
                canvas.bits(x + xoff, y, w, self.h, data, ink)
            x += adv
        return x
