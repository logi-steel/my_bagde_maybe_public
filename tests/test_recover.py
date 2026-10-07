"""A broken over-the-air update must not brick the badge: roll back once, never loop."""
import sys
import json
import machine
import esp32
from machine import Pin
from helpers import fresh_root
from badge import util
from ssd1680_sim import SSD1680Sim


def forget(*prefixes):
    # keep badge.util: it carries the temp ROOT (on the device ROOT is simply "")
    for name in [m for m in sys.modules if any(m == p or m.startswith(p + ".") for p in prefixes)]:
        if name != "badge.util":
            del sys.modules[name]


def read(path):
    with open(util.p(path)) as f:
        return f.read()


def write(path, text):
    with open(util.p(path), "w") as f:
        f.write(text)


def run_main():
    """Execute main.py the way the device does, returning the exception it ends with (or None)."""
    src = read("/main.py")
    try:
        exec(compile(src, "main.py", "exec"), {"__name__": "__main__"})
    except (machine.DeepSleep, machine.Reset) as e:
        return e
    return None


root = fresh_root()
import recover
recover.ROOT = root
for n in (5, 6, 7, 2, 3):
    Pin(n)
Pin.registry[3]._v = 1
sim = SSD1680Sim(dc=6, cs=5, rst=7, busy=2)
machine._state["rtc"] = b""
machine.set_boot(machine.PWRON_RESET)
sys.path.insert(0, "firmware")  # the real badge/ package (fresh_root copies everything but badge/)
util.ROOT = root

# the device root contains badge/ - copy the real package into the temp root for this test
import os
os.mkdir(root + "/badge")
for n in os.listdir("firmware/badge"):
    if n.endswith(".py"):
        with open("firmware/badge/" + n) as a, open(root + "/badge/" + n, "w") as b:
            b.write(a.read())
sys.path[:] = [root] + [p for p in sys.path if p not in ("firmware",)]
for name in [m for m in sys.modules if m == "badge" or m.startswith("badge.")]:
    del sys.modules[name]
import badge.util as _bu          # imported from the temp root's copy of the package
_bu.ROOT = root
util = _bu

# 0) healthy start sleeps and leaves no flag behind
e = run_main()
assert isinstance(e, machine.DeepSleep), e
assert not util.exists("/rollback.flag")
print("0 healthy boot ok")

# 1) simulate a portal upload of a broken layout.py: new file live, old one kept as .bak
good = read("/badge/layout.py")
util.write_atomic("/badge/layout.py", "raise NameError('oops from a bad upload')\n", backup="/badge/layout.py.bak")
forget("badge")
e = run_main()
assert isinstance(e, machine.Reset), "first failure must roll back and reset, got %r" % (e,)
assert read("/badge/layout.py") == good, "good version must be back"
assert "oops" in read("/badge/layout.py.bak"), "the broken version must stay reachable as .bak"
assert util.exists("/rollback.flag")
assert "NameError" in read("/error.log") and "rolled back" in read("/error.log")
print("1 broken upload rolled back ok")

# 2) after the rollback the badge starts again and cancels the pending state
forget("badge")
e = run_main()
assert isinstance(e, machine.DeepSleep), e
assert not util.exists("/rollback.flag"), "a healthy cycle clears the flag"
print("2 recovered badge boots and clears the flag ok")

# 3) it is broken AGAIN (and now both versions are bad): roll back must not ping-pong forever
util.write_atomic("/badge/layout.py", "raise NameError('bad 1')\n", backup="/badge/layout.py.bak")
forget("badge")
assert isinstance(run_main(), machine.Reset)            # first failure: swap
write("/badge/layout.py", "raise NameError('bad 2')\n")  # the swapped-in version is bad as well
forget("badge")
e = run_main()                                           # second failure: flag set -> no more swaps
assert isinstance(e, machine.DeepSleep) and e.ms == 3600000, e
assert util.exists("/rollback.flag")
print("3 no rollback loop: sleeps an hour instead ok")

# 4) with nothing to roll back it still reports and sleeps instead of crashing
for n in list(os.listdir(root + "/badge")):
    if n.endswith(".bak"):
        os.remove(root + "/badge/" + n)
recover.clear_flag()
forget("badge")
e = run_main()
assert isinstance(e, machine.DeepSleep) and e.ms == 3600000
print("4 nothing to roll back ok")
print("test_recover: OK")
