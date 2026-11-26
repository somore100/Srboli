# core/macro_core.py - click/drag automation macros (model, planner, save/load). No Kivy.
import os
import re

from core import jsonio

KINDS = ("click", "drag")
MAX_ACTIONS = 200
MAX_LOOPS = 9999
MIN_MS, MAX_MS = 0, 600000
DEFAULT_INTERVAL = 500
DEFAULT_DRAG_MS = 600
UNITS = {"ms": 1, "s": 1000}


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v != v:
        return default
    return max(lo, min(hi, v))


def clean_action(a):
    """A sanitised action dict, or None when it is unusable. Positions are screen fractions 0..1."""
    if not isinstance(a, dict) or a.get("kind") not in KINDS:
        return None
    out = {"kind": a["kind"],
           "x": _num(a.get("x"), 0, 1, 0.5), "y": _num(a.get("y"), 0, 1, 0.5),
           "interval_ms": int(_num(a.get("interval_ms"), MIN_MS, MAX_MS, DEFAULT_INTERVAL))}
    if out["kind"] == "click":
        out["hold_ms"] = int(_num(a.get("hold_ms"), 0, MAX_MS, 0))      # 0 = a quick tap
    if out["kind"] == "drag":
        out["x2"] = _num(a.get("x2"), 0, 1, out["x"])
        out["y2"] = _num(a.get("y2"), 0, 1, out["y"])
        out["duration_ms"] = int(_num(a.get("duration_ms"), 50, MAX_MS, DEFAULT_DRAG_MS))
    return out


class Macro:
    def __init__(self, name="Macro", actions=None, loops=1, speed=1.0):
        self.name = str(name)[:60] or "Macro"
        self.actions = [c for c in (clean_action(a) for a in (actions or [])[:MAX_ACTIONS]) if c]
        self.loops = int(_num(loops, 0, MAX_LOOPS, 1))      # 0 = until stopped
        self.speed = _num(speed, 0.25, 4.0, 1.0)

    def add_click(self, x, y, interval_ms=DEFAULT_INTERVAL, hold_ms=0):
        return self._add({"kind": "click", "x": x, "y": y, "interval_ms": interval_ms,
                          "hold_ms": hold_ms})

    def add_drag(self, x, y, x2, y2, duration_ms=DEFAULT_DRAG_MS, interval_ms=DEFAULT_INTERVAL):
        return self._add({"kind": "drag", "x": x, "y": y, "x2": x2, "y2": y2,
                          "duration_ms": duration_ms, "interval_ms": interval_ms})

    def _add(self, a):
        a = clean_action(a)
        if a is None or len(self.actions) >= MAX_ACTIONS:
            return None
        self.actions.append(a)
        return len(self.actions) - 1

    def remove_last(self):
        return self.actions.pop() if self.actions else None

    def remove(self, i):
        if 0 <= i < len(self.actions):
            return self.actions.pop(i)
        return None

    def update(self, i, **kw):
        """Change fields of action i (re-cleaned); returns True when applied."""
        if not 0 <= i < len(self.actions):
            return False
        c = clean_action({**self.actions[i], **kw})
        if c is None:
            return False
        self.actions[i] = c
        return True

    def set_loops(self, v):
        self.loops = int(_num(v, 0, MAX_LOOPS, 1))

    def set_speed(self, v):
        self.speed = _num(v, 0.25, 4.0, 1.0)

    def to_dict(self):
        return {"v": 1, "name": self.name, "loops": self.loops, "speed": self.speed,
                "actions": [dict(a) for a in self.actions]}

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict):
            return cls()
        acts = d.get("actions")
        return cls(d.get("name", "Macro"), acts if isinstance(acts, list) else [],
                   d.get("loops", 1), d.get("speed", 1.0))


def plan(macro, w, h):
    """Timed events [(t_ms, kind, x, y, x2, y2, duration_ms, index)] in pixels for a w*h screen
    (duration_ms is the drag time, or how long a click is held).
    Every loop repeats the actions; speed scales every wait and drag. loops == 0 plans one pass
    (the player repeats it)."""
    events, t = [], 0.0
    for _ in range(max(1, macro.loops)):
        for i, a in enumerate(macro.actions):
            x, y = a["x"] * w, a["y"] * h
            if a["kind"] == "drag":
                dur = a["duration_ms"] / macro.speed
                events.append((int(t), "drag", x, y, a["x2"] * w, a["y2"] * h, int(dur), i))
                t += dur
            else:
                hold = a["hold_ms"] / macro.speed
                events.append((int(t), "click", x, y, x, y, int(hold), i))
                t += hold
            t += a["interval_ms"] / macro.speed
    return events


def total_ms(macro):
    return plan(macro, 1, 1)[-1][0] + 1 if macro.actions else 0


def to_ms(value, unit):
    return int(_num(value, 0, MAX_MS, 0) * UNITS.get(unit, 1))


def from_ms(ms):
    """(value, unit) shown in the editor: whole seconds as 's', else 'ms'."""
    ms = int(ms)
    return (ms // 1000, "s") if ms and ms % 1000 == 0 else (ms, "ms")


def safe_name(name):
    return re.sub(r"[^\w\- ]", "", str(name)).strip()[:40] or "macro"


def save(macro, folder):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe_name(macro.name) + ".macro.json")
    jsonio.write_json_atomic(path, macro.to_dict())
    return path


def load(path):
    return Macro.from_dict(jsonio.read_json(path, default={}))


def list_saved(folder):
    try:
        return sorted(f for f in os.listdir(folder) if f.endswith(".macro.json"))
    except OSError:
        return []
