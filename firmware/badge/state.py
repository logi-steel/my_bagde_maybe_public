"""Tiny persistent state kept in RTC memory (survives deep sleep, lost on power-off)."""
import struct
import machine

_FMT = "<BBBBBH"
_MAGIC = 0xB7


class State:
    def __init__(self):
        self.page = 0
        self.partials = 0     # partial refreshes since the last full one
        self.panel_ok = False  # panel holds an image we can partially refresh on top of
        self.crashes = 0
        self.battery = 0      # last measured percent (0 = unknown)

    def load(self):
        try:
            raw = machine.RTC().memory()
            m, page, partials, flags, crashes, bat = struct.unpack(_FMT, raw[:struct.calcsize(_FMT)])
            if m == _MAGIC:
                self.page, self.partials = page, partials
                self.panel_ok = bool(flags & 1)
                self.crashes, self.battery = crashes, bat
        except Exception:
            pass
        return self

    def save(self):
        try:
            machine.RTC().memory(struct.pack(_FMT, _MAGIC, self.page & 255, self.partials & 255,
                                             1 if self.panel_ok else 0, self.crashes & 255,
                                             self.battery & 0xFFFF))
        except Exception:
            pass
