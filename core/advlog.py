# core/advlog.py - "Advanced logging": what the app RECEIVED and what it DID.
#
# Off by default (Settings > Advanced logging). When on, one text file
# (Srboli_advanced.log, previous run kept as .prev.log, capped at ~1.5 MB)
# gets timestamped lines for:
#   env     platform, Kivy, input providers + [input] config at start
#   touch   every down/up: device, button, position, the widget chain under
#           it, and the OTHER touches still active (a stuck one is what
#           makes `disable_on_activity` swallow all mouse clicks)
#   key     key presses (letters are logged as "<char>" only for shortcuts
#           with Ctrl/Alt, so typing is not recorded)
#   screen  every screen change
#   build   how long each screen took to build (stalls)
#   stall   main loop was blocked longer than STALL_S
#   did     anything else via advlog.did("...") from app code
# The toggle works live: handlers are always installed and return at once
# while disabled. Never raises.
import os
import sys
import time
import threading

STALL_S = 0.35
MAX_BYTES = 1_500_000
FILE = "Srboli_advanced.log"

_enabled = False
_installed = False
_path = None
_lock = threading.Lock()
_t0 = time.monotonic()


def _dirs():
    out = []
    try:
        import app_data
        out.append(os.path.join(app_data.get_data_dir(), "logs"))
    except Exception:
        pass
    out.append(os.path.join(os.getcwd(), "logs"))
    return out


def log_path():
    global _path
    if _path:
        return _path
    for d in _dirs():
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, FILE)
            if os.path.exists(p):
                os.replace(p, os.path.join(d, "Srboli_advanced.prev.log"))
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"=== advanced log {time.strftime('%Y-%m-%d %H:%M:%S')}"
                        " ===\n")
            _path = p
            return p
        except Exception:
            continue
    return None


def is_enabled():
    return _enabled


def _write(kind, msg):
    try:
        with _lock:
            p = log_path()
            if not p:
                return
            if os.path.getsize(p) > MAX_BYTES:
                with open(p, "w", encoding="utf-8") as f:
                    f.write("=== log truncated (size cap) ===\n")
            with open(p, "a", encoding="utf-8") as f:
                f.write(f"{time.monotonic() - _t0:9.3f}s {kind:<6} {msg}\n")
    except Exception:
        pass


def did(msg, kind="did"):
    """App code calls this for 'what I did'. Free when disabled."""
    if _enabled:
        _write(kind, msg)


def set_enabled(on):
    global _enabled
    on = bool(on)
    if on and not _enabled:
        _enabled = True
        _write("env", _env_text())
    elif not on and _enabled:
        _write("env", "advanced logging switched off")
        _enabled = False


def _env_text():
    parts = [f"python {sys.version.split()[0]} on {sys.platform}"]
    try:
        import kivy
        from kivy.base import EventLoop
        from kivy.config import Config
        parts.append(f"kivy {kivy.__version__}")
        parts.append("providers=" + ",".join(
            type(p).__name__ for p in EventLoop.input_providers))
        parts.append("[input]=" + "; ".join(
            f"{k}={v}" for k, v in Config.items("input")))
    except Exception as e:
        parts.append(f"(env probe failed: {e})")
    return " | ".join(parts)


def _chain(window, pos, limit=8):
    """Class names from the top-level child down to the widget under pos."""
    names = []
    kids = list(window.children)
    while kids and len(names) < limit:
        hit = None
        for w in kids:                      # children[0] is on top
            try:
                if w.collide_point(*pos):
                    hit = w
                    break
            except Exception:
                continue
        if hit is None:
            break
        label = type(hit).__name__
        t = getattr(hit, "text", None)
        if isinstance(t, str) and t:
            label += f"({t[:18]!r})"
        names.append(label)
        kids = list(getattr(hit, "children", []))
    return " > ".join(names) or "(nothing)"


def _touch_line(phase, touch, window):
    from kivy.base import EventLoop
    others = [f"{t.device}#{t.uid}" for t in EventLoop.touches
              if t.uid != touch.uid]
    btn = getattr(touch, "button", "")
    scroll = " wheel" if getattr(touch, "is_mouse_scrolling", False) else ""
    s = (f"{phase} {touch.device}#{touch.uid} {btn}{scroll} "
         f"pos=({touch.x:.0f},{touch.y:.0f})")
    if phase == "down":
        s += f" -> {_chain(window, touch.pos)}"
    if others:
        s += f" | other active touches: {', '.join(others)}"
    return s


def install(window, screen_manager=None):
    """Hook the window and screen manager once; logging itself stays off
    until set_enabled(True)."""
    global _installed
    if _installed:
        return
    _installed = True
    try:
        def on_down(w, touch, *a):
            if _enabled:
                _write("touch", _touch_line("down", touch, w))

        def on_up(w, touch, *a):
            if _enabled:
                _write("touch", _touch_line("up  ", touch, w))

        def on_key(w, key, scancode, codepoint, modifiers, *a):
            if _enabled:
                mods = "+".join(modifiers)
                shown = (f"'{codepoint}'" if ("ctrl" in modifiers
                                              or "alt" in modifiers)
                         else "<char>" if codepoint else "")
                _write("key", f"down key={key} {shown} mods={mods or '-'}")

        window.bind(on_touch_down=on_down, on_touch_up=on_up,
                    on_key_down=on_key)

        if screen_manager is not None:
            screen_manager.bind(current=lambda sm, cur: _write(
                "screen", f"-> {cur}") if _enabled else None)

        from kivy.clock import Clock
        last = [time.monotonic()]

        def tick(dt):
            now = time.monotonic()
            gap = now - last[0]
            last[0] = now
            if _enabled and gap > STALL_S + 0.1:
                _write("stall", f"main loop blocked for {gap:.2f}s")
        Clock.schedule_interval(tick, 0.1)
    except Exception as e:
        _write("env", f"install failed: {e}")
