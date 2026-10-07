"""Battery curve + ADC path + button helpers."""
import machine
from machine import Pin
from badge import power

# percent(): anchors, monotonic, clamped
assert power.percent(4.35) == 100 and power.percent(4.20) == 100
assert power.percent(3.80) == 50
assert power.percent(3.30) == 0 and power.percent(2.9) == 0
prev = -1
for mv in range(3000, 4300, 10):
    p = power.percent(mv / 1000)
    assert p >= prev, (mv, p, prev)
    prev = p
print("battery curve ok")

# ADC path: mock reads 1.9 V at the pin, divider 2:1 -> 3.8 V -> 50 %
hw = {"bat_adc": 4, "bat_divider": 2.0}
assert abs(power.battery_volts(hw) - 3.8) < 0.001
assert power.battery_percent(hw) == 50
assert power.battery_volts({"bat_adc": None}) is None, "not wired -> no reading (no random %)"
assert power.battery_percent({}) is None
print("adc path ok")

# buttons: pressed / hold_ms / wait_release with the mock pin
b = power.Buttons({"btn_next": 3, "btn_prev": None})
assert list(b.pins) == ["btn_next"]
Pin.registry[3]._v = 1
assert not b.pressed("btn_next") and b.hold_ms("btn_next", 500) == 0
Pin.registry[3]._v = 0
assert b.pressed("btn_next") and b.hold_ms("btn_next", 60) >= 60
assert b.wait_release(timeout_ms=80) is False, "a held button times out instead of blocking forever"
Pin.registry[3]._v = 1
assert b.wait_release(timeout_ms=500) is True
machine.set_boot(machine.DEEPSLEEP_RESET, 7, (3,))
assert b.which_woke({"btn_next": 3, "btn_prev": None}) == "btn_next"
print("buttons ok")
print("test_power: OK")
