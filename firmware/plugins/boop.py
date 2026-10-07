"""Example plugin: counts how many times this page was shown. Edit me from the web portal!

A plugin is a file /plugins/<name>.py with a function draw(c, item, ctx):
  c    - Canvas: c.w, c.h, c.rect(), c.line(), c.pixel(), c.text8(), c.bits() ...
  item - the JSON object of this widget (your own keys are welcome)
  ctx  - ctx.font("b24"), ctx.fmt("{name}"), ctx.vars, ctx.page_index, ctx.reload_plugins
"""
import json
from badge import util

PATH = "/data/boop.json"


def _count(bump):
    n = 0
    try:
        n = json.loads(util.read_text(PATH))["n"]
    except (OSError, ValueError, KeyError):
        pass
    if bump:
        n += 1
        util.write_atomic(PATH, json.dumps({"n": n}))
    return n


def draw(c, item, ctx):
    n = _count(bump=not ctx.reload_plugins)  # web preview must not count
    big = ctx.font("b36")
    small = ctx.font("s16")
    small.draw(c, "this badge was booped", 8, 8)
    big.draw(c, str(n), 8, 30)
    small.draw(c, "time" if n == 1 else "times", 16 + big.width(str(n)), 54)
    # tiny face, because why not
    c.ellipse(222, 40, 22, 22, 0, False)
    c.rect(212, 32, 4, 6, 0, True)
    c.rect(228, 32, 4, 6, 0, True)
    c.line(212, 50, 217, 54, 0)
    c.line(217, 54, 227, 54, 0)
    c.line(227, 54, 232, 50, 0)
    small.draw(c, ctx.fmt("-- {name}"), 8, 96)
