# cpython
"""Portal Image tab in a real browser: pick a picture -> Full screen -> Upload & add as a page.

Needs playwright + chromium; without them the test says so and passes (the rest of the suite does not need a browser).
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV = dict(os.environ, MICROPYPATH=os.pathsep.join([ROOT + "/firmware", ROOT + "/tests/mocks", ROOT + "/tests",
                                                    ROOT + "/tests/.hostlib"]))
PORT, DNS = 18990, 15990

try:
    from playwright.sync_api import sync_playwright
    from PIL import Image, ImageDraw
except ImportError as e:
    print("skip: no browser tooling (%s)" % e)
    sys.exit(0)


def expect(cond, msg):
    if not cond:
        raise SystemExit("FAIL: " + msg)
    print("ok:", msg)


def start():
    p = subprocess.Popen(["micropython", ROOT + "/tests/portal_server.py", str(PORT), str(DNS), "normal"],
                         cwd=ROOT, env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    t0, line = time.time(), ""
    while time.time() - t0 < 20:
        line = p.stdout.readline()
        if line.startswith("READY"):
            return p, line.split()[1]
        if not line and p.poll() is not None:
            break
    p.kill()
    raise SystemExit("server did not start: " + line)


def launch(pw):
    try:
        return pw.chromium.launch()
    except Exception as first:
        for d in sorted(os.listdir(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
                        if os.path.isdir(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")) else []):
            for sub in ("chrome-linux/chrome", "chrome-linux/headless_shell"):
                exe = os.path.join(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"), d, sub)
                if os.path.exists(exe):
                    try:
                        return pw.chromium.launch(executable_path=exe)
                    except Exception:
                        pass
        print("skip: no usable chromium (%s)" % str(first).splitlines()[0])
        sys.exit(0)


def pbm_size(data):
    parts = data.split(b"\n", 2)
    w, h = map(int, parts[1].split())
    return parts[0], w, h, parts[2]


proc, root = start()
tmp = tempfile.mkdtemp()
try:
    # a "Canva export": 1000 x 488, white background, one black block, some text
    pic = os.path.join(tmp, "design.png")
    im = Image.new("RGB", (1000, 488), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([60, 60, 440, 420], fill="black")
    d.rectangle([520, 100, 940, 160], fill="black")
    im.save(pic)

    with sync_playwright() as pw:
        br = launch(pw)
        pg = br.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto("http://127.0.0.1:%d/" % PORT)
        pg.click("#tb-image")
        expect(pg.is_disabled("#iadd"), "'Upload & add' is disabled until a picture is chosen")
        pg.set_input_files("#imgin", pic)
        pg.click("#ifull")
        pg.wait_for_function("!document.getElementById('iadd').disabled")
        expect(pg.input_value("#iw") == "250", "Full screen sets the width to 250 (landscape)")
        expect(pg.evaluate("[icv.width, icv.height]") == [250, 122], "converted picture is 250 x 122")

        pg.fill("#iname", "mycat")
        pg.dispatch_event("#iname", "input")
        pg.wait_for_function("!document.getElementById('iadd').disabled")
        n_before = len(json.loads(pg.evaluate("fetch('/api/config').then(r=>r.text())"))["pages"])
        pg.click("#iadd")
        pg.wait_for_function("document.getElementById('t-preview').classList.contains('on')")
        pg.wait_for_function("document.getElementById('msg').textContent.startsWith('added')")

        cfg = json.loads(pg.evaluate("fetch('/api/config').then(r=>r.text())"))
        hits = [p for p in cfg["pages"] if any(it.get("type") == "image" and it.get("src") == "img/mycat.pbm"
                                               for it in p.get("items", []))]
        expect(len(cfg["pages"]) == n_before + 1 and len(hits) == 1, "the page was added to the config exactly once")
        expect(hits[0]["items"][0].get("x") == 0 and hits[0]["items"][0].get("y") == 0, "image placed at 0,0")

        raw = pg.evaluate("""fetch('/api/file?path=/img/mycat.pbm').then(r=>r.arrayBuffer())
                             .then(b=>Array.from(new Uint8Array(b)))""")
        magic, w, h, body = pbm_size(bytes(raw))
        expect((magic, w, h) == (b"P4", 250, 122) and len(body) == 32 * 122, "uploaded /img/mycat.pbm is a 250x122 P4")
        ink = sum(bin(b).count("1") for b in body)
        expect(0.15 < ink / (250 * 122) < 0.45, "the black blocks arrived as ink (%.0f%%)" % (100 * ink / (250 * 122)))

        pg.click("#tb-image")
        pg.click("#iadd")
        pg.wait_for_function("document.getElementById('msg').textContent.startsWith('updated')")
        cfg2 = json.loads(pg.evaluate("fetch('/api/config').then(r=>r.text())"))
        expect(len(cfg2["pages"]) == len(cfg["pages"]), "uploading the same name again updates, it does not duplicate")

        pg.wait_for_timeout(300)
        expect(not errors, "no JavaScript errors (%s)" % errors)
        br.close()
finally:
    proc.kill()
print("ALL OK")
