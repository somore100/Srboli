# core/cover_core.py — shared, Kivy-free and tkinter-free logic for the
# "Cover" feature (privacy boxes / blackout / screen-capture exclusion).
#
# Pieces:
#   * config   — cover.json in the Srboli data dir (boxes, hotkeys, options)
#   * control  — a tiny localhost TCP channel to the running cover process
#                (`Srboli --cover`). Same authkey file as the daemon IPC.
#                Also what `Srboli --cover-cmd toggle` uses, so Wayland users
#                can bind a *system* shortcut (global hotkeys are not
#                possible for apps on Wayland).
#   * launch   — command lines for spawning the cover process
#
# Desktop only. Nothing here touches Android APIs.

import os
import sys
import json
import socket
import platform

import app_data

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 47613
CONFIG_NAME = "cover.json"

STYLES = ("solid", "frame")
HOTKEY_ACTIONS = ("toggle", "blackout", "add_box", "lock")
HOTKEY_LABELS = {
    "toggle":   "Show / hide all boxes",
    "blackout": "Blackout (all screens)",
    "add_box":  "Draw a new box",
    "lock":     "Lock the session",
}
DEFAULT_HOTKEYS = {
    "toggle":   "<ctrl>+<alt>+h",
    "blackout": "<ctrl>+<alt>+b",
    "add_box":  "<ctrl>+<alt>+n",
    "lock":     "",
}


# ── platform helpers ────────────────────────────────────────────────────
def is_desktop():
    return ("ANDROID_ARGUMENT" not in os.environ
            and "ANDROID_ROOT" not in os.environ)


def session_type():
    """'windows', 'x11', 'wayland', 'mac' or 'unknown'."""
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    s = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if s in ("x11", "wayland"):
        return s
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def global_hotkeys_supported():
    """True where a pynput global hotkey listener can actually work."""
    return session_type() in ("windows", "x11", "mac")


def capture_exclusion_supported():
    """Hiding a window from screen capture only exists on Windows
    (SetWindowDisplayAffinity). Elsewhere the compositor captures
    everything, so a 'hide from recording' box would still be recorded."""
    return os.name == "nt"


def tk_available():
    import importlib.util
    try:
        return importlib.util.find_spec("tkinter") is not None
    except Exception:
        return False


def pynput_available():
    import importlib.util
    try:
        return importlib.util.find_spec("pynput") is not None
    except Exception:
        return False


# ── hotkey strings (pynput GlobalHotKeys syntax) ────────────────────────
_MODS = {"ctrl", "alt", "shift", "cmd", "alt_gr", "ctrl_l", "ctrl_r",
         "alt_l", "alt_r", "shift_l", "shift_r", "cmd_l", "cmd_r"}
_NAMED = {"space", "enter", "esc", "tab", "backspace", "delete", "home",
          "end", "page_up", "page_down", "up", "down", "left", "right",
          "insert", "pause", "print_screen", "scroll_lock", "caps_lock",
          "menu"} | {f"f{i}" for i in range(1, 25)}


def normalize_hotkey(text):
    """Turn user input like 'Ctrl+Alt+H' or '<ctrl>+<alt>+h' into pynput
    syntax ('<ctrl>+<alt>+h'). Returns '' for empty input. Raises
    ValueError with a readable message for anything unusable."""
    text = (text or "").strip().lower()
    if not text:
        return ""
    parts = [p.strip() for p in text.replace(" ", "").split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    out, mods, keys = [], 0, 0
    for p in parts:
        bare = p[1:-1] if p.startswith("<") and p.endswith(">") else p
        bare = {"control": "ctrl", "win": "cmd", "super": "cmd",
                "meta": "cmd", "escape": "esc", "return": "enter",
                "pgup": "page_up", "pgdn": "page_down"}.get(bare, bare)
        if bare in _MODS:
            out.append(f"<{bare}>")
            mods += 1
        elif bare in _NAMED:
            out.append(f"<{bare}>")
            keys += 1
        elif len(bare) == 1 and bare.isprintable():
            out.append(bare)
            keys += 1
        else:
            raise ValueError(f"unknown key: {p!r}")
    if keys != 1:
        raise ValueError("need exactly one non-modifier key")
    if mods == 0:
        raise ValueError("add at least one modifier (Ctrl / Alt / Shift)")
    return "+".join(out)


# ── config ──────────────────────────────────────────────────────────────
def config_path():
    return os.path.join(app_data.subdir("cover"), CONFIG_NAME)


def default_box(n=1):
    return {"id": f"b{n}", "name": f"Box {n}", "x": 100, "y": 100,
            "w": 400, "h": 200, "style": "solid", "color": "#000000",
            "opacity": 1.0, "hide_from_capture": False, "hotkey": ""}


def default_config():
    return {"version": 1, "service_enabled": False, "start_hidden": False,
            "hotkeys": dict(DEFAULT_HOTKEYS),
            "blackout": {"color": "#000000", "opacity": 1.0},
            "lock_after_blackout": False,
            "boxes": []}


def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _color(v, default="#000000"):
    v = str(v or "").strip()
    if len(v) == 7 and v[0] == "#":
        try:
            int(v[1:], 16)
            return v.lower()
        except ValueError:
            pass
    return default


def _hotkey_or_empty(v):
    try:
        return normalize_hotkey(v)
    except ValueError:
        return ""


def normalize_box(b, fallback_n=1):
    base = default_box(fallback_n)
    if not isinstance(b, dict):
        return base
    out = dict(base)
    out["id"] = str(b.get("id") or base["id"])
    out["name"] = str(b.get("name") or base["name"])[:40]
    out["x"] = int(_clamp(b.get("x"), -20000, 20000, base["x"]))
    out["y"] = int(_clamp(b.get("y"), -20000, 20000, base["y"]))
    out["w"] = int(_clamp(b.get("w"), 8, 20000, base["w"]))
    out["h"] = int(_clamp(b.get("h"), 8, 20000, base["h"]))
    out["style"] = b.get("style") if b.get("style") in STYLES else "solid"
    out["color"] = _color(b.get("color"))
    out["opacity"] = round(_clamp(b.get("opacity"), 0.05, 1.0, 1.0), 2)
    out["hide_from_capture"] = bool(b.get("hide_from_capture"))
    out["hotkey"] = _hotkey_or_empty(b.get("hotkey"))
    return out


def normalize_config(cfg):
    out = default_config()
    if not isinstance(cfg, dict):
        return out
    out["service_enabled"] = bool(cfg.get("service_enabled"))
    out["start_hidden"] = bool(cfg.get("start_hidden"))
    out["lock_after_blackout"] = bool(cfg.get("lock_after_blackout"))
    hk = cfg.get("hotkeys")
    if isinstance(hk, dict):
        for k in HOTKEY_ACTIONS:
            if k in hk:
                out["hotkeys"][k] = _hotkey_or_empty(hk[k])
    bo = cfg.get("blackout")
    if isinstance(bo, dict):
        out["blackout"]["color"] = _color(bo.get("color"))
        out["blackout"]["opacity"] = round(
            _clamp(bo.get("opacity"), 0.05, 1.0, 1.0), 2)
    seen, boxes = set(), []
    raw = cfg.get("boxes")
    for i, b in enumerate(raw if isinstance(raw, list) else [], 1):
        nb = normalize_box(b, i)
        while nb["id"] in seen:
            nb["id"] += "_"
        seen.add(nb["id"])
        boxes.append(nb)
    out["boxes"] = boxes
    return out


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            return normalize_config(json.load(f))
    except (OSError, ValueError):
        return default_config()


def save_config(cfg):
    cfg = normalize_config(cfg)
    path = config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)
    return cfg


def config_mtime():
    try:
        return os.path.getmtime(config_path())
    except OSError:
        return 0.0


def new_box_id(cfg):
    used = {b["id"] for b in cfg["boxes"]}
    n = 1
    while f"b{n}" in used:
        n += 1
    return f"b{n}", n


# ── control channel ─────────────────────────────────────────────────────
def _token():
    from core.daemon_ipc import get_authkey
    return get_authkey().hex()


def send_cover_command(cmd, arg="", timeout=1.5):
    """Send one command to the running cover process. Returns the reply
    string ('ok', 'ok <info>', 'err <why>') or None if nothing answered."""
    line = f"{_token()} {cmd} {arg}".rstrip() + "\n"
    try:
        with socket.create_connection((CONTROL_HOST, CONTROL_PORT),
                                      timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(line.encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(256)
                if not chunk:
                    break
                data += chunk
            return data.decode("utf-8", "replace").strip() or None
    except OSError:
        return None


def is_running():
    return (send_cover_command("ping") or "").startswith("ok")


def parse_control_line(line):
    """'<token> cmd arg...' -> (token, cmd, arg). Tolerates junk."""
    parts = (line or "").strip().split(None, 2)
    if len(parts) < 2:
        return None, None, ""
    return parts[0], parts[1].lower(), parts[2] if len(parts) > 2 else ""


def token_ok(given):
    import hmac
    try:
        return hmac.compare_digest(str(given), _token())
    except Exception:
        return False


# ── launching ───────────────────────────────────────────────────────────
def _app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cover_launch_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cover"]
    return [sys.executable, os.path.join(_app_root(), "main.py"), "--cover"]


def cover_cmd_launch_cmd(cmd):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cover-cmd", cmd]
    return [sys.executable, os.path.join(_app_root(), "main.py"),
            "--cover-cmd", cmd]


def start_cover():
    """Spawn the cover process if it isn't already running."""
    from core.daemon_ipc import spawn_detached
    if is_running():
        return True
    try:
        spawn_detached(cover_launch_cmd())
        return True
    except Exception:
        return False


def lock_session():
    """Lock the OS session. Returns True if a lock command was issued."""
    import subprocess
    try:
        if os.name == "nt":
            import ctypes
            return bool(ctypes.windll.user32.LockWorkStation())
        if sys.platform == "darwin":
            subprocess.Popen(["pmset", "displaysleepnow"])
            return True
        for cmd in (["loginctl", "lock-session"],
                    ["xdg-screensaver", "lock"],
                    ["gnome-screensaver-command", "-l"]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    except Exception:
        pass
    return False
