"""Safety net for over-the-air updates. Lives outside the badge/ package on purpose:
it must still work when badge/*.py is broken.

If the firmware fails to start right after an upload, swap every badge/*.py back to its
.bak version once (the broken version stays as .bak so nothing is lost) and reboot.
"""
import os
import machine

ROOT = ""
FLAG = "/rollback.flag"
LOG = "/error.log"


def _exists(path):
    try:
        os.stat(ROOT + path)
        return True
    except OSError:
        return False


def log(text):
    try:
        size = os.stat(ROOT + LOG)[6] if _exists(LOG) else 0
        with open(ROOT + LOG, "a" if size < 4096 else "w") as f:
            f.write(text + "\n")
    except Exception:
        pass


def swap_backups():
    """badge/x.py <-> badge/x.py.bak for every backup that exists. Returns how many."""
    n = 0
    try:
        names = os.listdir(ROOT + "/badge")
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".py.bak"):
            continue
        bak = "/badge/" + name
        cur = bak[:-4]
        tmp = cur + ".swap"
        try:
            if _exists(cur):
                os.rename(ROOT + cur, ROOT + tmp)
            os.rename(ROOT + bak, ROOT + cur)
            if _exists(tmp):
                os.rename(ROOT + tmp, ROOT + bak)  # the broken version stays reachable as .bak
            n += 1
        except OSError:
            pass
    return n


def rollback_once():
    """True if backups were swapped in (caller should reset). Only once per failure streak."""
    if _exists(FLAG):
        return False
    if swap_backups() == 0:
        return False
    try:
        with open(ROOT + FLAG, "w") as f:
            f.write("1")
    except OSError:
        pass
    return True


def clear_flag():
    """Called by the firmware once it got far enough to be considered healthy."""
    try:
        os.remove(ROOT + FLAG)
    except OSError:
        pass


def handle(exc):
    """Called from main.py when starting the badge raised."""
    try:
        import sys
        import io
        buf = io.StringIO()
        sys.print_exception(exc, buf)
        log(buf.getvalue())
    except Exception:
        log("boot failure: %r" % (exc,))
    if rollback_once():
        log("rolled back to the previous firmware files")
        machine.reset()
    try:
        import badge.app as app
        app.rescue(exc)
    except Exception as e:
        log("rescue failed: %r" % (e,))
    machine.deepsleep(3600000)
