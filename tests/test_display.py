"""Canvas -> native bits -> EPD driver -> simulated SSD1680, checked pixel by pixel."""
import machine
from machine import Pin, SPI
from badge.canvas import Canvas, BLACK, WHITE
from badge.epd import EPD, EPDError
from ssd1680_sim import SSD1680Sim


def make():
    spi = SPI(1, 4000000, sck=Pin(8), mosi=Pin(10), miso=Pin(9))
    epd = EPD(spi, cs=5, dc=4, rst=7, busy=6)
    sim = SSD1680Sim(dc=4, cs=5, rst=7, busy=6)
    return epd, sim


def to_native(rot, x, y):
    # independent, pixel-level definition of the four orientations
    if rot == 0:
        return y, 249 - x            # == Waveshare getbuffer(): image.rotate(90, expand=True)
    if rot == 180:
        return 121 - y, x
    if rot == 90:
        return x, y
    return 121 - x, 249 - y          # 270


def noise(c):
    seed = 12345
    for y in range(c.h):
        for x in range(c.w):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            c.pixel(x, y, (seed >> 16) & 1)


def check_rotation(rot):
    epd, sim = make()
    c = Canvas(rot)
    noise(c)
    # extra asymmetric markers so a mirrored result can't pass by luck
    c.rect(0, 0, 12, 7, BLACK, True)
    c.rect(c.w - 5, c.h - 3, 5, 3, WHITE, True)
    epd.show_full(c.native())
    assert not sim.errors, sim.errors
    bad = 0
    for y in range(c.h):
        for x in range(c.w):
            nx, ny = to_native(rot, x, y)
            if sim.native_pixel(nx, ny) != c.get(x, y):
                bad += 1
    assert bad == 0, "rotation %d: %d mismatching pixels" % (rot, bad)
    assert [r[0] for r in sim.refreshes] == [0xF7]
    assert sim.refreshes[0][1] == sim.refreshes[0][2], "base image must be in both RAMs"
    print("rotation", rot, "ok")


def check_partial_and_sleep():
    epd, sim = make()
    c = Canvas(0)
    c.text8("one", 4, 4)
    epd.show_full(c.native())
    c.clear()
    c.text8("two", 4, 4)
    epd.show_partial(c.native())
    assert [r[0] for r in sim.refreshes] == [0xF7, 0xFF], sim.refreshes
    assert sim.ram24 == sim.ram26, "partial must leave 'old' RAM equal to shown frame"
    assert bytes(sim.screen) == bytes(c.native())
    epd.sleep()
    assert sim.asleep
    # waking: a partial refresh does its own hardware reset, so this must be clean
    c.clear()
    c.text8("three", 4, 4)
    epd.show_partial(c.native())
    assert not sim.errors, sim.errors
    assert len(sim.refreshes) == 3
    # and the simulator really would have caught a missing reset
    epd.sleep()
    epd._cmd(0x12)
    assert sim.errors and "while asleep" in sim.errors[0]
    print("partial/sleep ok")


def check_busy_timeout():
    import badge.epd as e
    epd, sim = make()
    e._BUSY_TIMEOUT_MS = 50
    Pin.registry[6]._v = 1  # panel stuck busy / not connected
    try:
        epd.show_full(bytes(4000))
    except EPDError:
        print("busy timeout ok")
        return
    raise AssertionError("expected EPDError")


for r in (0, 90, 180, 270):
    check_rotation(r)
check_partial_and_sleep()
check_busy_timeout()
print("test_display: OK")
