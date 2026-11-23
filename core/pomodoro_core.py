# core/pomodoro_core.py - the Pomodoro / focus timer logic. Pure Python.
#
# Focus (work) rounds with short breaks and a long break after every `rounds` focus
# rounds. Time is measured with a clock the caller passes in (time.monotonic in the app,
# a fake one in tests), so a screen that wakes up late still shows the right time.
import os
import time

import app_data
from core.jsonio import read_json, write_json_atomic

WORK, SHORT, LONG = "work", "short", "long"
PHASE_NAMES = {WORK: "Focus", SHORT: "Short break", LONG: "Long break"}
DEFAULTS = {"work": 25, "short": 5, "long": 15, "rounds": 4, "auto": True}
LIMITS = {"work": (1, 180), "short": (1, 60), "long": (1, 90), "rounds": (1, 12)}


def clean_settings(d):
    out = dict(DEFAULTS)
    for k, (lo, hi) in LIMITS.items():
        try:
            out[k] = max(lo, min(hi, int(d.get(k, DEFAULTS[k]))))
        except (TypeError, ValueError):
            pass
    out["auto"] = bool(d.get("auto", DEFAULTS["auto"]))
    return out


def fmt(seconds):
    s = max(0, int(seconds + 0.999))
    return f"{s // 60:02d}:{s % 60:02d}"


class Pomodoro:
    def __init__(self, settings=None):
        self.settings = clean_settings(settings or {})
        self.phase = WORK
        self.running = False
        self.remaining = self.duration(WORK)
        self.round = 1               # which focus round of the cycle we are in (1-based)
        self.finished_work = 0       # focus rounds completed since reset
        self._last = None

    def duration(self, phase):
        return self.settings[phase] * 60

    def configure(self, settings):
        """New durations. A timer that has not started this phase yet picks them up."""
        fresh = (not self.running and self.remaining == self.duration(self.phase))
        self.settings = clean_settings(settings)
        if fresh:
            self.remaining = self.duration(self.phase)
        else:                           # mid-phase: never more time left than the phase has
            self.remaining = min(self.remaining, self.duration(self.phase))

    # ----- controls -----
    def start(self, now):
        if not self.running:
            self.running = True
            self._last = now

    def pause(self, now):
        self.tick(now)
        self.running = False

    def reset(self):
        self.phase, self.running = WORK, False
        self.round, self.finished_work = 1, 0
        self.remaining = self.duration(WORK)

    def skip(self, now):
        """End this phase early. A skipped focus round does not count."""
        was_running = self.running
        self._advance(counted=False)
        self.running = was_running
        self._last = now

    # ----- time -----
    def tick(self, now):
        """Advance the clock. Returns a list of events: ("work_done", minutes) when a
        focus round was completed, ("phase", new_phase) whenever the phase changed."""
        events = []
        if not self.running:
            return events
        dt = max(0.0, now - self._last)
        self._last = now
        self.remaining -= dt
        if self.remaining <= 0:
            was_work = self.phase == WORK
            events += self._advance(counted=True)
            if was_work:
                events.insert(0, ("work_done", self.settings["work"]))
            if not self.settings["auto"]:
                self.running = False
        return events

    def _advance(self, counted):
        if self.phase == WORK:
            if counted:
                self.finished_work += 1
            nxt = LONG if self.round % self.settings["rounds"] == 0 else SHORT
        else:
            nxt = WORK
            if self.phase == LONG:
                self.round = 1
            else:
                self.round += 1
        self.phase = nxt
        self.remaining = self.duration(nxt)
        return [("phase", nxt)]

    def progress(self):
        total = self.duration(self.phase)
        return max(0.0, min(1.0, 1 - self.remaining / total)) if total else 0.0


# ---------- saved settings and per-day totals ----------
def _path():
    return os.path.join(app_data.subdir("config"), "pomodoro.json")


def load():
    d = read_json(_path(), {})
    return clean_settings(d.get("settings", {})), d.get("days", {})


def save(settings, days):
    keep = sorted(days)[-30:]
    try:
        write_json_atomic(_path(), {"settings": clean_settings(settings),
                                    "days": {k: days[k] for k in keep}})
    except Exception:
        pass


def add_focus(days, minutes, today=None):
    """Count one finished focus round (in place) for today's date."""
    today = today or time.strftime("%Y-%m-%d")
    day = days.setdefault(today, {"rounds": 0, "minutes": 0})
    day["rounds"] += 1
    day["minutes"] += int(minutes)
    return day
