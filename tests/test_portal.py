# cpython
"""Portal end to end: real HTTP + DNS against the firmware running under MicroPython."""
import base64
import http.client
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

import cv2
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV = dict(os.environ, MICROPYPATH=os.pathsep.join([ROOT + "/firmware", ROOT + "/tests/mocks", ROOT + "/tests",
                                                    ROOT + "/tests/.hostlib"]))
PORT, DNS = 18765, 15353


def start(mode="normal", port=PORT, dns=DNS):
    p = subprocess.Popen(["micropython", ROOT + "/tests/portal_server.py", str(port), str(dns), mode],
                         cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0 = time.time()
    line = ""
    while time.time() - t0 < 20:
        line = p.stdout.readline()
        if line.startswith("READY"):
            _, root, ssid, pw = line.split()
            return p, root, ssid, pw
        if not line and p.poll() is not None:
            break
    p.kill()
    raise SystemExit("server did not start: " + line + (p.stdout.read() or ""))


def call(method, path, body=None, port=PORT):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    if isinstance(body, str):
        body = body.encode()
    c.request(method, path, body=body)
    r = c.getresponse()
    data = r.read()
    c.close()
    ctype = r.getheader("content-type", "")
    return r.status, (json.loads(data) if "json" in ctype and data else data)


def expect(cond, msg):
    if not cond:
        raise SystemExit("FAIL: " + msg)
    print("ok:", msg)


proc, root, ssid, pw = start()
try:
    # -- pages + captive portal behaviour ------------------------------------------------
    st, html = call("GET", "/")
    expect(st == 200 and b"Badge portal" in html, "GET / serves the UI")
    st, html2 = call("GET", "/generate_204")
    expect(st == 200 and html2 == html, "unknown paths serve the UI (captive portal pop-up)")
    st, s = call("GET", "/api/status")
    expect(st == 200 and s["battery"] == 73 and s["pages"] == 4 and s["ssid"] == ssid, "status: %s" % s["impl"])

    # -- config: read / save / validation / backup ------------------------------------------
    st, text = call("GET", "/api/config")
    cfg = text  # already decoded (application/json)
    expect(cfg["vars"]["name"] == "Logi", "GET config")
    cfg["vars"]["name"] = "Zed"
    st, r = call("PUT", "/api/config", json.dumps(cfg))
    expect(st == 200 and r["ok"], "PUT valid config")
    st, files = call("GET", "/api/files")
    names = {f["p"] for f in files["files"]}
    expect("/config.json.bak" in names and "/config.json" in names, "previous config kept as backup")
    st, r = call("PUT", "/api/config", "{ nope")
    expect(st == 400 and "invalid JSON" in r["error"], "broken JSON rejected: %s" % r["error"][:40])
    st, r = call("PUT", "/api/config", json.dumps({"pages": [{"items": [{"type": "wat"}]}]}))
    expect(st == 400 and "unknown type" in r["error"], "invalid widget rejected")
    st, text = call("GET", "/api/config")
    expect(text["vars"]["name"] == "Zed", "rejected saves did not touch the stored config")
    st, r = call("PUT", "/api/config", b" " * (30 * 1024))
    expect(st == 413, "oversized config body -> 413")
    st, r = call("POST", "/api/restore?path=/config.json")
    st, text = call("GET", "/api/config")
    expect(text["vars"]["name"] == "Logi", "restore swaps config.json with its backup")

    # -- preview: rendered by the firmware itself --------------------------------------------
    st, pv = call("POST", "/api/preview?page=1")
    expect(st == 200 and pv["w"] == 250 and pv["h"] == 122 and pv["pages"] == 4 and not pv["errors"], "preview page 2")
    ref = subprocess.run(["micropython", ROOT + "/tools/render_pages.py", ROOT + "/firmware",
                          ROOT + "/firmware/config.json", tempfile.mkdtemp()], capture_output=True, text=True,
                         env=ENV, cwd=ROOT)
    st, pv_draft = call("POST", "/api/preview?page=0", json.dumps({"vars": {"name": "DRAFT"}, "pages": [
        {"items": [{"type": "text", "text": "{name}", "x": 4, "y": 4, "font": "b36"}]}]}))
    st, pv_other = call("POST", "/api/preview?page=0", json.dumps({"vars": {"name": "OTHER"}, "pages": [
        {"items": [{"type": "text", "text": "{name}", "x": 4, "y": 4, "font": "b36"}]}]}))
    expect(pv_draft["data"] != pv_other["data"], "preview renders unsaved draft configs")
    st, bad = call("POST", "/api/preview", json.dumps({"pages": [{"items": [{"type": "x"}]}]}))
    expect(st == 400, "invalid draft -> 400")

    # -- the e-paper shows the join QR for exactly these credentials ---------------------------
    # (decoded below from the dumped panel; first check the live 'show' call)
    st, r = call("POST", "/api/show?page=2")
    expect(st == 200 and r["ok"], "show page on the e-paper")

    # -- code in flight: upload a plugin, use it, change it, roll back ------------------------------
    plug_v1 = "def draw(c, item, ctx):\n    ctx.font('b36').draw(c, 'V1', 10, 10)\n"
    plug_v2 = "def draw(c, item, ctx):\n    ctx.font('b36').draw(c, 'V2', 10, 10)\n"
    draft = json.dumps({"pages": [{"items": [{"type": "plugin", "name": "hello", "x": 0, "y": 0}]}]})
    st, r = call("PUT", "/api/file?path=/plugins/hello.py", plug_v1)
    expect(st == 200, "upload plugin")
    st, a = call("POST", "/api/preview?page=0", draft)
    expect(st == 200 and not a["errors"], "preview uses the uploaded plugin")
    st, r = call("PUT", "/api/file?path=/plugins/hello.py", plug_v2)
    st, b = call("POST", "/api/preview?page=0", draft)
    expect(a["data"] != b["data"], "edited plugin takes effect immediately (hot reload)")
    st, r = call("POST", "/api/restore?path=/plugins/hello.py")
    st, c = call("POST", "/api/preview?page=0", draft)
    expect(c["data"] == a["data"], "restore brings back the previous plugin version")
    st, r = call("PUT", "/api/file?path=/plugins/hello.py", "def draw(c, item, ctx)\n    pass\n")
    expect(st == 400 and "SyntaxError" in r["error"], "syntax error rejected before writing: %s" % r["error"][:30])
    st, got = call("GET", "/api/file?path=/plugins/hello.py")
    expect(got.decode() == plug_v1, "failed upload left the working file untouched")
    st, files = call("GET", "/api/files")
    expect(not any(f["p"].endswith(".tmp") for f in files["files"]), "no .tmp leftovers")

    # -- upload safety --------------------------------------------------------------------------------
    for path, why in (("/../evil.py", "traversal"), ("/plugins/..%2F..%2Fx.py", "encoded traversal"),
                      ("/plugins/a%20b.py", "space in name"), ("/x.exe", "extension")):
        st, r = call("PUT", "/api/file?path=" + path, "x=1")
        expect(st == 400, "rejected %s (%s)" % (path, why))
    st, r = call("PUT", "/api/file?path=/big.py", b"#" * (41 * 1024))
    expect(st == 413, ".py over the size limit -> 413")
    st, r = call("DELETE", "/api/file?path=/main.py")
    expect(st == 400, "main.py cannot be deleted")
    st, r = call("PUT", "/api/file?path=/img/test.pbm", b"P4\n8 1\n\xff")
    expect(st == 200, "binary upload (pbm)")
    st, r = call("DELETE", "/api/file?path=/img/test.pbm")
    st, r = call("GET", "/api/file?path=/img/test.pbm")
    expect(st == 404, "delete + 404 afterwards")

    # -- several clients at once ---------------------------------------------------------------------------
    results = []
    def worker():
        results.append(call("GET", "/api/status")[0])
    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    expect(results == [200] * 6, "6 parallel clients served")

    # -- DNS catch-all ----------------------------------------------------------------------------------------
    def dns_query(name, qtype):
        q = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
        q += b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\x00" + struct.pack(">HH", qtype, 1)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        s.sendto(q, ("127.0.0.1", DNS))
        d, _ = s.recvfrom(512)
        s.close()
        return d
    a = dns_query("connectivitycheck.gstatic.com", 1)
    expect(a[:2] == b"\x12\x34" and struct.unpack(">H", a[6:8])[0] == 1 and a[-4:] == bytes([192, 168, 4, 1]),
           "DNS answers every A query with the portal IP")
    aaaa = dns_query("example.com", 28)
    expect(struct.unpack(">H", aaaa[6:8])[0] == 0, "AAAA gets an empty answer (clients fall back to A)")

    # -- clean shutdown ------------------------------------------------------------------------------------------
    st, r = call("POST", "/api/exit")
    out, _ = proc.communicate(timeout=10)
    expect(proc.returncode == 0 and "EXIT" in out, "portal exits on /api/exit")
    dump = json.load(open(os.path.join(root, "dump.json")))
    expect(dump["modes"][0] == 0xF7 and dump["errors"] == [], "panel: first a full refresh, no driver errors")
    expect(0xFF in dump["modes"], "panel: 'show' used a partial refresh")

    # -- decode the join-QR from the simulated panel pixels -----------------------------------------------------------
    # native (nx, ny) = (y, 249 - x) for rotation 0; the portal screen was the first (full) refresh
finally:
    if proc.poll() is None:
        proc.kill()

# the dump holds the LAST screen; rerun a clean server to decode the portal screen itself
proc, root, ssid, pw = start()
try:
    call("POST", "/api/exit")
    proc.communicate(timeout=10)
    dump = json.load(open(os.path.join(root, "dump.json")))
    screen = bytes.fromhex(dump["screen"])
    img = np.ones((122, 250), np.uint8) * 255
    for y in range(122):
        for x in range(250):
            nx, ny = y, 249 - x
            if not (screen[ny * 16 + (nx >> 3)] >> (7 - (nx & 7))) & 1:
                img[y, x] = 0
    qr = cv2.resize(img[0:122, 0:112], None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
    text, _, _ = cv2.QRCodeDetector().detectAndDecode(qr)
    expect(text == "WIFI:T:WPA;S:%s;P:%s;;" % (ssid, pw), "panel QR decodes to the Wi-Fi join string (%s)" % text)
finally:
    if proc.poll() is None:
        proc.kill()

# -- idle timeout and button-to-quit ------------------------------------------------------------------------------------
for mode in ("idle", "button"):
    proc, root, ssid, pw = start(mode, PORT + 1, DNS + 1)
    t0 = time.time()
    out, _ = proc.communicate(timeout=15)
    expect("EXIT" in out and proc.returncode == 0, "portal quits by itself (%s) after %.1fs" % (mode, time.time() - t0))
print("test_portal: OK")
