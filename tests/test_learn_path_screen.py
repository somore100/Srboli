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

# ---- modes, review, retry (new in 5.30)
store["st"] = {"xp": 0, "streak": 0, "last_day": "", "plans": {}}
plan2 = dict(plan, id="pq", mode="course", units=[{"title": "One", "lessons": [
    {"title": "A", "intro": "", "items": [
        {"type": "tf", "q": "first [b]q[/b]?", "answer": True, "explain": "why"},
        {"type": "choice", "q": "second?", "options": ["x", "y"], "answer": 1, "explain": ""}]}]}])
sc._show_plan(plan2)
assert "Points: on" in texts(sc._root, [])
sc._toggle_graded(); assert store["st"]["plans"]["pq"]["graded"] is False
sc._start_lesson(0, 0)
it = sc._les["steps"][0]; sc._pick(it, False); sc._check(it); sc._next_step()      # wrong
it = sc._les["steps"][1]; sc._pick(it, 1); sc._check(it); sc._next_step()           # right
it = sc._les["steps"][2]; sc._pick(it, True); sc._check(it); sc._next_step()        # retried right
t = texts(sc._root, [])
assert any(x.startswith("Review my answers (1 right, 1 wrong)") for x in t), t
assert "Retry the ones I got wrong" in t
assert store["st"]["xp"] == 0, store["st"]            # points are off
assert len(store["st"]["plans"]["pq"]["missed"]) == 1
sc._show_review(sc._summary)                           # markup in the question must not break it
sc._start_practice([plan2["units"][0]["lessons"][0]["items"][0]], "Retry")
it = sc._les["steps"][0]; sc._pick(it, True); sc._check(it); sc._next_step()
assert store["st"]["plans"]["pq"]["missed"] == []
plan3 = dict(plan2, id="pg", mode="general")
sc._show_plan(plan3)
assert "Mixed practice (10 random questions)" in texts(sc._root, [])
sc._start_mixed(); assert sc._les["kind"] == "practice" and len(sc._les["steps"]) == 2
print("learn modes screen OK")
