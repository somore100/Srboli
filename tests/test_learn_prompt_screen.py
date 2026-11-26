# tests/test_learn_prompt_screen.py - xvfb-run -a python3 tests/test_learn_prompt_screen.py  (kivy screens.)
# The "Get AI prompt" box must not rebuild its long text on every keystroke (it lagged on phones).
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.clock import Clock
from core import learn_core as L
store = {"st": {"xp": 0, "streak": 0, "last_day": "", "plans": {}}}
L.load_progress = lambda: store["st"]
L.save_progress = lambda st: store.update(st=st)
from screens.learn_screen import LearnScreen

calls = []
real = L.build_prompt
L.build_prompt = lambda *a, **k: (calls.append(a), real(*a, **k))[1]

sc = LearnScreen()
sc._prompt_popup()
pop, topic, level, out = sc._prompt
base = len(calls)
assert "<your topic>" in out.text
for ch in "Python for beginners":
    topic.text += ch
assert len(calls) == base, "typing rebuilt the prompt on every key"
assert "<your topic>" in out.text
t0 = time.time()
while time.time() - t0 < 1.0:
    Clock.tick(); time.sleep(0.02)
assert len(calls) == base + 1, len(calls) - base
assert "Python for beginners" in out.text
before = out.text
sc._prompt_refresh()
assert out.text == before                                  # unchanged text is not re-set
topic.text += "!"
pop.dismiss()
t0 = time.time()
while time.time() - t0 < 0.8:
    Clock.tick(); time.sleep(0.02)
assert "beginners!" not in out.text, "a refresh fired after the popup closed"
print("learn prompt OK")
