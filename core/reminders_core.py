# core/reminders_core.py — reminder/to-do data model + scheduling logic.
#
# Kivy-free (like file_sorter_core.py) so the daemon's scheduler and the
# Reminders screen share exactly one implementation of "is this due yet".
#
# Two files on disk, both under app_data.subdir("reminders"):
#   reminders.json        the reminders themselves — source of truth,
#                         edited by the UI, read (never written) by the
#                         daemon's scheduler.
#   reminders_state.json  daemon-owned: when each reminder last fired, so
#                         a restart doesn't re-fire something already
#                         shown, and a repeating reminder fires once per
#                         occurrence rather than once per scheduler tick.
#
# A reminder with no due date is a plain to-do: it never fires a
# notification, "done" just checks it off. A reminder with a due date
# and repeat "none" fires once, whenever due passes (including well
# after the fact, if the daemon wasn't running — better late than
# never for something you were reminded to do once). "daily" / "weekly"
# fire at the same time of day going forward; only *today's* occurrence
# is ever caught up on restart, so a daemon that was off for three days
# doesn't fire three backlogged notifications for a daily reminder.

import os
import json
import uuid
import datetime

import app_data

REMINDERS_DIR = "reminders"
REMINDERS_FILE = "reminders.json"
STATE_FILE = "reminders_state.json"
REPEATS = ("none", "daily", "weekly")
SCHEDULE_INTERVAL = 20        # seconds between scheduler polls (daemon)


def _dir():
    return app_data.subdir(REMINDERS_DIR)


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)      # atomic on POSIX and Windows alike


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


# ── CRUD (source-of-truth file) ─────────────────────────────────────────────
def load_reminders():
    data = _read_json(os.path.join(_dir(), REMINDERS_FILE), [])
    return data if isinstance(data, list) else []


def save_reminders(reminders):
    _atomic_write_json(os.path.join(_dir(), REMINDERS_FILE), reminders)


def new_reminder(title, due=None, repeat="none", weekdays=None, notes=""):
    """due: ISO datetime string ("YYYY-MM-DDTHH:MM") or None for a plain
    to-do with no notification. weekdays: list of 0=Monday..6=Sunday,
    only meaningful when repeat == "weekly"."""
    return {
        "id": f"r_{uuid.uuid4().hex[:12]}",
        "title": title,
        "notes": notes or "",
        "due": due,
        "repeat": repeat if repeat in REPEATS else "none",
        "weekdays": sorted(set(weekdays or [])),
        "enabled": True,
        "done": False,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
    }


# ── daemon-owned runtime state ───────────────────────────────────────────────
def load_state():
    data = _read_json(os.path.join(_dir(), STATE_FILE), {})
    return data if isinstance(data, dict) else {}


def save_state(state):
    _atomic_write_json(os.path.join(_dir(), STATE_FILE), state)


def mark_fired(reminder, state, when):
    """Record in `state` (in place) that `reminder` fired at `when`
    (a datetime) — its current occurrence for "none", or today's date
    for a repeating one."""
    entry = state.setdefault(reminder["id"], {})
    if reminder.get("repeat", "none") == "none":
        entry["last_fired_occurrence"] = reminder.get("due")
    else:
        entry["last_fired_date"] = when.date().isoformat()
    entry["last_fired_at"] = when.isoformat(timespec="seconds")


def prune_state(reminders, state):
    """Drop state entries for reminders that no longer exist, so a
    deleted-then-recreated reminder (new id) starts fresh, and the state
    file doesn't grow forever."""
    live = {r["id"] for r in reminders}
    for rid in list(state.keys()):
        if rid not in live:
            del state[rid]


# ── scheduling ───────────────────────────────────────────────────────────────
def _parse_due(due):
    return datetime.datetime.fromisoformat(due)


def scan_due(reminders, state, now=None):
    """Reminders that should fire right now, given what's already fired
    (per `state`). Pure function of its inputs — the daemon supplies the
    real clock and real files; tests supply their own of both."""
    now = now or datetime.datetime.now()
    due_now = []
    for r in reminders:
        if not r.get("enabled", True) or not r.get("due") or r.get("done"):
            continue
        try:
            due = _parse_due(r["due"])
        except (ValueError, TypeError):
            continue
        repeat = r.get("repeat", "none")
        entry = state.get(r["id"], {})

        if repeat == "none":
            if due <= now and entry.get("last_fired_occurrence") != r["due"]:
                due_now.append(r)
            continue

        if repeat == "weekly" and now.weekday() not in set(r.get("weekdays", [])):
            continue
        scheduled_today = datetime.datetime.combine(now.date(), due.time())
        if (scheduled_today <= now
                and entry.get("last_fired_date") != now.date().isoformat()):
            due_now.append(r)
    return due_now


def next_occurrence(reminder, after=None):
    """The occurrence this reminder is (or was) due at, from `after`
    onward. None only when there truly isn't one: no due date, or a
    completed one-time reminder. An overdue, not-yet-done one-time
    reminder still returns its (past) due time — it's overdue, not
    gone; scan_due() will fire it and describe_next() will say so."""
    after = after or datetime.datetime.now()
    if not reminder.get("due") or reminder.get("done"):
        return None
    try:
        due = _parse_due(reminder["due"])
    except (ValueError, TypeError):
        return None
    repeat = reminder.get("repeat", "none")

    if repeat == "none":
        return due

    time_of_day = due.time()
    if repeat == "daily":
        candidate = datetime.datetime.combine(after.date(), time_of_day)
        if candidate < after:
            candidate += datetime.timedelta(days=1)
        return candidate

    if repeat == "weekly":
        weekdays = sorted(set(reminder.get("weekdays", [due.weekday()])))
        if not weekdays:
            return None
        for delta in range(8):
            d = after.date() + datetime.timedelta(days=delta)
            if d.weekday() in weekdays:
                candidate = datetime.datetime.combine(d, time_of_day)
                if candidate >= after:
                    return candidate
    return None


_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


_MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_month_day_time(dt):
    # %-d (no leading zero) is a glibc/Linux strftime extension; Windows
    # uses %#d instead. Building it by hand keeps this working on both.
    return f"{_MONTH_SHORT[dt.month - 1]} {dt.day}, {dt.strftime('%H:%M')}"


def describe_next(reminder, now=None):
    """One-line, human-facing description of when a reminder is next
    due, for the Reminders screen's list — "Overdue", "Today 14:30",
    "Tomorrow 09:00", "Mon 09:00", "No due date", "Done"."""
    now = now or datetime.datetime.now()
    if not reminder.get("due"):
        return "Done" if reminder.get("done") else "To-do — no due date"
    nxt = next_occurrence(reminder, now)
    if nxt is None:
        return "Done"
    if reminder.get("repeat", "none") == "none" and nxt < now:
        return f"Overdue — was due {_fmt_month_day_time(nxt)}"
    if nxt.date() == now.date():
        return f"Today {nxt.strftime('%H:%M')}"
    if nxt.date() == now.date() + datetime.timedelta(days=1):
        return f"Tomorrow {nxt.strftime('%H:%M')}"
    if (nxt.date() - now.date()).days < 7:
        return f"{_WEEKDAY_SHORT[nxt.weekday()]} {nxt.strftime('%H:%M')}"
    return _fmt_month_day_time(nxt)


def sort_key(reminder, now=None):
    """Key for ordering the Reminders list: pending items with a due
    date first (soonest first), then plain to-dos, then done items
    last."""
    now = now or datetime.datetime.now()
    if reminder.get("done") and not reminder.get("due"):
        return (2, 0)
    if not reminder.get("due"):
        return (1, 0)
    nxt = next_occurrence(reminder, now)
    if nxt is None:
        return (2, 0)
    return (0, nxt.timestamp())
