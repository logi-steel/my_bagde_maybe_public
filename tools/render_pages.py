"""Run under MicroPython (host): render every page of a config to PBM files.

  micropython tools/render_pages.py <firmware_root> <config.json> <out_dir> [rotation]

No mocks needed - the renderer does not touch hardware. tools/preview.py wraps this.
"""
import sys

root, cfg_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
from badge import util, config, layout
from badge.canvas import Canvas

util.ROOT = root
with open(cfg_path) as f:
    cfg = config.parse(f.read())
if len(sys.argv) > 4:
    cfg["device"]["rotation"] = int(sys.argv[4])
errs, warns = config.validate(cfg)
for e in errs:
    print("ERROR:", e)
for w in warns:
    print("warning:", w)
for i in range(len(cfg["pages"])):
    c = Canvas(cfg["device"]["rotation"])
    ctx = layout.render_page(c, cfg, i, battery=cfg["vars"].get("battery_demo", 87),
                             reload_plugins=True, log=False)
    for m in ctx.errors:
        print("render error:", m)
    with open("%s/page%d.pbm" % (out_dir, i), "wb") as f:
        f.write(c.pbm())
print("pages", len(cfg["pages"]))
