"""Whole device flow on the host: wake -> render -> SPI -> simulated SSD1680 -> sleep."""
import json
import sys
import machine
import esp32
from machine import Pin
from helpers import fresh_root
from badge import util, config, app, power, layout, epd as epd_mod
from badge.canvas import Canvas
from ssd1680_sim import SSD1680Sim

GPIO_WAKE = 7  # ESP_SLEEP_WAKEUP_GPIO - what the C3 really reports (PIN_WAKE would be EXT0)
BTN, BUSY = 3, 2


def setup(patch=None):
    root = fresh_root()
    machine._state["rtc"] = b""
    cfg = json.loads(util.read_text("/config.json"))
    if patch:
        for k, v in patch.items():
            cfg.setdefault("device", {}).update(v) if k == "device" else cfg.__setitem__(k, v)
    util.write_atomic("/config.json", json.dumps(cfg))
    for n in (5, 6, 7, BUSY, BTN):
        Pin(n)
    Pin.registry[BTN]._v = 1       # button released
    Pin.registry[BUSY]._v = 0
    esp32.armed.update(pins=None, level=None)
    return SSD1680Sim(dc=6, cs=5, rst=7, busy=BUSY)


def boot(kind, pins=()):
    if kind == "power":
        machine.set_boot(machine.PWRON_RESET)
    elif kind == "button":
        machine.set_boot(machine.DEEPSLEEP_RESET, GPIO_WAKE, pins or (BTN,))
    else:
        machine.set_boot(machine.DEEPSLEEP_RESET, machine.TIMER_WAKE)
    try:
        app.run()
    except machine.DeepSleep as e:
        return e
    raise AssertionError("app.run() returned instead of sleeping")


def expected_native(page, rotation=0):
    cfg, _ = config.load()
    bat = power.battery_percent(cfg["hardware"])
    c = Canvas(rotation)
    layout.render_page(c, cfg, page, bat, log=False)
    return bytes(c.native())


# 1) power-on: full refresh of page 0, then sleeps with the button armed ---------------
sim = setup()
e = boot("power")
assert e.ms is None, "no timer wake unless auto_rotate_min is set"
assert [r[0] for r in sim.refreshes] == [0xF7], sim.refreshes
assert sim.refreshes[0][1] == expected_native(0), "panel RAM != rendered page 0"
assert not sim.errors, sim.errors
assert sim.asleep, "panel must be put to sleep before the MCU sleeps"
assert [p.id for p in esp32.armed["pins"]] == [BTN] and esp32.armed["level"] == esp32.WAKEUP_ALL_LOW
print("1 power-on ok")

# 2) tap -> next page via PARTIAL refresh, state survives deep sleep (RTC memory) -----
e = boot("button")
assert [r[0] for r in sim.refreshes] == [0xF7, 0xFF], sim.refreshes
assert sim.refreshes[1][1] == expected_native(1), "panel RAM != rendered page 1"
assert not sim.errors, sim.errors
print("2 tap -> page 2, partial refresh ok")

# 3) a full refresh every N-th change (ghost clean-up) ---------------------------------
sim = setup({"device": {"full_refresh_every": 3}})
boot("power")
boot("button"); boot("button"); boot("button")
assert [r[0] for r in sim.refreshes] == [0xF7, 0xFF, 0xFF, 0xF7], [hex(r[0]) for r in sim.refreshes]
boot("button")
assert [r[0] for r in sim.refreshes][-1] == 0xFF
print("3 full refresh every 3rd update ok")

# 4) pages wrap around ----------------------------------------------------------------
sim = setup()
boot("power")
for _ in range(4):
    boot("button")
assert sim.refreshes[-1][1] == expected_native(0), "after 4 taps (4 pages) we are back on page 1"
print("4 page wrap-around ok")

# 5) timer wake = auto-rotate; sleep call carries the interval ------------------------
sim = setup({"device": {"auto_rotate_min": 5}})
e = boot("power")
assert e.ms == 300000, e.ms
e = boot("timer")
assert e.ms == 300000 and sim.refreshes[-1][1] == expected_native(1)
print("5 auto-rotate timer ok")

# 6) long press opens the portal, then reboots ---------------------------------------------
sim = setup({"device": {"long_press_ms": 120}})
boot("power")
calls = []
class _PortalStub:
    def run(self, cfg, st, btn):
        calls.append("portal")


stub = _PortalStub()
sys.modules["badge.portal"] = stub
import badge
badge.portal = stub
Pin.registry[BTN]._v = 0           # button is still held when we wake
machine.set_boot(machine.DEEPSLEEP_RESET, GPIO_WAKE, (BTN,))
try:
    app.run()
    raise AssertionError("expected reset after the portal")
except machine.Reset:
    pass
assert calls == ["portal"]
assert len(sim.refreshes) == 1, "long press must not redraw before the portal"
del sys.modules["badge.portal"]
print("6 long press -> portal ok")

# 7) a stuck button must not cause a wake-up loop ---------------------------------------------
sim = setup()
boot("power")
orig = power.Buttons.wait_release
power.Buttons.wait_release = lambda self, timeout_ms=0: False
esp32.armed.update(pins="untouched")
e = boot("timer")
power.Buttons.wait_release = orig
assert esp32.armed["pins"] == "untouched", "stuck button must NOT be armed as wake source"
assert e.ms == 3600000, e.ms
print("7 stuck button safe ok")

# 8) panel missing / BUSY stuck: no crash loop, retry with a full refresh next time ---------
sim = setup()
epd_mod._BUSY_TIMEOUT_MS = 30
Pin.registry[BUSY]._v = 1
e = boot("power")
assert "BUSY timeout" in util.read_text("/error.log")
Pin.registry[BUSY]._v = 0
sim2 = SSD1680Sim(dc=6, cs=5, rst=7, busy=BUSY)
boot("button")
assert [r[0] for r in sim2.refreshes] == [0xF7], "after a failed refresh the next one must be full"
epd_mod._BUSY_TIMEOUT_MS = 12000
print("8 missing panel handled ok")

# 9) portrait rotation end to end ---------------------------------------------------------------
sim = setup({"device": {"rotation": 90}})
boot("power")
assert sim.refreshes[0][1] == expected_native(0, 90)
sim = setup({"device": {"rotation": 270}})
boot("power")
assert sim.refreshes[0][1] == expected_native(0, 270)
print("9 portrait ok")

# 10) rescue(): shows an error screen, logs, sleeps an hour instead of crash-looping ------
sim = setup()
try:
    app.rescue(RuntimeError("synthetic failure"))
    raise AssertionError("rescue must sleep")
except machine.DeepSleep as e:
    assert e.ms == 3600000
assert len(sim.refreshes) == 1
assert "synthetic failure" in util.read_text("/error.log")
print("10 rescue ok")

# 11) dev mode keeps the MCU awake (USB/REPL alive) ----------------------------------------------
sim = setup({"device": {"sleep": "none"}})
import time as real_time


class Stop(Exception):
    pass


class FakeTime:
    """Builtin modules are read-only in MicroPython, so swap the reference inside power."""

    def __getattr__(self, name):
        return getattr(real_time, name)

    def sleep(self, s):
        raise Stop()


power.time = FakeTime()
try:
    machine.set_boot(machine.PWRON_RESET)
    app.run()
    raise AssertionError("dev mode should loop instead of returning")
except Stop:
    pass
finally:
    power.time = real_time
print("11 dev mode ok")
print("test_app: OK")
