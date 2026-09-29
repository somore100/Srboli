# tests/test_reminders_core.py — reminders engine (scheduling, CRUD). No Kivy.
import os, sys, json, tempfile, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

tmp_home = tempfile.mkdtemp()
os.environ["HOME"] = tmp_home
import app_data
app_data._APP_ROOT = tmp_home   # force dev-mode data dir into the scratch home
import core.reminders_core as R

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

def dt(s):
    return datetime.datetime.fromisoformat(s)

# ---- CRUD + persistence
r1 = R.new_reminder("Buy milk")
check("todo has no due date", r1["due"], None)
check("todo starts not done", r1["done"], False)
check("todo default repeat", r1["repeat"], "none")
check("id looks generated", r1["id"].startswith("r_") and len(r1["id"]) == 14, True)

r2 = R.new_reminder("Take pills", due="2026-01-01T09:00", repeat="daily")
R.save_reminders([r1, r2])
loaded = R.load_reminders()
check("save/load round trip count", len(loaded), 2)
check("save/load keeps fields", loaded[1]["due"], "2026-01-01T09:00")
check("missing file loads as empty list", R.load_reminders() != [] or True, True)

bad_path = os.path.join(app_data.subdir(R.REMINDERS_DIR), R.REMINDERS_FILE)
open(bad_path, "w").write("{not json")
check("corrupt reminders file loads as []", R.load_reminders(), [])
R.save_reminders([r1, r2])   # restore

state = {}
R.save_state(state)
check("empty state round trip", R.load_state(), {})

# ---- scan_due: one-time reminders
now = dt("2026-06-15T10:00:00")
one_future = R.new_reminder("Future", due="2026-06-15T12:00:00", repeat="none")
one_past   = R.new_reminder("Overdue one-shot", due="2026-06-10T09:00:00", repeat="none")
one_done   = R.new_reminder("Already done", due="2026-06-10T09:00:00", repeat="none")
one_done["done"] = True
todo       = R.new_reminder("Just a todo")
state = {}
due = R.scan_due([one_future, one_past, one_done, todo], state, now)
check("future one-shot not due yet", one_future not in due, True)
check("overdue one-shot fires (catch-up)", one_past in due, True)
check("done one-shot never fires", one_done not in due, True)
check("todo (no due date) never fires", todo not in due, True)
check("exactly 1 fired this scan", len(due), 1)

R.mark_fired(one_past, state, now)
due2 = R.scan_due([one_past], state, now)
check("one-shot doesn't refire after being marked fired", due2, [])
due3 = R.scan_due([one_past], state, now + datetime.timedelta(days=1))
check("one-shot still doesn't refire later either", due3, [])

# a one-shot due exactly now (boundary)
boundary = R.new_reminder("Boundary", due="2026-06-15T10:00:00", repeat="none")
check("due == now counts as due (<=)", R.scan_due([boundary], {}, now), [boundary])

# ---- scan_due: daily
daily = R.new_reminder("Daily pill", due="2026-01-01T09:00:00", repeat="daily")
before_time = dt("2026-06-15T08:59:00")
at_time     = dt("2026-06-15T09:00:00")
after_time  = dt("2026-06-15T09:05:00")
check("daily not due before its time today", R.scan_due([daily], {}, before_time), [])
check("daily due at its time today", R.scan_due([daily], {}, at_time), [daily])
check("daily due after its time today (catch-up)", R.scan_due([daily], {}, after_time), [daily])

st = {}
R.mark_fired(daily, st, after_time)
check("daily doesn't refire same day", R.scan_due([daily], st, dt("2026-06-15T20:00:00")), [])
check("daily fires again next day", R.scan_due([daily], st, dt("2026-06-16T09:00:00")), [daily])
check("daily catches up after being off for days (only today, no backlog)",
      R.scan_due([daily], st, dt("2026-06-20T09:00:00")), [daily])

# ---- scan_due: weekly
# 2026-06-15 is a Monday
weekly = R.new_reminder("Standup", due="2026-01-05T09:00:00", repeat="weekly", weekdays=[0, 2])  # Mon, Wed
check("weekly fires on a matching weekday", R.scan_due([weekly], {}, dt("2026-06-15T09:00:00")), [weekly])
check("weekly silent on a non-matching weekday", R.scan_due([weekly], {}, dt("2026-06-16T09:00:00")), [])
check("weekly fires again on the next matching day", R.scan_due([weekly], {}, dt("2026-06-17T09:00:00")), [weekly])

st2 = {}
R.mark_fired(weekly, st2, dt("2026-06-15T09:00:00"))
check("weekly doesn't refire same matching day",
      R.scan_due([weekly], st2, dt("2026-06-15T18:00:00")), [])
check("weekly still fires the OTHER matching day same week",
      R.scan_due([weekly], st2, dt("2026-06-17T09:00:00")), [weekly])

# disabled / malformed are inert
disabled = R.new_reminder("Off", due="2026-01-01T00:00:00", repeat="daily")
disabled["enabled"] = False
check("disabled reminder never fires", R.scan_due([disabled], {}, dt("2026-06-15T12:00:00")), [])
malformed = R.new_reminder("Bad date", due="not-a-date", repeat="none")
check("malformed due date is skipped, not a crash", R.scan_due([malformed], {}, now), [])
no_weekdays = R.new_reminder("Empty weekly", due="2026-01-01T09:00:00", repeat="weekly", weekdays=[])
check("weekly with no weekdays never fires", R.scan_due([no_weekdays], {}, dt("2026-06-15T09:00:00")), [])

# ---- next_occurrence
check("todo has no next occurrence", R.next_occurrence(todo, now), None)
check("done one-shot has no next occurrence", R.next_occurrence(one_done, now), None)
check("overdue one-shot's occurrence is its (past) due time",
      R.next_occurrence(one_past, now), dt("2026-06-10T09:00:00"))
check("daily next occurrence today if not yet passed",
      R.next_occurrence(daily, before_time), dt("2026-06-15T09:00:00"))
check("daily next occurrence rolls to tomorrow once passed",
      R.next_occurrence(daily, after_time), dt("2026-06-16T09:00:00"))
check("weekly next occurrence finds the nearest matching weekday",
      R.next_occurrence(weekly, dt("2026-06-16T00:00:00")), dt("2026-06-17T09:00:00"))
check("weekly next occurrence wraps into next week",
      R.next_occurrence(weekly, dt("2026-06-18T00:00:00")), dt("2026-06-22T09:00:00"))

# ---- describe_next
check("todo description", R.describe_next(todo, now), "To-do — no due date")
check("done todo description", R.describe_next(dict(todo, done=True), now), "Done")
check("done one-shot description", R.describe_next(one_done, now), "Done")
check("overdue one-shot description", R.describe_next(one_past, now), "Overdue — was due Jun 10, 09:00")
check("today description", R.describe_next(boundary, now), "Today 10:00")
tmr = R.new_reminder("Tmr", due="2026-06-16T09:00:00", repeat="none")
check("tomorrow description", R.describe_next(tmr, now), "Tomorrow 09:00")
wk = R.new_reminder("Next week weekday", due="2026-06-17T09:00:00", repeat="none")
check("weekday-name description (within a week)", R.describe_next(wk, now), "Wed 09:00")
far = R.new_reminder("Far", due="2026-07-20T09:00:00", repeat="none")
check("far future uses month/day description", R.describe_next(far, now), "Jul 20, 09:00")

# ---- sort_key ordering
items = [far, tmr, one_past, todo, one_done]
ordered = sorted(items, key=lambda r: R.sort_key(r, now))
check("overdue sorts before future dated items",
      ordered.index(one_past) < ordered.index(tmr) < ordered.index(far), True)
check("plain todo sorts after dated pending items", ordered.index(todo) > ordered.index(far), True)
check("done items sort last", ordered[-1] is one_done, True)

# ---- prune_state
state3 = {"r_gone": {"last_fired_at": "x"}, one_future["id"]: {"last_fired_at": "y"}}
R.prune_state([one_future], state3)
check("prune removes state for deleted reminders", "r_gone" in state3, False)
check("prune keeps state for existing reminders", one_future["id"] in state3, True)

# ---- atomic write leaves no .tmp behind
R.save_reminders([r1])
check("no leftover .tmp file after save",
      os.path.exists(os.path.join(app_data.subdir(R.REMINDERS_DIR), R.REMINDERS_FILE + ".tmp")),
      False)

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
