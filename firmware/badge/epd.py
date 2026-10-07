"""SSD1680 e-paper driver for 250x122 panels (Waveshare 2.13" V4 / GDEY0213B74 class).

Register/command sequences are taken from Waveshare's epd2in13_V4.py (MIT licence, see
https://github.com/waveshareteam/e-Paper): init, display, displayPartBaseImage,
displayPartial, sleep - rewritten for MicroPython. The only additions are a BUSY
timeout (a missing panel must not hang the badge forever) and a proper reset
wait after wake-up.

RAM layout (native): 122 source columns x 250 gate rows, one row = 16 bytes,
MSB first, 1 = white, 0 = black.
"""
import time
from machine import Pin

NATIVE_BYTES = 16 * 250

_BUSY_TIMEOUT_MS = 12000


class EPDError(OSError):
    pass


class EPD:
    def __init__(self, spi, cs, dc, rst, busy):
        self.spi = spi
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)
        self.busy = Pin(busy, Pin.IN)

    # -- low level -------------------------------------------------------
    def _cmd(self, c, *data):
        self.dc(0)
        self.cs(0)
        self.spi.write(bytes((c,)))
        self.cs(1)
        if data:
            self._data(bytes(data))

    def _data(self, buf):
        self.dc(1)
        self.cs(0)
        self.spi.write(buf)
        self.cs(1)

    def _wait(self):
        # BUSY is high while the controller works
        t0 = time.ticks_ms()
        while self.busy.value() == 1:
            if time.ticks_diff(time.ticks_ms(), t0) > _BUSY_TIMEOUT_MS:
                raise EPDError("e-paper BUSY timeout - check wiring")
            time.sleep_ms(10)

    def _reset(self):
        self.rst(1)
        time.sleep_ms(20)
        self.rst(0)
        time.sleep_ms(2)
        self.rst(1)
        time.sleep_ms(20)

    def _cursor(self):
        self._cmd(0x4E, 0)
        self._cmd(0x4F, 0, 0)

    def _window(self):
        # x in bytes (0..15), y in lines (0..249)
        self._cmd(0x44, 0, 15)
        self._cmd(0x45, 0, 0, 249, 0)
        self._cursor()

    def _turn_on(self, mode):
        # 0xF7 full, 0xFF partial (Waveshare TurnOnDisplay / TurnOnDisplayPart)
        self._cmd(0x22, mode)
        self._cmd(0x20)
        self._wait()

    # -- public ----------------------------------------------------------
    def init_full(self):
        """Full init, sequence from epd2in13_V4.init()."""
        self._reset()
        self._wait()
        self._cmd(0x12)  # SWRESET
        self._wait()
        self._cmd(0x01, 0xF9, 0x00, 0x00)  # driver output control
        self._cmd(0x11, 0x03)  # data entry mode
        self._window()
        self._cmd(0x3C, 0x05)  # border waveform
        self._cmd(0x21, 0x00, 0x80)  # display update control
        self._cmd(0x18, 0x80)  # internal temperature sensor
        self._wait()

    def show_full(self, native):
        """Full refresh (~2-3 s). Also loads the partial-refresh base image."""
        self.init_full()
        self._cmd(0x24)
        self._data(native)
        self._cursor()  # Waveshare relies on the address counter wrapping; be explicit
        self._cmd(0x26)
        self._data(native)
        self._turn_on(0xF7)

    def show_partial(self, native):
        """Fast refresh (~0.3-0.5 s). Needs a previous show_full()."""
        # displayPartial() from epd2in13_V4.py; reset also wakes the panel
        self._reset()
        self._wait()
        self._cmd(0x3C, 0x80)
        self._cmd(0x01, 0xF9, 0x00, 0x00)
        self._cmd(0x11, 0x03)
        self._window()
        self._cmd(0x24)
        self._data(native)
        self._turn_on(0xFF)
        # keep "previous frame" RAM in sync so the next partial diffs correctly
        self._cursor()
        self._cmd(0x26)
        self._data(native)

    def sleep(self):
        """Deep sleep mode 1 (RAM retained). Image stays on the panel."""
        self._cmd(0x10, 0x01)
        time.sleep_ms(100)
