import json
import sys
from helpers import fresh_root, black_pixels, bbox
from badge import util, config, layout
from badge.canvas import Canvas


root = fresh_root()

# -- template + wrap helpers -------------------------------------------------
assert layout.fmt("Hi {name}, {unknown}!", {"name": "Logi"}) == "Hi Logi, {unknown}!"
assert layout.fmt("no braces", {}) == "no braces"
assert layout.fmt("open { brace", {}) == "open { brace"

ctx = layout.Ctx(config.parse("{}"), Canvas(0))
f = ctx.font("s12")
lines = layout.wrap("the quick brown fox jumps over the lazy dog", f, 100)
assert len(lines) >= 3 and all(f.width(l) <= 100 for l in lines), lines
assert layout.wrap("a\nb", f, 100) == ["a", "b"]
long = layout.wrap("supercalifragilisticexpialidocious", f, 60)
assert len(long) > 1 and all(f.width(l) <= 60 for l in long), long
cut = layout.wrap("one two three four five six seven eight", f, 80, max_lines=2)
assert len(cut) == 2 and cut[1].endswith("…"), cut
print("fmt/wrap ok")

# -- shipped config is clean -------------------------------------------------
cfg = config.parse(util.read_text("/config.json"))
errs, warns = config.validate(cfg)
assert not errs and not warns, (errs, warns)
print("shipped config validates")

# -- every page renders on every rotation, without widget errors --------------
for rot in (0, 90, 180, 270):
    cfg["device"]["rotation"] = rot
    for i in range(len(cfg["pages"])):
        c = Canvas(rot)
        cx = layout.render_page(c, cfg, i, battery=55, reload_plugins=True, log=False)
        assert not cx.errors, (rot, i, cx.errors)
        assert black_pixels(c) > 200, "page %d rot %d is blank" % (i, rot)
print("pages render on all rotations")

# -- alignment ---------------------------------------------------------------
cfg = config.parse(json.dumps({"pages": [{"items": [
    {"type": "text", "text": "MID", "x": 0, "y": 40, "w": 250, "align": "center", "font": "b24"},
    {"type": "text", "text": "R", "x": 0, "y": 80, "w": 250, "align": "right", "font": "b24"},
]}]}))
c = Canvas(0)
layout.render_page(c, cfg, 0, log=False)
mid = bbox(c, 0, 40, 250, 70)
assert abs((mid[0] + mid[2]) / 2 - 125) <= 3, mid
r = bbox(c, 0, 80, 250, 112)
assert r[2] >= 235, r
print("alignment ok")

# -- a broken widget must not take the page down ------------------------------
cfg = config.parse(json.dumps({"pages": [{"items": [
    {"type": "text", "text": "still here", "x": 4, "y": 4, "font": "b16"},
    {"type": "plugin", "name": "does_not_exist", "x": 150, "y": 60},
    {"type": "image", "src": "img/nope.pbm", "x": 10, "y": 60},
    {"type": "qr", "data": "x" * 400, "x": 0, "y": 0},
]}]}))
c = Canvas(0)
cx = layout.render_page(c, cfg, 0, log=False)
assert len(cx.errors) == 3, cx.errors
assert black_pixels(c) > 100
print("widget errors are isolated:", len(cx.errors), "reported")

# a plugin that raises
with open(util.p("/plugins/boom.py"), "w") as f:
    f.write("def draw(c, item, ctx):\n    raise RuntimeError('kaboom')\n")
cfg = config.parse(json.dumps({"pages": [{"items": [{"type": "plugin", "name": "boom", "x": 5, "y": 5}]}]}))
c = Canvas(0)
cx = layout.render_page(c, cfg, 0, log=False)
assert cx.errors and "kaboom" in cx.errors[0], cx.errors
print("raising plugin handled")

# -- validation catches mistakes -----------------------------------------------
bad = {"device": {"rotation": 45}, "pages": [{"items": [{"type": "nope"}, {"type": "text"},
                                                        {"type": "qr"}, {"type": "text", "text": "x", "x": "a"}]}]}
errs, _ = config.validate(config.parse(json.dumps(bad)))
assert len(errs) >= 5, errs
errs, warns = config.validate(config.parse(json.dumps({"device": {"sleep": "deep"}, "hardware": {"btn_next": 9}, "pages": []})))
assert any("GPIO0-5" in w for w in warns), warns
print("validation ok")

# -- config load / save / fallback --------------------------------------------
c1, problem = config.load()
assert problem is None and len(c1["pages"]) == 4
good = json.dumps({"vars": {"name": "Zed"}, "pages": [{"items": [{"type": "text", "text": "{name}", "x": 1, "y": 1}]}]})
warn = config.save_text(good)
assert util.exists("/config.json") and util.exists("/config.json.bak")
assert json.loads(util.read_text("/config.json.bak"))["vars"]["name"] == "Logi", "old config must become the backup"
try:
    config.save_text('{"pages": [{"items": [{"type": "bogus"}]}]}')
    raise AssertionError("invalid config was saved")
except ValueError:
    pass
try:
    config.save_text("{not json")
    raise AssertionError("broken JSON was saved")
except ValueError:
    pass
assert json.loads(util.read_text("/config.json"))["vars"]["name"] == "Zed", "failed save must not touch config"
# corrupt the live file -> falls back to the backup
with open(util.p("/config.json"), "w") as f:
    f.write("{{{{ garbage")
c2, problem = config.load()
assert problem and "bak" in problem and c2["vars"]["name"] == "Logi", (problem, c2["vars"])
# corrupt both -> error page instead of a dead badge
with open(util.p("/config.json.bak"), "w") as f:
    f.write("also garbage")
c3, problem = config.load()
assert problem and len(c3["pages"]) == 1 and "error" in c3["vars"]
c = Canvas(0)
cx = layout.render_page(c, c3, 0, log=False)
assert not cx.errors and black_pixels(c) > 100
print("config save/backup/fallback ok")
print("test_layout: OK")
