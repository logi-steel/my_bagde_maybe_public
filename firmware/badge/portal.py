"""Wi-Fi config portal: access point + tiny HTTP server (asyncio) + DNS catch-all.

Long-press the button -> the e-paper shows a QR code that joins the badge's Wi-Fi, open
http://192.168.4.1 (most phones pop it up by themselves) and edit config, code, fonts,
images from the browser. Everything is checked before it is written:
  * config.json is parsed + validated (a typo can't brick the badge)
  * .py files must compile, .json files must parse
  * the previous version is kept as <file>.bak (restore button in the UI)
"""
import os
import sys
import gc
import json
import time
import binascii
import machine
import network

try:
    import asyncio
except ImportError:  # MicroPython < 1.21
    import uasyncio as asyncio

from . import util, config, layout, power, VERSION
from .canvas import Canvas, BLACK

MAX_JSON = 24 * 1024
MAX_UPLOAD = 96 * 1024
MAX_PY = 40 * 1024
ALLOWED_EXT = (".py", ".json", ".fnt", ".pbm", ".txt", ".md", ".html", ".css", ".js")
PROTECTED = ("/main.py", "/boot.py", "/recover.py")
_ALPHA = "abcdefghjkmnpqrstuvwxyz23456789"

_REASONS = {200: "OK", 204: "No Content", 400: "Bad Request", 404: "Not Found",
            405: "Method Not Allowed", 413: "Payload Too Large", 500: "Internal Server Error",
            507: "Insufficient Storage"}
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
          ".json": "application/json", ".txt": "text/plain; charset=utf-8",
          ".py": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}


class HTTPError(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg


# -- small helpers ---------------------------------------------------------------
def unquote(s):
    raw = s.replace("+", " ").encode()
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == 37 and i + 2 < n:
            try:
                out.append(int(raw[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(c)
        i += 1
    return out.decode()


def parse_query(q):
    res = {}
    for part in q.split("&"):
        if part:
            k, _, v = part.partition("=")
            res[unquote(k)] = unquote(v)
    return res


def norm_path(p):
    p = unquote(p).strip()
    parts = [x for x in p.split("/") if x]
    if not parts:
        raise HTTPError(400, "empty path")
    for x in parts:
        if x in (".", ".."):
            raise HTTPError(400, "bad path")
        for ch in x:
            if not (ch.isalpha() or ch.isdigit() or ch in "._-"):
                raise HTTPError(400, "bad character %r in path" % ch)
    path = "/" + "/".join(parts)
    if len(path) > 80:
        raise HTTPError(400, "path too long")
    return path


def make_creds(cfg):
    pc = cfg["device"].get("portal", {})
    uid = machine.unique_id()
    ssid = pc.get("ssid") or "BADGE-%02X%02X" % (uid[-2], uid[-1])
    pw = pc.get("password") or ""
    if len(pw) < 8:
        pw = "".join(_ALPHA[b % len(_ALPHA)] for b in os.urandom(8))
    return ssid, pw


def _wifi_escape(s):
    for ch in "\\;,:\"":
        s = s.replace(ch, "\\" + ch)
    return s


def start_ap(ssid, pw):
    ap = network.WLAN(getattr(network.WLAN, "IF_AP", getattr(network, "AP_IF", 1)))
    sec = getattr(network.WLAN, "SEC_WPA2", getattr(network, "AUTH_WPA2_PSK", 3))
    ap.config(ssid=ssid, password=pw, security=sec, max_clients=4)
    ap.active(True)
    return ap


class Portal:
    def __init__(self, cfg, st, btn, ssid, pw, ip, port=None, dns_port=None):
        self.cfg = cfg
        self.st = st
        self.btn = btn
        self.ssid, self.pw, self.ip = ssid, pw, ip
        pc = cfg["device"].get("portal", {})
        self.port = port or pc.get("port", 80)
        self.dns_port = dns_port if dns_port is not None else pc.get("dns_port", 53)
        self.timeout_s = pc.get("timeout_s", 300)
        self.last = time.ticks_ms()
        self.stop = False
        self.ready = False   # True once the server is listening
        self.t0 = time.ticks_ms()

    # -- e-paper screen with the join QR ----------------------------------------
    def show_screen(self):
        from . import app
        from .state import State
        wifi = "WIFI:T:WPA;S:%s;P:%s;;" % (_wifi_escape(self.ssid), _wifi_escape(self.pw))
        rot = self.cfg["device"]["rotation"]
        if rot in (0, 180):
            items = [
                {"type": "qr", "data": wifi, "x": 6, "y": 11, "scale": 3, "ecc": "M"},
                {"type": "text", "text": "Wi-Fi portal", "x": 114, "y": 4, "font": "b16"},
                {"type": "text", "text": "{ssid}", "x": 114, "y": 26, "font": "b16"},
                {"type": "text", "text": "pass: {pw}", "x": 114, "y": 48, "font": "s16"},
                {"type": "text", "text": "http://{ip}", "x": 114, "y": 72, "font": "s12"},
                {"type": "text", "text": "scan = join Wi-Fi", "x": 114, "y": 88, "font": "s12"},
                {"type": "text", "text": "button = quit", "x": 114, "y": 104, "font": "s12"},
            ]
        else:
            items = [
                {"type": "qr", "data": wifi, "x": 11, "y": 4, "scale": 3, "ecc": "M"},
                {"type": "text", "text": "Wi-Fi portal", "x": 4, "y": 112, "font": "b16"},
                {"type": "text", "text": "{ssid}", "x": 4, "y": 136, "font": "b16"},
                {"type": "text", "text": "pass:", "x": 4, "y": 162, "font": "s16"},
                {"type": "text", "text": "{pw}", "x": 4, "y": 182, "font": "b16"},
                {"type": "text", "text": "http://{ip}", "x": 4, "y": 208, "font": "s12"},
                {"type": "text", "text": "button = quit", "x": 4, "y": 228, "font": "s12"},
            ]
        pcfg = config._merge(config.DEFAULTS, {})
        pcfg["device"]["rotation"] = rot
        pcfg["hardware"] = self.cfg["hardware"]
        pcfg["vars"] = {"ssid": self.ssid, "pw": self.pw, "ip": self.ip}
        pcfg["pages"] = [{"items": items}]
        tmp = State()
        app.show(pcfg, tmp, True)
        self.st.panel_ok = tmp.panel_ok
        self.st.partials = 0

    # -- HTTP ---------------------------------------------------------------------
    async def _send(self, w, code, ctype, body=b"", extra=""):
        if isinstance(body, str):
            body = body.encode()
        head = "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n" \
               "Cache-Control: no-store\r\n%s\r\n" % (code, _REASONS.get(code, "OK"), ctype, len(body), extra)
        w.write(head.encode())
        if body:
            w.write(body)
        await w.drain()

    async def _json(self, w, obj, code=200):
        await self._send(w, code, "application/json", json.dumps(obj))

    async def _send_file(self, w, path, ctype):
        size = os.stat(util.p(path))[6]
        head = "HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n" \
               "Cache-Control: no-store\r\n\r\n" % (ctype, size)
        w.write(head.encode())
        with open(util.p(path), "rb") as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                w.write(chunk)
                await w.drain()

    async def handle(self, r, w):
        self.last = time.ticks_ms()
        try:
            try:
                await asyncio.wait_for(self._serve_one(r, w), 30)
            except HTTPError as e:
                await self._json(w, {"error": e.msg}, e.code)
            except Exception as e:  # never let one request kill the portal
                sys.print_exception(e)
                try:
                    await self._json(w, {"error": "%s: %s" % (type(e).__name__, e)}, 500)
                except Exception:
                    pass
        finally:
            try:
                w.close()
                await w.wait_closed()
            except Exception:
                pass
            gc.collect()
            self.last = time.ticks_ms()

    async def _serve_one(self, r, w):
        line = await r.readline()
        if not line:
            return
        parts = line.decode().split()
        if len(parts) < 2:
            raise HTTPError(400, "bad request line")
        method, target = parts[0], parts[1]
        headers = {}
        for _ in range(40):
            h = await r.readline()
            if h in (b"\r\n", b"\n", b""):
                break
            k, _, v = h.decode().partition(":")
            headers[k.strip().lower()] = v.strip()
        path, _, q = target.partition("?")
        query = parse_query(q)
        length = int(headers.get("content-length", "0") or 0)

        if path.startswith("/api/"):
            await self.api(method, path[5:], query, headers, length, r, w)
        elif method in ("GET", "HEAD"):
            # index for "/" and for every unknown host/path -> captive-portal pop-up works
            await self._send_file(w, "/web/index.html", _TYPES[".html"])
        else:
            raise HTTPError(405, "method not allowed")

    async def _body(self, r, length, limit=MAX_JSON):
        if length > limit:
            raise HTTPError(413, "body too large (max %d bytes)" % limit)
        return await r.readexactly(length) if length else b""

    # -- API ----------------------------------------------------------------------
    async def api(self, method, name, query, headers, length, r, w):
        if name == "status" and method == "GET":
            gc.collect()
            fs = (util.free_bytes(),)
            cfg, problem = config.load()
            return await self._json(w, {
                "version": VERSION, "heap_free": gc.mem_free(), "fs_free": fs[0],
                "battery": power.battery_percent(self.cfg["hardware"]),
                "page": self.st.page, "pages": len(cfg["pages"]),
                "rotation": cfg["device"]["rotation"], "ssid": self.ssid,
                "uptime_s": time.ticks_diff(time.ticks_ms(), self.t0) // 1000,
                "problem": problem, "impl": sys.implementation[0] + " " + ".".join(
                    str(x) for x in sys.implementation[1][:3])})
        if name == "config" and method == "GET":
            try:
                text = util.read_text(config.CONFIG)
            except OSError:
                text = json.dumps(config.DEFAULTS)
            return await self._send(w, 200, "application/json", text)
        if name == "config" and method == "PUT":
            text = (await self._body(r, length)).decode()
            try:
                warns = config.save_text(text)
            except ValueError as e:
                raise HTTPError(400, str(e))
            self.cfg, _ = config.load()
            return await self._json(w, {"ok": True, "warnings": warns})
        if name == "validate" and method == "POST":
            text = (await self._body(r, length)).decode()
            try:
                errs, warns = config.validate(config.parse(text))
            except ValueError as e:
                errs, warns = [str(e)], []
            return await self._json(w, {"errors": errs, "warnings": warns})
        if name == "preview" and method == "POST":
            return await self._preview(w, query, await self._body(r, length))
        if name == "show" and method == "POST":
            return await self._show(w, query, await self._body(r, length))
        if name == "files" and method == "GET":
            files = [{"p": p, "s": s} for p, s in util.walk("/") if not p.endswith(".tmp")]
            return await self._json(w, {"files": files, "free": util.free_bytes()})
        if name == "file":
            return await self._file(method, query, length, r, w)
        if name == "restore" and method == "POST":
            path = norm_path(query.get("path", ""))
            if not util.exists(path + ".bak"):
                raise HTTPError(404, "no backup for " + path)
            os.rename(util.p(path), util.p(path + ".swap")) if util.exists(path) else None
            os.rename(util.p(path + ".bak"), util.p(path))
            if util.exists(path + ".swap"):
                os.rename(util.p(path + ".swap"), util.p(path + ".bak"))
            if path == config.CONFIG:
                self.cfg, _ = config.load()
            return await self._json(w, {"ok": True})
        if name in ("exit", "reboot") and method == "POST":
            await self._json(w, {"ok": True})
            self.stop = True
            return
        raise HTTPError(404, "unknown API call")

    def _draft(self, body):
        if not body:
            return self.cfg
        try:
            cfg = config.parse(body.decode())
        except ValueError as e:
            raise HTTPError(400, str(e))
        errs, _ = config.validate(cfg)
        if errs:
            raise HTTPError(400, "; ".join(errs[:3]))
        return cfg

    async def _preview(self, w, query, body):
        cfg = self._draft(body)
        pages = max(1, len(cfg["pages"]))
        idx = int(query.get("page", "0")) % pages
        c = Canvas(cfg["device"]["rotation"])
        ctx = layout.render_page(c, cfg, idx, power.battery_percent(cfg["hardware"]),
                                 reload_plugins=True, log=False)
        raw = c.pbm()
        hdr = raw.index(b"\n", raw.index(b"\n") + 1) + 1
        await self._json(w, {"w": c.w, "h": c.h, "page": idx, "pages": pages,
                             "data": binascii.b2a_base64(raw[hdr:]).decode().strip(),
                             "errors": ctx.errors[:6]})

    async def _show(self, w, query, body):
        from . import app
        cfg = self._draft(body)
        pages = max(1, len(cfg["pages"]))
        self.st.page = int(query.get("page", "0")) % pages
        if query.get("full") == "1":
            self.st.panel_ok = False
        ctx = app.show(cfg, self.st, False)
        await self._json(w, {"ok": True, "errors": ctx.errors[:6] if ctx else []})

    async def _file(self, method, query, length, r, w):
        path = norm_path(query.get("path", ""))
        if method == "GET":
            if not util.exists(path) or util.is_dir(path):
                raise HTTPError(404, "no such file")
            ext = path[path.rfind("."):] if "." in path else ""
            return await self._send_file(w, path, _TYPES.get(ext, "application/octet-stream"))
        if method == "DELETE":
            if path in PROTECTED:
                raise HTTPError(400, path + " is protected")
            if not util.exists(path):
                raise HTTPError(404, "no such file")
            util.remove(path)
            return await self._json(w, {"ok": True})
        if method != "PUT":
            raise HTTPError(405, "method not allowed")
        ext = path[path.rfind("."):] if "." in path else ""
        if ext not in ALLOWED_EXT:
            raise HTTPError(400, "allowed file types: " + " ".join(ALLOWED_EXT))
        limit = MAX_PY if ext == ".py" else MAX_UPLOAD
        if length > limit:
            raise HTTPError(413, "%s files are limited to %d bytes" % (ext, limit))
        if length + 16384 > util.free_bytes():
            raise HTTPError(507, "not enough flash space")
        util.makedirs(util.parent(path))
        tmp = path + ".tmp"
        left = length
        try:
            with open(util.p(tmp), "wb") as f:
                while left:
                    chunk = await r.readexactly(min(1024, left))
                    f.write(chunk)
                    left -= len(chunk)
            self._verify(path, tmp, ext)
        except Exception:
            util.remove(tmp)
            raise
        util.commit(tmp, path, path + ".bak" if ext in (".py", ".json") else None)
        if path == config.CONFIG:
            self.cfg, _ = config.load()
        await self._json(w, {"ok": True, "size": length})

    def _verify(self, path, tmp, ext):
        gc.collect()
        try:
            if ext == ".py":
                with open(util.p(tmp)) as f:
                    src = f.read()
                compile(src, path, "exec")
            elif path == config.CONFIG:
                errs, _ = config.validate(config.parse(util.read_text(tmp)))
                if errs:
                    raise ValueError("; ".join(errs[:3]))
            elif ext == ".json":
                with open(util.p(tmp)) as f:
                    json.load(f)
        except MemoryError:
            raise HTTPError(413, "file too big to verify in RAM")
        except (SyntaxError, ValueError, UnicodeError) as e:
            raise HTTPError(400, "%s: %s" % (type(e).__name__, e))

    # -- DNS catch-all (so phones open the portal automatically) ---------------------
    async def _dns(self):
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setblocking(False)
            s.bind(socket.getaddrinfo("0.0.0.0", self.dns_port)[0][-1])  # portable across ports
        except Exception as e:
            print("dns disabled:", e)
            return
        ip = bytes(int(x) for x in self.ip.split("."))
        try:
            while not self.stop:
                try:
                    data, addr = s.recvfrom(256)
                except OSError:
                    await asyncio.sleep_ms(30)
                    continue
                try:
                    if len(data) < 17:
                        continue
                    end = 12
                    while data[end] != 0:
                        end += data[end] + 1
                    end += 5
                    is_a = data[end - 4:end - 2] == b"\x00\x01"
                    resp = data[:2] + b"\x81\x80" + data[4:6] + (b"\x00\x01" if is_a else b"\x00\x00") \
                        + b"\x00\x00\x00\x00" + data[12:end]
                    if is_a:
                        resp += b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + ip
                    s.sendto(resp, addr)
                except Exception:
                    pass
        finally:
            s.close()

    async def serve(self):
        server = await asyncio.start_server(self.handle, "0.0.0.0", self.port)
        asyncio.create_task(self._dns())
        self.ready = True
        armed = False
        while not self.stop:
            await asyncio.sleep_ms(200)
            idle = time.ticks_diff(time.ticks_ms(), self.last)
            if idle > self.timeout_s * 1000:
                break
            if self.btn is not None:
                if not self.btn.any_pressed():
                    armed = True          # released after the long press that opened us
                elif armed:
                    break                 # pressed again -> quit
        self.stop = True
        server.close()
        await server.wait_closed()
        await asyncio.sleep_ms(100)


def run(cfg, st, btn):
    ssid, pw = make_creds(cfg)
    ap = start_ap(ssid, pw)
    ip = ap.ifconfig()[0]
    p = Portal(cfg, st, btn, ssid, pw, ip)
    try:
        p.show_screen()
    except Exception as e:
        layout._log("portal screen: %s" % e)
    asyncio.run(p.serve())
    try:
        ap.active(False)
    except Exception:
        pass
