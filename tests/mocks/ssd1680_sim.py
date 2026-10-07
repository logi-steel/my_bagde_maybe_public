"""Behavioural simulator of an SSD1680 250x122 panel, hooked to the mocked SPI/Pins.

Models what matters for the driver:
  * DC/CS discipline on every SPI write (a cmd must come with DC=0, CS=0 ...)
  * data entry mode 0x03 + RAM window/cursor addressing (X byte-wise, then Y)
  * BW RAM (0x24) and "old" RAM (0x26)
  * 0x22/0x20 refresh -> `screen` becomes BW RAM; log of every refresh
  * SWRESET keeps RAM, deep sleep ignores commands until a hardware reset pulse
"""
import machine

W_BYTES = 16
H = 250


class SSD1680Sim:
    def __init__(self, dc, cs, rst, busy):
        self.dc, self.cs, self.rst, self.busy = dc, cs, rst, busy
        self.ram24 = bytearray(b"\xff" * (W_BYTES * H))
        self.ram26 = bytearray(b"\xff" * (W_BYTES * H))
        self.screen = bytearray(b"\xff" * (W_BYTES * H))
        self.refreshes = []
        self.errors = []
        self.asleep = False
        self.cmd = None
        self.params = []
        self.update_mode = None
        self.reset_defaults()
        self.rst_seen_low = False
        machine.Pin.registry[rst].watch = self._rst_watch
        machine.Pin.registry[busy]._v = 0
        machine.SPI.hook = self.on_spi

    def reset_defaults(self):
        self.entry = 0x01
        self.xs, self.xe, self.ys, self.ye = 0, 0x15, 0, 0x127
        self.cx, self.cy = 0, 0
        self.cmd_log = []

    def _rst_watch(self, v):
        if v == 0:
            self.rst_seen_low = True
        elif v == 1 and self.rst_seen_low:
            self.rst_seen_low = False
            self.asleep = False
            self.reset_defaults()

    def on_spi(self, data):
        d = machine.Pin.registry[self.dc].value()
        c = machine.Pin.registry[self.cs].value()
        if c != 0:
            self.errors.append("SPI write while CS=1")
            return
        if d == 0:
            if len(data) != 1:
                self.errors.append("command write longer than 1 byte")
                return
            self.begin(data[0])
        else:
            self.feed(data)

    def begin(self, cmd):
        if self.asleep:
            self.errors.append("command 0x%02X while asleep" % cmd)
            self.cmd = None
            return
        self.cmd = cmd
        self.params = []
        self.cmd_log.append(cmd)
        if cmd == 0x12:
            self.reset_defaults()
        elif cmd == 0x20:
            self.activate()
        elif cmd == 0x10:
            pass  # takes effect once its data byte arrives

    def feed(self, data):
        cmd = self.cmd
        if cmd is None:
            if not self.asleep:
                self.errors.append("data without command")
            return
        if cmd in (0x24, 0x26):
            ram = self.ram24 if cmd == 0x24 else self.ram26
            for b in data:
                ram[self.cy * W_BYTES + self.cx] = b
                self.cx += 1
                if self.cx > self.xe:
                    self.cx = self.xs
                    self.cy += 1
                    if self.cy > self.ye:
                        self.cy = self.ys  # window wrap
            return
        self.params += list(data)
        p = self.params
        if cmd == 0x11:
            self.entry = p[0]
            if p[0] != 0x03:
                self.errors.append("only data entry mode 0x03 is simulated")
        elif cmd == 0x44 and len(p) >= 2:
            self.xs, self.xe = p[0], p[1]
        elif cmd == 0x45 and len(p) >= 4:
            self.ys = p[0] | (p[1] << 8)
            self.ye = p[2] | (p[3] << 8)
        elif cmd == 0x4E and len(p) >= 1:
            self.cx = p[0]
        elif cmd == 0x4F and len(p) >= 2:
            self.cy = p[0] | (p[1] << 8)
        elif cmd == 0x22 and len(p) >= 1:
            self.update_mode = p[0]
        elif cmd == 0x10 and len(p) >= 1:
            self.asleep = True
            self.sleep_mode = p[0]

    def activate(self):
        mode = self.update_mode
        if mode not in (0xF7, 0xFF, 0xC7):
            self.errors.append("refresh with unknown mode %r" % (mode,))
        self.screen = bytearray(self.ram24)
        self.refreshes.append((mode, bytes(self.ram24), bytes(self.ram26)))

    # -- helpers for tests ----------------------------------------------
    def native_pixel(self, nx, ny):
        """1 = white, 0 = black, in native panel coordinates (122 x 250)."""
        return (self.screen[ny * W_BYTES + (nx >> 3)] >> (7 - (nx & 7))) & 1
