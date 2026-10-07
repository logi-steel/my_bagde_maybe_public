#!/bin/sh
# Host test runner: MicroPython (unix port) for firmware tests, CPython for tool tests.
# usage: tests/run.sh [name ...]   e.g. tests/run.sh display qr
cd "$(dirname "$0")/.." || exit 1
[ -s tests/.hostlib/asyncio/core.py ] || tests/fetch_hostlib.sh || echo "warning: could not fetch asyncio for host tests"
export MICROPYPATH="$PWD/firmware:$PWD/tests/mocks:$PWD/tests:$PWD/tests/.hostlib"
fail=0
names="$*"
[ -z "$names" ] && names=$(ls tests/test_*.py | sed 's#tests/test_##; s#\.py$##')
for n in $names; do
    f="tests/test_$n.py"
    echo "== $n"
    if grep -q '^# cpython' "$f"; then
        python3 -I "$f" || fail=1
    else
        micropython "$f" || fail=1
    fi
done
[ $fail -eq 0 ] && echo "ALL OK" || { echo "FAILED"; exit 1; }
