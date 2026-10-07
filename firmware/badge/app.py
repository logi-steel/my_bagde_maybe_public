"""Main flow: wake -> decide what to show -> draw -> refresh panel -> deep sleep."""
import gc
import time
import machine
from . import config, layout, power, util
from .canvas import Canvas
from .state import State


def classify(buttons):
    """Why are we running? "boot" (power-on/reset), "button" or "timer".

    machine.PIN_WAKE means EXT0 on MicroPython, which the ESP32-C3 lacks; GPIO wake has no
    named constant. wake_pins() is filled for GPIO wake, so use that.
    """
    if machine.reset_cause() != machine.DEEPSLEEP_RESET:
        return "boot"
    try:
        if machine.wake_pins():
            return "button"
    except Exception:
        pass
    if machine.wake_reason() == getattr(machine, "TIMER_WAKE", 4):
        return "timer"
    return "button" if buttons.any_pressed() else "timer"


def show(cfg, st, first):
    """Render the current page and push it to the panel. Returns the layout context."""
    dev, hw = cfg["device"], cfg["hardware"]
    gc.collect()
    bat = power.battery_percent(hw)
    if bat is not None:
        st.battery = bat
    canvas = Canvas(dev["rotation"])
    ctx = layout.render_page(canvas, cfg, st.page, bat)
    gc.collect()  # fonts/QR buffers are garbage now; the C3 heap is small
    from . import board
    epd = board.make_epd(hw)
    every = max(1, int(dev["full_refresh_every"]))
    full = first or not st.panel_ok or st.partials >= every - 1
    try:
        native = canvas.native()
        if full:
            epd.show_full(native)
            st.partials = 0
        else:
            epd.show_partial(native)
            st.partials += 1
        st.panel_ok = True
        epd.sleep()
    except OSError as e:  # panel missing / BUSY stuck: don't crash-loop, try full next time
        st.panel_ok = False
        layout._log("display: %s" % e)
    return ctx


def _healthy():
    """We got far enough: cancel a pending 'roll back after failed update' decision."""
    try:
        import recover
        recover.ROOT = util.ROOT
        recover.clear_flag()
    except ImportError:
        pass


def run():
    cfg, problem = config.load()
    dev, hw = cfg["device"], cfg["hardware"]
    st = State().load()
    st.crashes = 0
    btn = power.Buttons(hw)
    event = classify(btn)
    pages = max(1, len(cfg["pages"]))
    action = "show"
    if event == "boot":
        st.page, st.partials, st.panel_ok = 0, 0, False
    elif event == "timer":
        st.page = (st.page + 1) % pages
    else:
        name = btn.which_woke(hw)
        long_ms = int(dev["long_press_ms"])
        if btn.hold_ms(name, long_ms) >= long_ms:
            action = "portal"
        elif name == "btn_prev":
            st.page = (st.page - 1) % pages
        else:
            st.page = (st.page + 1) % pages
    if st.page >= pages:
        st.page = 0
    if action == "portal":
        st.save()
        from . import portal
        portal.run(cfg, st, btn)
        _healthy()
        machine.reset()
        return
    show(cfg, st, event == "boot")
    st.save()
    free = btn.wait_release()
    _healthy()  # a full cycle worked: this firmware is good (see recover.py)
    power.go_to_sleep(cfg, btn, free)


def rescue(exc):
    """Last resort after an unhandled error: log it, show it, sleep an hour (the button still wakes us)."""
    try:
        import sys
        import io
        buf = io.StringIO()
        sys.print_exception(exc, buf)
        layout._log(buf.getvalue())
    except Exception:
        pass
    st = State().load()
    st.crashes += 1
    st.save()
    try:
        cfg = config._merge(config.DEFAULTS, {})
        cfg["vars"]["error"] = "%s: %s" % (type(exc).__name__, exc)
        cfg["pages"] = [{"items": [
            {"type": "text", "text": "Badge crashed", "x": 4, "y": 4, "font": "b16"},
            {"type": "text", "text": "{error}", "x": 4, "y": 30, "w": 242, "font": "s12", "lines": 6},
            {"type": "text", "text": "Hold button 2s = Wi-Fi portal", "x": 4, "y": 104, "font": "s12"},
        ]}]
        show(cfg, st, True)
    except Exception:
        pass
    btn = None
    try:
        btn = power.Buttons(config.DEFAULTS["hardware"])
        btn.wait_release()
    except Exception:
        pass
    # sleep an hour (button still wakes us) instead of crash-looping and draining the battery
    try:
        import esp32
        if btn and btn.pins:
            esp32.wake_on_gpio(list(btn.pins.values()), esp32.WAKEUP_ALL_LOW)
    except Exception:
        pass
    machine.deepsleep(3600000)
