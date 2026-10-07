"""Host mock of MicroPython's `machine` (just enough for the badge firmware tests)."""

PIN_WAKE = 2   # NB: on real MicroPython this is EXT0 (absent on ESP32-C3), GPIO wake is cause 7
TIMER_WAKE = 4
PWRON_RESET = 1
DEEPSLEEP_RESET = 4
SOFT_RESET = 5
HARD_RESET = 2


class DeepSleep(BaseException):
    """Raised by deepsleep() so tests can observe 'the device went to sleep'.

    BaseException on purpose: the real deepsleep() never returns and must not be
    swallowed by `except Exception` in the firmware."""

    def __init__(self, ms=None):
        self.ms = ms


class Reset(BaseException):
    pass


_state = {"reset_cause": PWRON_RESET, "wake_reason": 0, "wake_pins": (), "rtc": b""}


def set_boot(reset_cause=PWRON_RESET, wake_reason=0, wake_pins=()):
    _state["reset_cause"] = reset_cause
    _state["wake_reason"] = wake_reason
    _state["wake_pins"] = wake_pins


def reset_cause():
    return _state["reset_cause"]


def wake_reason():
    return _state["wake_reason"]


def wake_pins():
    return _state["wake_pins"]


def deepsleep(ms=None):
    raise DeepSleep(ms)


def reset():
    raise Reset()


def unique_id():
    return b"\xde\xad\xbe\xef\x12\x34"


def freq(*a):
    return 160000000


class Pin:
    OUT = 1
    IN = 0
    OPEN_DRAIN = 2
    PULL_UP = 2
    PULL_DOWN = 3
    registry = {}

    def __init__(self, id, mode=-1, pull=-1, value=None):
        self.id = id
        self.watch = None
        old = Pin.registry.get(id)
        self._v = old._v if old else 1
        if value is not None:
            self._v = value
        Pin.registry[id] = self
        if old and old.watch:
            self.watch = old.watch

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = 1 if v else 0
        if self.watch:
            self.watch(self._v)

    __call__ = value


class SPI:
    hook = None

    def __init__(self, id, baudrate=1000000, polarity=0, phase=0, sck=None, mosi=None, miso=None):
        self.id = id
        self.baudrate = baudrate

    def write(self, buf):
        if SPI.hook:
            SPI.hook(bytes(buf))


class ADC:
    ATTN_11DB = 3

    def __init__(self, pin, atten=None):
        self.pin = pin
        self.uv = 1900000

    def read_uv(self):
        return self.uv


class RTC:
    def memory(self, data=None):
        if data is None:
            return _state["rtc"]
        _state["rtc"] = bytes(data)
