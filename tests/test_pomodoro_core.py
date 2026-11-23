# tests/test_pomodoro_core.py - python3 tests/test_pomodoro_core.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import pomodoro_core as p

assert p.clean_settings({"work": 0, "short": "x", "rounds": 99, "auto": 0}) == {
    "work": 1, "short": 5, "long": 15, "rounds": 12, "auto": False}
assert p.fmt(1500) == "25:00" and p.fmt(59.2) == "01:00" and p.fmt(0) == "00:00" and p.fmt(-3) == "00:00"

t = p.Pomodoro({"work": 2, "short": 1, "long": 3, "rounds": 2, "auto": True})
assert t.phase == p.WORK and t.remaining == 120 and not t.running
assert t.tick(5) == []                                   # not started: nothing moves
t.start(10); assert t.tick(40) == [] and abs(t.remaining - 90) < 1e-9
t.pause(70); assert not t.running and abs(t.remaining - 60) < 1e-9
t.tick(500); assert abs(t.remaining - 60) < 1e-9          # paused time does not count
t.start(500)
ev = t.tick(560)                                          # focus round 1 ends
assert ev == [("work_done", 2), ("phase", p.SHORT)] and t.phase == p.SHORT and t.running
assert t.finished_work == 1 and t.remaining == 60 and t.round == 1
ev = t.tick(620); assert ev == [("phase", p.WORK)] and t.round == 2
ev = t.tick(740)                                          # focus round 2 -> long break
assert ev == [("work_done", 2), ("phase", p.LONG)] and t.finished_work == 2
ev = t.tick(920); assert ev == [("phase", p.WORK)] and t.round == 1
# a very late tick only ends ONE phase (no burning through hours of phases)
t.tick(10**6); assert t.phase == p.SHORT and t.finished_work == 3

m = p.Pomodoro({"work": 1, "auto": False})               # manual: stops after each phase
m.start(0); ev = m.tick(61)
assert ("work_done", 1) in ev and not m.running and m.phase == p.SHORT and m.remaining == 300
s = p.Pomodoro({"work": 5}); s.start(0); s.tick(10)
s.skip(10); assert s.phase == p.SHORT and s.finished_work == 0 and s.running   # skipped focus not counted
s.skip(11); assert s.phase == p.WORK and s.round == 2
s.reset(); assert s.phase == p.WORK and s.round == 1 and not s.running and s.remaining == 300
c = p.Pomodoro(); c.configure({"work": 50}); assert c.remaining == 3000
c.start(0); c.tick(100); c.configure({"work": 10}); assert c.remaining == 600   # running: capped to the new, shorter phase
assert 0 <= c.progress() <= 1

days = {}
p.add_focus(days, 25, "2026-01-01"); p.add_focus(days, 25, "2026-01-01"); p.add_focus(days, 10, "2026-01-02")
assert days["2026-01-01"] == {"rounds": 2, "minutes": 50} and days["2026-01-02"]["rounds"] == 1
print("pomodoro core OK")
