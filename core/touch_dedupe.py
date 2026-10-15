# core/touch_dedupe.py - drop the duplicate "ghost" touch Android produces.
#
# Kivy's SDL2 window feeds a phone tap in TWICE: once as a real finger touch
# (provider "sdl", see SDL2MotionEventProvider in kivy/core/window/
# window_sdl2.py - Kivy's own source admits "we have a conflict of using
# either the mouse or the finger") and once as the mouse event SDL
# synthesises from that same finger (provider "mouse"). Every widget then
# sees two taps. That single fact explains most of the "needs two taps" family
# of bugs: a CheckBox toggled on then straight back off, a DropDown that
# opens and is dismissed by the second touch, popups whose button "didn't
# work", folders that open twice, a Back that needs a second press.
#
# The filter: a 'begin' from one device within DEDUPE_WINDOW seconds and
# ~5% of the screen of a 'begin' from a DIFFERENT device is a duplicate -
# drop it and every later event (update/end) of that same touch. Real
# multi-touch is unaffected (all fingers come from the same device) and a
# real second tap is much later than the window.
#
# Install on Android only; desktop mouse+touchscreen setups are left alone.

import time

DEDUPE_WINDOW = 0.12     # seconds
DEDUPE_DIST = 0.05       # normalised screen units


class TouchDeduper:
    """Never raises: on any internal error it switches itself off and lets
    every event through, so the filter can degrade the app to 'double taps'
    but can never make it unresponsive."""

    def __init__(self, log=None):
        self._recent = []        # (time, device, x, y) of accepted begins
        self._dropped = {}       # touch uid -> time it was marked a ghost
        self.count = 0           # how many duplicates were dropped
        self.disabled = False
        self._log = log

    def should_drop(self, etype, me, now=None):
        if self.disabled:
            return False
        try:
            return self._should_drop(etype, me, now)
        except Exception as e:           # never break input handling
            self.disabled = True
            if self._log:
                self._log(f"DEDUP disabled itself after error: {e!r}")
            return False

    def _should_drop(self, etype, me, now):
        # Hover events (a mouse pointer moving with no button) are not taps:
        # never record them and never drop them - otherwise a hover arriving
        # a few ms before a real finger touch could make the finger look like
        # the "duplicate" and swallow it.
        if not getattr(me, "is_touch", True):
            return False
        now = time.monotonic() if now is None else now
        # uid is unique per touch for the life of the process. (id(me) is
        # NOT: Python reuses addresses, which could make a brand-new touch
        # look like an old ghost and swallow it.)
        key = me.uid
        if self._dropped:
            # a ghost whose 'end' never showed up must not linger
            for k in [k for k, t in self._dropped.items() if now - t > 5.0]:
                del self._dropped[k]
        if key in self._dropped:
            if etype == "end":
                del self._dropped[key]
            return True
        if etype != "begin":
            return False
        x, y = me.sx, me.sy
        self._recent = [r for r in self._recent if now - r[0] < DEDUPE_WINDOW]
        for _, dev, rx, ry in self._recent:
            if (dev != me.device and abs(rx - x) < DEDUPE_DIST
                    and abs(ry - y) < DEDUPE_DIST):
                self._dropped[key] = now
                self.count += 1
                if self._log:
                    self._log(f"DEDUP dropped {me.device} touch "
                              f"(duplicate of {dev}) at ({x:.3f},{y:.3f}) "
                              f"total={self.count}")
                return True
        self._recent.append((now, me.device, x, y))
        return False


_deduper = None


def install(log=None):
    """Wrap EventLoop.post_dispatch_input. Safe to call twice."""
    global _deduper
    if _deduper is not None:
        return _deduper
    from kivy.base import EventLoop
    _deduper = TouchDeduper(log)
    orig = EventLoop.post_dispatch_input

    def post_dispatch_input(etype, me):
        if _deduper.should_drop(etype, me):
            return
        return orig(etype, me)

    EventLoop.post_dispatch_input = post_dispatch_input
    return _deduper


def stats():
    return _deduper.count if _deduper else 0


# ── persisted switch (Touch Test screen) ───────────────────────────────────
# Flag files in the phone's root are unreliable (a fresh install can't read
# them until "all files access" is granted), so the switch lives in the app's
# own data dir. DEFAULT IS OFF: the filter only runs if you turned it on.
#
# Self-healing: when the filter starts it sets "pending". The first time any
# button actually reacts to a tap, mark_healthy() clears "pending". If the next
# start still finds "pending" set, taps never worked with the filter on, so it
# switches itself OFF again before installing - a bad filter can cost you one
# launch, never a permanently dead app.

import json
import os


def _cfg_path():
    import app_data
    return os.path.join(app_data.subdir("touch"), "touch_dedupe.json")


def load_cfg():
    try:
        with open(_cfg_path(), encoding="utf-8") as f:
            d = json.load(f)
        return {"enabled": bool(d.get("enabled", False)),
                "pending": bool(d.get("pending", False))}
    except Exception:
        return {"enabled": False, "pending": False}


def save_cfg(cfg):
    try:
        with open(_cfg_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return True
    except Exception:
        return False


def set_enabled(on):
    cfg = load_cfg()
    cfg["enabled"] = bool(on)
    cfg["pending"] = False
    return save_cfg(cfg)


def mark_healthy():
    cfg = load_cfg()
    if cfg.get("pending"):
        cfg["pending"] = False
        save_cfg(cfg)


def decide_at_startup(log=None):
    """True if the filter should be installed this run. Applies the
    self-healing rule above."""
    cfg = load_cfg()
    if cfg["pending"]:
        cfg["enabled"] = False
        cfg["pending"] = False
        save_cfg(cfg)
        if log:
            log("touch filter was ON last run and no tap ever worked: "
                "switched OFF automatically")
        return False
    if not cfg["enabled"]:
        return False
    cfg["pending"] = True
    save_cfg(cfg)
    return True
