# tests/test_math_steps_screen.py - needs a display (xvfb-run -a python3 tests/test_math_steps_screen.py)
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
from screens.math_steps_screen import MathStepsScreen

def tick(n=3):
    for _ in range(n): Clock.tick()

s = MathStepsScreen(name="m"); tick()
assert s.step_in.disabled and s.session is None
s.check(); s.hint()                                  # nothing happens before Start
s.problem_in.text = "2x+"; s.start(); assert s.session is None and "ends too early" in s.feedback.text
s.problem_in.text = "x^3=8"; s.start()
assert s.session and "can't solve" in s.info.text and not s.step_in.disabled   # hard: checked, not solved
s.problem_in.text = "2x+3=5x-1"; s.start(); tick()
assert s.session.level == "Medium" and "Equation" in s.info.text and len(s.log.children) == 1

s.step_in.text = "-3x=-1-3"; s.check(); tick()          # a valid route
assert "OK" in s.log.children[0].text and s.session.wrong == 0
s.step_in.text = "3x=5"; s.check(); tick()              # wrong
assert "Try again" in s.feedback.text and s.session.wrong >= 1
n = len(s.log.children)
s.hint(); assert "Hint" in s.feedback.text and s._hint_level == 1
s.hint(); s.hint(); s.hint(); assert s._hint_level == 3 and "Next line" in s.feedback.text

s.problem_in.text = "3(x+2)=15"; s.start()
for t in ("3x+6=15", "3x=9", "x=3"):
    s.step_in.text = t; s.check(); tick()
assert "Done" in s.feedback.text and s.step_in.disabled and "No wrong steps" in s.feedback.text

s.problem_in.text = "2x+3=7"; s.start(); s.show_solution(); tick()
assert "That was the solution" in s.feedback.text and len(s.log.children) == 3

# quadratics: factor route, with the zero-product rule and a wrong "x = 2"
s.problem_in.text = "x^2-5x+6=0"; s.start(); assert "medium" in s.info.text
s.step_in.text = "(x-2)(x-3)=0"; s.check(); tick()
s.step_in.text = "x=2"; s.check(); tick(); assert "missing" in s.feedback.text
s.step_in.text = "x-2=0 or x-3=0"; s.check(); tick()
s.step_in.text = "x = 2 or x = 3"; s.check(); tick()
assert "Done" in s.feedback.text and s.step_in.disabled
s.problem_in.text = "x^2-3x+1=0"; s.start(); s.hint(); s.hint(); s.hint(); tick()
s.show_solution(); tick(); assert "\u00b1" in s.log.children[0].text and "sqrt(5)" in s.log.children[0].text

# the keypad types into the active box
s.problem_in.text = "2"; s._active = s.problem_in; s.problem_in.cursor = (1, 0)
s._type("x"); assert s.problem_in.text == "2x", s.problem_in.text
print("math steps screen OK")
