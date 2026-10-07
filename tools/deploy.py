#!/usr/bin/env python3
"""Copy the firmware/ tree to the badge over USB with mpremote.

  python3 tools/deploy.py                 # everything (first install)
  python3 tools/deploy.py --code-only     # code + web UI + fonts, keep your config.json, plugins and data
  python3 tools/deploy.py --port /dev/ttyACM0 --reset
  python3 tools/deploy.py --dry-run       # just print the mpremote command

Needs `pip install mpremote` and MicroPython already flashed (see README).
Tip: the badge sleeps most of the time and USB disappears while it does. Either press its
button and run this within a few seconds, or set "sleep": "none" in config.json while developing
(the badge then stays awake and the USB serial port stays up).
"""
import argparse
import os
import shlex
import shutil
import subprocess
import sys

FIRMWARE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "firmware"))
USER_OWNED = {"config.json", "plugins", "data", "img"}   # skipped with --code-only
SKIP = {"__pycache__", ".keep"}


def clean_pycache():
    """CPython may leave __pycache__ dirs in firmware/ - never ship those to the badge."""
    for dirpath, dirnames, _ in os.walk(FIRMWARE):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d))
                dirnames.remove(d)


def build_command(port, code_only, reset):
    clean_pycache()
    cmd = ["mpremote"] + (["connect", port] if port else [])
    first = True

    def add(*parts):
        nonlocal first
        if not first:
            cmd.append("+")
        first = False
        cmd.extend(parts)

    for name in sorted(os.listdir(FIRMWARE)):
        if name in SKIP or (code_only and name in USER_OWNED):
            continue
        path = os.path.join(FIRMWARE, name)
        if os.path.isdir(path):
            # destination ":" exists, so mpremote copies the directory *into* it
            add("fs", "cp", "-r", path, ":")
        else:
            add("fs", "cp", path, ":" + name)
    if reset:
        add("reset")
    return cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", help="serial port, e.g. /dev/ttyACM0 or COM5 (default: auto)")
    ap.add_argument("--code-only", action="store_true")
    ap.add_argument("--reset", action="store_true", help="hard-reset the badge afterwards")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cmd = build_command(a.port, a.code_only, a.reset)
    print(" ".join(shlex.quote(c) for c in cmd))
    if a.dry_run:
        return 0
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
