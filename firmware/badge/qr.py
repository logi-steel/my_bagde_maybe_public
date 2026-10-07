"""Compact QR Code encoder for MicroPython: byte mode, versions 1-10, ECC L/M/Q/H.

Version 10 holds 271 bytes at ECC L, plenty for URLs, vCards and Wi-Fi join codes.
Algorithm follows the QR spec (ISO/IEC 18004); checked bit-for-bit against segno.
"""

# [version] for versions 0(unused)..10
_ECC_PER_BLOCK = {
    "L": (0, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18),
    "M": (0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26),
    "Q": (0, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24),
    "H": (0, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28),
}
_NUM_BLOCKS = {
    "L": (0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4),
    "M": (0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5),
    "Q": (0, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8),
    "H": (0, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8),
}
_FORMAT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}
MAX_VERSION = 10

_EXP = None
_LOG = None


def _gf_tables():
    global _EXP, _LOG
    if _EXP is None:
        exp = bytearray(512)
        log = bytearray(256)
        x = 1
        for i in range(255):
            exp[i] = x
            log[x] = i
            x <<= 1
            if x & 0x100:
                x ^= 0x11D
        for i in range(255, 512):
            exp[i] = exp[i - 255]
        _EXP, _LOG = exp, log
    return _EXP, _LOG


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    exp, log = _gf_tables()
    return exp[log[a] + log[b]]


def _rs_divisor(degree):
    res = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _mul(root, 2)
    return res


def _rs_remainder(data, divisor):
    res = [0] * len(divisor)
    for b in data:
        factor = b ^ res.pop(0)
        res.append(0)
        for i in range(len(divisor)):
            res[i] ^= _mul(divisor[i], factor)
    return res


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        r -= (25 * n - 10) * n - 55
        if ver >= 7:
            r -= 36
    return r


def capacity(ver, ecc):
    """Max number of bytes (byte mode) for a version/ECC combination."""
    data_cw = _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ecc][ver] * _NUM_BLOCKS[ecc][ver]
    cc_bits = 8 if ver < 10 else 16
    return (data_cw * 8 - 4 - cc_bits) // 8


def _align_positions(ver):
    if ver == 1:
        return []
    n = ver // 7 + 2
    size = ver * 4 + 17
    step = (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    res = [size - 7 - i * step for i in range(n - 1)] + [6]
    res.reverse()
    return res


def _codewords(data, ver, ecc):
    """Pad, split into blocks, add Reed-Solomon ECC and interleave."""
    cc_bits = 8 if ver < 10 else 16
    nblocks = _NUM_BLOCKS[ecc][ver]
    ecc_len = _ECC_PER_BLOCK[ecc][ver]
    raw = _raw_modules(ver) // 8
    data_cw = raw - ecc_len * nblocks
    cap_bits = data_cw * 8
    cw = bytearray()
    acc = 0
    nacc = 0
    total = 0
    # bit writer (no per-bit lists or tuples: the C3 heap is small)
    for val, n in ((4, 4), (len(data), cc_bits)):
        acc = (acc << n) | val
        nacc += n
        total += n
        while nacc >= 8:
            nacc -= 8
            cw.append((acc >> nacc) & 0xFF)
        acc &= (1 << nacc) - 1
    for b in data:  # nacc stays constant here: 8 bits in, 8 bits out
        acc = (acc << 8) | b
        cw.append((acc >> nacc) & 0xFF)
        acc &= (1 << nacc) - 1
    total += 8 * len(data)
    term = min(4, cap_bits - total)  # terminator
    acc <<= term
    nacc += term
    if nacc:
        cw.append((acc << (8 - nacc)) & 0xFF)
    pad = 0xEC
    while len(cw) < data_cw:
        cw.append(pad)
        pad ^= 0xEC ^ 0x11
    short = nblocks - raw % nblocks
    short_len = raw // nblocks
    divisor = _rs_divisor(ecc_len)
    datas = []
    eccs = []
    k = 0
    for i in range(nblocks):
        n = short_len - ecc_len + (0 if i < short else 1)
        d = list(cw[k:k + n])
        k += n
        datas.append(d)
        eccs.append(_rs_remainder(d, divisor))
    # interleave: all data codewords first, then all ECC codewords
    out = bytearray()
    for i in range(short_len - ecc_len + 1):
        for d in datas:
            if i < len(d):
                out.append(d[i])
    for i in range(ecc_len):
        for e in eccs:
            out.append(e[i])
    return out


class _Matrix:
    def __init__(self, ver):
        self.n = ver * 4 + 17
        self.m = bytearray(self.n * self.n)   # 1 = dark
        self.f = bytearray(self.n * self.n)   # 1 = function pattern (never masked)

    def set(self, x, y, dark, func=True):
        i = y * self.n + x
        self.m[i] = 1 if dark else 0
        if func:
            self.f[i] = 1

    def get(self, x, y):
        return self.m[y * self.n + x]


def _function_patterns(mx, ver):
    n = mx.n
    for i in range(n):
        mx.set(6, i, i % 2 == 0)
        mx.set(i, 6, i % 2 == 0)

    def finder(cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    d = max(abs(dx), abs(dy))
                    mx.set(x, y, d != 2 and d != 4)

    finder(3, 3)
    finder(n - 4, 3)
    finder(3, n - 4)
    pos = _align_positions(ver)
    last = len(pos) - 1
    for i in range(len(pos)):
        for j in range(len(pos)):
            if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    mx.set(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
    _format_bits(mx, "L", 0)  # reserve the format areas (real bits drawn later)
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = ver << 12 | rem
        for i in range(18):
            bit = (bits >> i) & 1
            a = n - 11 + i % 3
            b = i // 3
            mx.set(a, b, bit)
            mx.set(b, a, bit)


def _format_bits(mx, ecc, mask):
    n = mx.n
    data = _FORMAT_BITS[ecc] << 3 | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412
    for i in range(0, 6):
        mx.set(8, i, (bits >> i) & 1)
    mx.set(8, 7, (bits >> 6) & 1)
    mx.set(8, 8, (bits >> 7) & 1)
    mx.set(7, 8, (bits >> 8) & 1)
    for i in range(9, 15):
        mx.set(14 - i, 8, (bits >> i) & 1)
    for i in range(0, 8):
        mx.set(n - 1 - i, 8, (bits >> i) & 1)
    for i in range(8, 15):
        mx.set(8, n - 15 + i, (bits >> i) & 1)
    mx.set(8, n - 8, 1)


def _place(mx, cw):
    n = mx.n
    i = 0
    total = len(cw) * 8
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = n - 1 - vert if upward else vert
                idx = y * n + x
                if not mx.f[idx] and i < total:
                    mx.m[idx] = (cw[i >> 3] >> (7 - (i & 7))) & 1
                    i += 1
        right -= 2


def _mask_fn(mask):
    if mask == 0:
        return lambda x, y: (x + y) % 2 == 0
    if mask == 1:
        return lambda x, y: y % 2 == 0
    if mask == 2:
        return lambda x, y: x % 3 == 0
    if mask == 3:
        return lambda x, y: (x + y) % 3 == 0
    if mask == 4:
        return lambda x, y: (x // 3 + y // 2) % 2 == 0
    if mask == 5:
        return lambda x, y: x * y % 2 + x * y % 3 == 0
    if mask == 6:
        return lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0
    return lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0


def _apply_mask(mx, mask):
    fn = _mask_fn(mask)
    n = mx.n
    for y in range(n):
        for x in range(n):
            i = y * n + x
            if not mx.f[i] and fn(x, y):
                mx.m[i] ^= 1


def _penalty(mx):
    n = mx.n
    m = mx.m
    score = 0
    dark = 0
    for horizontal in (True, False):
        for a in range(n):
            run_color = -1
            run = 0
            bits = 0
            for b in range(n + 4):
                # past the end the line continues with (virtual) light modules, so
                # finder-like patterns touching the border are counted like inside ones
                c = 0
                if b < n:
                    c = m[a * n + b] if horizontal else m[b * n + a]
                    if horizontal:
                        dark += c
                    if c == run_color:
                        run += 1
                        if run == 5:
                            score += 3
                        elif run > 5:
                            score += 1
                    else:
                        run_color = c
                        run = 1
                bits = ((bits << 1) | c) & 0x7FF
                if bits == 0x5D0 or bits == 0x05D:
                    score += 40
    for y in range(n - 1):
        for x in range(n - 1):
            c = m[y * n + x]
            if c == m[y * n + x + 1] and c == m[(y + 1) * n + x] and c == m[(y + 1) * n + x + 1]:
                score += 3
    total = n * n
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    return score + k * 10


def encode(text, ecc="M", min_version=1, mask=None):
    """Return (size, modules) where modules is a bytearray of size*size (1 = dark)."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    ecc = ecc.upper()
    ver = max(1, min_version)
    while ver <= MAX_VERSION and capacity(ver, ecc) < len(data):
        ver += 1
    if ver > MAX_VERSION:
        raise ValueError("QR payload too long (%d bytes, max %d at ECC %s)" % (
            len(data), capacity(MAX_VERSION, ecc), ecc))
    cw = _codewords(data, ver, ecc)
    mx = _Matrix(ver)
    _function_patterns(mx, ver)
    _place(mx, cw)
    if mask is None:
        best, best_score = 0, None
        for k in range(8):
            _apply_mask(mx, k)
            _format_bits(mx, ecc, k)
            s = _penalty(mx)
            _apply_mask(mx, k)  # undo
            if best_score is None or s < best_score:
                best, best_score = k, s
        mask = best
    _apply_mask(mx, mask)
    _format_bits(mx, ecc, mask)
    return mx.n, mx.m


def draw_modules(canvas, n, m, x, y, scale=2, border=2, ink=0):
    """Draw an already encoded code; (x, y) is the top-left of the quiet zone."""
    total = (n + 2 * border) * scale
    canvas.rect(x, y, total, total, 1 - ink, True)
    for row in range(n):
        col = 0
        while col < n:
            if m[row * n + col]:
                start = col
                while col < n and m[row * n + col]:
                    col += 1
                canvas.rect(x + (border + start) * scale, y + (border + row) * scale,
                            (col - start) * scale, scale, ink, True)
            else:
                col += 1
    return total


def draw(canvas, text, x, y, scale=2, ecc="M", border=2, ink=0, mask=None):
    """Encode + draw. Returns the edge length in pixels."""
    n, m = encode(text, ecc, mask=mask)
    return draw_modules(canvas, n, m, x, y, scale, border, ink)
