"""Battery measurement, button handling and sleep."""
import time
import machine
from machine import Pin

# LiPo open-circuit voltage -> percent (rough, good enough for a badge)
_CURVE = ((4.20, 100), (4.10, 90), (4.00, 80), (3.90, 65), (3.80, 50),
          (3.70, 35), (3.60, 20), (3.50, 10), (3.30, 0))


def percent(volts):
    if volts >= _CURVE[0][0]:
        return 100
    for (v1, p1), (v2, p2) in zip(_CURVE, _CURVE[1:]):
        if volts >= v2:
            return int(p2 + (p1 - p2) * (volts - v2) / (v1 - v2))
    return 0


def battery_volts(hw):
    """Battery voltage via a resistor divider on hw['bat_adc'], or None if not wired."""
    pin = hw.get("bat_adc")
    if pin is None:
        return None
    try:
        adc = machine.ADC(Pin(pin), atten=machine.ADC.ATTN_11DB)
        time.sleep_ms(20)
        total = 0
        for _ in range(16):
            total += adc.read_uv()
        uv = total / 16
        return uv / 1000000 * hw.get("bat_divider", 2.0)
    except Exception:
        return None


def battery_percent(hw):
    v = battery_volts(hw)
    return None if v is None else percent(v)


class Buttons:
    """One or two active-low buttons (external pull-up recommended, see README)."""

    def __init__(self, hw):
        self.pins = {}
        for name in ("btn_next", "btn_prev"):
            n = hw.get(name)
            if n is not None:
                self.pins[name] = Pin(n, Pin.IN, Pin.PULL_UP)

    def gpio_numbers(self):
        return {name: pin for name, pin in self.pins.items()}

    def pressed(self, name):
        pin = self.pins.get(name)
        return pin is not None and pin.value() == 0

    def any_pressed(self):
        for pin in self.pins.values():
            if pin.value() == 0:
                return True
        return False

    def which_woke(self, hw):
        """Name of the button that woke us from deep sleep (best effort)."""
        try:
            woke = machine.wake_pins()
        except Exception:
            woke = ()
        for name in ("btn_next", "btn_prev"):
            if hw.get(name) is not None and hw[name] in woke:
                return name
        for name in self.pins:  # fall back to whatever is held right now
            if self.pressed(name):
                return name
        return "btn_next"

    def hold_ms(self, name, limit_ms):
        """How long `name` stays down (0 if it was already released), capped at limit_ms."""
        pin = self.pins.get(name)
        if pin is None:
            return 0
        t0 = time.ticks_ms()
        while pin.value() == 0:
            dt = time.ticks_diff(time.ticks_ms(), t0)
            if dt >= limit_ms:
                return dt
            time.sleep_ms(10)
        return time.ticks_diff(time.ticks_ms(), t0)

    def wait_release(self, timeout_ms=15000):
        """Block until all buttons are up (debounced). False on timeout (stuck button)."""
        t0 = time.ticks_ms()
        up_since = None
        while True:
            if self.any_pressed():
                up_since = None
            else:
                if up_since is None:
                    up_since = time.ticks_ms()
                if time.ticks_diff(time.ticks_ms(), up_since) > 40:
                    return True
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
            time.sleep_ms(10)


def go_to_sleep(cfg, buttons, buttons_free=True):
    """Deep sleep until a button is pressed (or the auto-rotate timer fires)."""
    dev = cfg["device"]
    ms = int(dev.get("auto_rotate_min", 0) * 60000) or None
    if dev.get("sleep") == "none":
        while True:  # development mode: keep USB/REPL alive
            time.sleep(1)
    if buttons_free:
        import esp32
        pins = [p for p in buttons.pins.values()]
        if pins:
            esp32.wake_on_gpio(pins, esp32.WAKEUP_ALL_LOW)
    elif ms is None:
        ms = 3600000  # stuck button: don't wake on it, check again in an hour
    if ms:
        machine.deepsleep(ms)
    machine.deepsleep()
