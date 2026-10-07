"""Host mock of `esp32`."""

WAKEUP_ALL_LOW = False
WAKEUP_ANY_HIGH = True

armed = {"pins": None, "level": None}


def wake_on_gpio(pins=None, level=WAKEUP_ALL_LOW):
    armed["pins"] = pins
    armed["level"] = level
