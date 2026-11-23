# core/cursor_core.py - settings, shapes and process control for the Cursor Overlay.
# No Kivy, no tkinter: the overlay window itself is core/cursor_app.py.
#
# The overlay is a small see-through, click-through window that follows the mouse
# pointer (a ring, dot, crosshair... in your colour) so an audience can follow it.
# It runs as its own process (`Srboli --cursor`); this file holds what the screen and
# the process share: the saved settings, the drawing instructions and the "is it alive"
# check.
import os
import re
import sys
import time

import app_data
from core.jsonio import read_json, write_json_atomic

SHAPES = {"ring": "Ring", "dot": "Dot", "target": "Ring with dot", "crosshair": "Crosshair",
          "square": "Square", "arrow": "Arrow"}
DEFAULTS = {"shape": "ring", "color": "#FFD400", "size": 56, "thickness": 4, "opacity": 0.8,
            "click_flash": True, "visible": True, "quit": False}
LIMITS = {"size": (16, 200), "thickness": (1, 16)}
ALIVE_SECONDS = 3.0


def supported(platform=None):
    """The overlay needs a click-through window and the global pointer position: Windows for now."""
    return (platform or sys.platform).startswith("win")


def clean(d):
    out = dict(DEFAULTS)
    d = d if isinstance(d, dict) else {}
    if d.get("shape") in SHAPES:
        out["shape"] = d["shape"]
    if isinstance(d.get("color"), str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", d["color"]):
        out["color"] = d["color"].upper()
    for k, (lo, hi) in LIMITS.items():
        try:
            out[k] = max(lo, min(hi, int(d.get(k, DEFAULTS[k]))))
        except (TypeError, ValueError):
            pass
    try:
        out["opacity"] = max(0.2, min(1.0, float(d.get("opacity", DEFAULTS["opacity"]))))
    except (TypeError, ValueError):
        pass
    for k in ("click_flash", "visible", "quit"):
        if isinstance(d.get(k), bool):
            out[k] = d[k]
    return out


def _dir():
    return app_data.subdir("cursor")


def config_path():
    return os.path.join(_dir(), "cursor.json")


def alive_path():
    return os.path.join(_dir(), "alive")


def load():
    return clean(read_json(config_path(), {}))


def save(cfg):
    write_json_atomic(config_path(), clean(cfg))


def touch_alive():
    try:
        with open(alive_path(), "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def is_running(now=None):
    try:
        return (now or time.time()) - os.path.getmtime(alive_path()) < ALIVE_SECONDS
    except OSError:
        return False


def launch_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cursor"]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(root, "main.py"), "--cursor"]


def start():
    """Start the overlay process unless it already runs. Returns (ok, message)."""
    if not supported():
        return False, "The cursor overlay works on Windows for now."
    if is_running():
        return True, "Already running."
    cfg = load()
    cfg["quit"] = False
    save(cfg)
    try:
        from core.daemon_ipc import spawn_detached
        spawn_detached(launch_cmd())
        return True, "Started."
    except Exception as e:
        return False, f"Could not start it: {e}"


def stop():
    cfg = load()
    cfg["quit"] = True
    save(cfg)


# ---------- shapes ----------
def canvas_size(cfg):
    """Side of the square window that holds the shape."""
    return cfg["size"] + 2 * cfg["thickness"] + 4


def hotspot(cfg):
    """The point of the window that sits exactly on the pointer."""
    c = canvas_size(cfg)
    if cfg["shape"] == "arrow":
        return (cfg["thickness"] + 2, cfg["thickness"] + 2)
    return (c // 2, c // 2)


def shape_items(cfg):
    """Drawing instructions in window pixels (y down):
    ("oval"|"rect", x0, y0, x1, y1, filled), ("line", x0, y0, x1, y1), ("poly", [(x, y)...], filled)"""
    s, t = cfg["size"], cfg["thickness"]
    c = canvas_size(cfg)
    m = (c - s) / 2
    x0, y0, x1, y1 = m, m, m + s, m + s
    mid = c / 2
    shape = cfg["shape"]
    if shape == "ring":
        return [("oval", x0, y0, x1, y1, False)]
    if shape == "dot":
        return [("oval", x0, y0, x1, y1, True)]
    if shape == "target":
        d = max(4, s * 0.18)
        return [("oval", x0, y0, x1, y1, False),
                ("oval", mid - d, mid - d, mid + d, mid + d, True)]
    if shape == "square":
        return [("rect", x0, y0, x1, y1, False)]
    if shape == "crosshair":
        gap = max(3, s * 0.12)
        return [("line", x0, mid, mid - gap, mid), ("line", mid + gap, mid, x1, mid),
                ("line", mid, y0, mid, mid - gap), ("line", mid, mid + gap, mid, y1)]
    h = t + 2                                   # arrow: tip on the hotspot, like a mouse pointer
    k = s / 20.0
    outline = [(0, 0), (0, 16), (4, 12), (7, 19), (10, 18), (7, 11), (12, 11)]
    return [("poly", [(h + x * k, h + y * k) for x, y in outline], True)]
