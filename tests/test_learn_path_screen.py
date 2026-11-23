# tests/test_learn_path_screen.py - xvfb-run -a python3 tests/test_learn_path_screen.py  (kivy screens.)
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.clock import Clock
from core import learn_core as L
store = {"st": {"xp": 0, "streak": 0, "last_day": "", "plans": {}}}
L.load_progress = lambda: store["st"]                      # keep everything in memory
L.save_progress = lambda st: store.update(st=st)
from screens.learn_screen import LearnScreen

plan = {"id": "pp", "title": "Path course", "topic": "t", "level": "", "description": "d", "units": [
    {"title": "One", "lessons": [{"title": "A", "intro": "", "items": [{"type": "tf", "q": "q?", "answer": True, "explain": ""}]},
                                 {"title": "B", "intro": "", "items": [{"type": "tf", "q": "q?", "answer": True, "explain": ""}]}]}]}
def texts(w, out):
    from kivy.uix.button import Button
    if isinstance(w, Button): out.append(w.text)
    for c in w.children: texts(c, out)
    return out

sc = LearnScreen()
sc._show_plan(plan)
for _ in range(5): Clock.tick(); time.sleep(0.02)
t = texts(sc._root, [])
assert "START" in t and "locked" in t and "UNIT" in t, t
sc._node_tapped({"state": "locked", "ui": 0, "li": 1, "title": "B"})   # a toast, no crash
sc._toggle_free_roam()
assert store["st"]["free_roam"] is True and "2" in texts(sc._root, [])
sc._start_lesson(0, 0); sc._next_step() if sc._les["steps"][0]["type"] == "info" else None
item = sc._les["steps"][0]; sc._pick(item, True); sc._check(item); sc._next_step()
t = texts(sc._root, [])
assert store["st"]["plans"]["pp"]["done"]["0.0"] == 100
sc._start_lesson(0, 1); item = sc._les["steps"][0]; sc._pick(item, True); sc._check(item); sc._next_step()
assert "Unit complete" in str([getattr(c, "text", "") for c in sc._root.children]) and store["st"]["xp"] >= 70
print("learn path screen OK")
