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
    def __init__(self, log=None):
        self._recent = []        # (time, device, x, y) of accepted begins
        self._dropped = set()    # id(touch) of touches being ignored
        self.count = 0           # how many duplicates were dropped
        self._log = log

    def should_drop(self, etype, me, now=None):
        key = id(me)
        if key in self._dropped:
            if etype == "end":
                self._dropped.discard(key)
            return True
        if etype != "begin":
            return False
        now = time.monotonic() if now is None else now
        x, y = me.sx, me.sy
        self._recent = [r for r in self._recent if now - r[0] < DEDUPE_WINDOW]
        for _, dev, rx, ry in self._recent:
            if (dev != me.device and abs(rx - x) < DEDUPE_DIST
                    and abs(ry - y) < DEDUPE_DIST):
                self._dropped.add(key)
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
