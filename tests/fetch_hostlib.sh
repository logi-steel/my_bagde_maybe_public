#!/bin/sh
# The apt MicroPython (unix port) ships without the pure-Python part of asyncio.
# Fetch it - same tag as the interpreter - into tests/.hostlib (git-ignored, test-only).
# Only needed for host tests; the real firmware has asyncio built in.
set -e
cd "$(dirname "$0")"
TAG="${MPY_TAG:-v1.22.1}"
mkdir -p .hostlib/asyncio
for f in __init__ core event funcs lock stream task; do
    [ -s ".hostlib/asyncio/$f.py" ] || curl -fsS -m 60 -o ".hostlib/asyncio/$f.py" \
        "https://raw.githubusercontent.com/micropython/micropython/$TAG/extmod/asyncio/$f.py"
done
