"""Loading, validating and saving /config.json (the whole badge is described by it)."""
import json
from . import util

CONFIG = "/config.json"
BACKUP = "/config.json.bak"

WIDGETS = ("text", "rect", "line", "circle", "image", "qr", "chips", "battery", "plugin")

DEFAULTS = {
    "version": 1,
    "device": {
        "rotation": 0,            # 0/180 landscape, 90/270 portrait; flip 0<->180 if upside down
        "sleep": "deep",          # "deep" (battery) or "none" (stay awake, for USB development)
        "full_refresh_every": 10,  # every Nth page change is a full (flashing) refresh
        "auto_rotate_min": 0,     # 0 = only change pages on button press
        "long_press_ms": 1200,    # hold the button this long to open the config portal
        "portal": {"timeout_s": 300, "ssid": "", "password": "", "port": 80},
    },
    "hardware": {                 # GPIO numbers, defaults = Seeed XIAO ESP32-C3 wiring from README
        "spi_id": 1, "sck": 8, "mosi": 10, "miso": 9,
        "cs": 5, "dc": 6, "rst": 7, "busy": 2,
        "btn_next": 3, "btn_prev": None,
        "bat_adc": 4, "bat_divider": 2.0,
    },
    "vars": {},
    "pages": [],
}

ERROR_PAGE = {
    "items": [
        {"type": "text", "text": "config.json problem", "x": 4, "y": 4, "font": "b16"},
        {"type": "text", "text": "{error}", "x": 4, "y": 30, "w": 242, "font": "s12", "lines": 6},
        {"type": "text", "text": "Hold button 2s = Wi-Fi portal", "x": 4, "y": 104, "font": "s12"},
    ]
}


def _merge(base, over):
    out = {}
    for k in base:
        if k in over and isinstance(base[k], dict) and isinstance(over[k], dict):
            out[k] = _merge(base[k], over[k])
        elif k in over:
            out[k] = over[k]
        else:
            b = base[k]
            out[k] = dict(b) if isinstance(b, dict) else (list(b) if isinstance(b, list) else b)
    for k in over:
        if k not in base:
            out[k] = over[k]
    return out


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(cfg):
    """Return (errors, warnings). Errors make a config unsafe to save."""
    errs, warns = [], []
    if not isinstance(cfg, dict):
        return ["top level must be a JSON object"], warns
    dev = cfg.get("device", {})
    if not isinstance(dev, dict):
        errs.append("device must be an object")
        dev = {}
    if dev.get("rotation", 0) not in (0, 90, 180, 270):
        errs.append("device.rotation must be 0, 90, 180 or 270")
    if dev.get("sleep", "deep") not in ("deep", "none"):
        errs.append('device.sleep must be "deep" or "none"')
    for k in ("full_refresh_every", "auto_rotate_min", "long_press_ms"):
        if k in dev and not _is_num(dev[k]):
            errs.append("device.%s must be a number" % k)
    hw = cfg.get("hardware", {})
    if not isinstance(hw, dict):
        errs.append("hardware must be an object")
        hw = {}
    for k, v in hw.items():
        if v is not None and not _is_num(v):
            errs.append("hardware.%s must be a number or null" % k)
    if dev.get("sleep", "deep") == "deep":
        for k in ("btn_next", "btn_prev"):
            if _is_num(hw.get(k)) and hw[k] > 5:
                warns.append("hardware.%s=%s: on ESP32-C3 only GPIO0-5 can wake from deep sleep" % (k, hw[k]))
    if not isinstance(cfg.get("vars", {}), dict):
        errs.append("vars must be an object")
    pages = cfg.get("pages", [])
    if not isinstance(pages, list):
        errs.append("pages must be a list")
        pages = []
    if not pages:
        warns.append("no pages defined")
    rot = dev.get("rotation", 0)
    w, h = (250, 122) if rot in (0, 180) else (122, 250)
    for pi, page in enumerate(pages):
        tag = "pages[%d]" % pi
        if not isinstance(page, dict) or not isinstance(page.get("items", []), list):
            errs.append(tag + " must be an object with an items list")
            continue
        for ii, it in enumerate(page.get("items", [])):
            t = "%s.items[%d]" % (tag, ii)
            if not isinstance(it, dict):
                errs.append(t + " must be an object")
                continue
            typ = it.get("type")
            if typ not in WIDGETS:
                errs.append("%s: unknown type %r (use %s)" % (t, typ, ", ".join(WIDGETS)))
                continue
            for k in ("x", "y", "w", "h", "r", "size", "scale", "lines", "x1", "y1", "x2", "y2", "gap"):
                if k in it and not _is_num(it[k]):
                    errs.append("%s.%s must be a number" % (t, k))
            if typ == "text" and "text" not in it:
                errs.append(t + ": text needs a \"text\" field")
            if typ == "text":
                f = it.get("font", "s16")
                if f != "8x8" and not util.exists("/fonts/%s.fnt" % f):
                    warns.append("%s: font %r not found in /fonts" % (t, f))
            if typ == "image":
                if not it.get("src"):
                    errs.append(t + ": image needs \"src\"")
                elif not util.exists("/" + it["src"].lstrip("/")):
                    warns.append("%s: image %r not found" % (t, it["src"]))
            if typ == "qr" and not it.get("data"):
                errs.append(t + ": qr needs \"data\"")
            if typ == "plugin":
                name = it.get("name", "")
                if not name or not util.exists("/plugins/%s.py" % name):
                    warns.append("%s: plugin %r not found in /plugins" % (t, name))
            x = it.get("x", 0)
            y = it.get("y", 0)
            if _is_num(x) and _is_num(y) and (x >= w or y >= h or x < -w or y < -h):
                warns.append("%s: x/y outside the %dx%d screen" % (t, w, h))
    return errs, warns


def parse(text):
    """Parse + merge defaults. Raises ValueError with a readable message."""
    try:
        user = json.loads(text)
    except ValueError as e:
        raise ValueError("invalid JSON: %s" % e)
    if not isinstance(user, dict):
        raise ValueError("top level must be a JSON object")
    return _merge(DEFAULTS, user)


def load():
    """Return (config, problem). problem is None when everything is fine."""
    problem = None
    for path in (CONFIG, BACKUP):
        try:
            cfg = parse(util.read_text(path))
            errs, _ = validate(cfg)
            if errs:
                raise ValueError(errs[0])
            if path == BACKUP:
                problem = "using config.json.bak (config.json: %s)" % (problem or "unreadable")
            return cfg, problem
        except (OSError, ValueError) as e:
            problem = problem or str(e)
    cfg = _merge(DEFAULTS, {})
    cfg["vars"]["error"] = problem or "no config"
    cfg["pages"] = [ERROR_PAGE]
    return cfg, problem


def save_text(text):
    """Validate and atomically store a config given as text. Returns warnings."""
    cfg = parse(text)
    errs, warns = validate(cfg)
    if errs:
        raise ValueError("; ".join(errs[:5]))
    util.write_atomic(CONFIG, text, backup=BACKUP)
    return warns
