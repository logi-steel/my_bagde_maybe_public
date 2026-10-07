"""Run under MicroPython by test_portal.py: portal + simulated panel on localhost.

usage: micropython tests/portal_server.py <port> <dns_port> [normal|idle|button]
Prints "READY <root> <ssid> <password>"; on exit dumps the panel to <root>/dump.json.
"""
import sys
import json
import binascii
import machine
from machine import Pin
from helpers import fresh_root
from ssd1680_sim import SSD1680Sim
from badge import util, config, portal, power
from badge.state import State

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

port, dns_port = int(sys.argv[1]), int(sys.argv[2])
mode = sys.argv[3] if len(sys.argv) > 3 else "normal"

root = fresh_root()
for n in (5, 6, 7, 2, 3):
    Pin(n)
Pin.registry[3]._v = 1
sim = SSD1680Sim(dc=6, cs=5, rst=7, busy=2)
power.battery_percent = lambda hw: 73

cfg, _ = config.load()
if mode == "idle":
    cfg["device"]["portal"]["timeout_s"] = 1
ssid, pw = portal.make_creds(cfg)
btn = power.Buttons(cfg["hardware"])
p = portal.Portal(cfg, State(), btn, ssid, pw, "192.168.4.1", port=port, dns_port=dns_port)
p.show_screen()


async def main():
    task = asyncio.create_task(p.serve())
    while not p.ready:           # listen first, announce second (no connect-before-listen race)
        await asyncio.sleep_ms(10)
    await asyncio.sleep_ms(50)   # let the DNS task bind too
    print("READY", root, ssid, pw)
    sys.stdout.flush()
    if mode == "button":
        await asyncio.sleep_ms(1200)
        Pin.registry[3]._v = 0
    await task


asyncio.run(main())
with open(root + "/dump.json", "w") as f:
    json.dump({"modes": [r[0] for r in sim.refreshes],
               "screen": binascii.hexlify(sim.screen).decode(),
               "errors": sim.errors}, f)
print("EXIT")
