"""Shared helpers for the MicroPython-side tests."""
import os
import sys

_counter = [0]


def _cp(src, dst):
    if os.stat(src)[0] & 0x4000:
        try:
            os.mkdir(dst)
        except OSError:
            pass
        for n in os.listdir(src):
            if n == "__pycache__":
                continue
            _cp(src + "/" + n, dst + "/" + n)
    else:
        with open(src, "rb") as a, open(dst, "wb") as b:
            while True:
                chunk = a.read(1024)
                if not chunk:
                    break
                b.write(chunk)


def rmtree(path):
    for n in os.listdir(path):
        p = path + "/" + n
        if os.stat(p)[0] & 0x4000:
            rmtree(p)
        else:
            os.remove(p)
    os.rmdir(path)


def fresh_root():
    """Copy firmware/ (minus badge/ code, which is imported from the real tree) to a temp dir."""
    from badge import util
    _counter[0] += 1
    root = "/tmp/badge_test_%d_%d" % (os.getpid() if hasattr(os, "getpid") else 0, _counter[0])
    try:
        rmtree(root)
    except OSError:
        pass
    os.mkdir(root)
    for n in os.listdir("firmware"):
        if n in ("badge", "__pycache__"):
            continue
        _cp("firmware/" + n, root + "/" + n)
    util.ROOT = root
    # like the device, where "/" is on sys.path: plugins/ must resolve inside the temp root
    for name in [m for m in sys.modules if m == "plugins" or m.startswith("plugins.")]:
        del sys.modules[name]
    sys.path[:] = [q for q in sys.path if not q.startswith("/tmp/badge_test_")]
    sys.path.insert(0, root)
    return root


def black_pixels(canvas):
    n = 0
    for y in range(canvas.h):
        for x in range(canvas.w):
            if canvas.get(x, y) == 0:
                n += 1
    return n


def bbox(canvas, x0=0, y0=0, x1=None, y1=None):
    x1 = canvas.w if x1 is None else x1
    y1 = canvas.h if y1 is None else y1
    xs, ys = [], []
    for y in range(y0, y1):
        for x in range(x0, x1):
            if canvas.get(x, y) == 0:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)
