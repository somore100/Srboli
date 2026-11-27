# tests/test_keyboard_inset.py - xvfb-run -a python3 tests/test_keyboard_inset.py  (kivy screens.)
# The keyboard must never cover the Learn / Math Steps answer boxes.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from core.keyboard_inset import KeyboardLift, ime_height_px

assert ime_height_px() == 0                      # off Android: nothing to do

kb = {"h": 0}
root = BoxLayout(padding=10)
ti = TextInput(); root.add_widget(ti)
lift = KeyboardLift(root, height_fn=lambda: kb["h"])
lift.watch(ti)
assert list(root.padding) == [10, 10, 10, 10]

ti.focus = True; kb["h"] = 300; lift._tick(0)
assert list(root.padding) == [10, 10, 10, 310], root.padding       # lifted above the keyboard
kb["h"] = 280; lift._tick(0); assert root.padding[3] == 290         # follows the keyboard
ti.focus = False; lift._tick(0)
assert root.padding[3] == 290                                       # kept while the keyboard hides
kb["h"] = 0; assert lift._tick(0) is False                          # keyboard gone: stop polling
assert list(root.padding) == [10, 10, 10, 10], root.padding         # and restore the layout
assert lift._ev is None

# the real screens use it
from screens.math_steps_screen import MathStepsScreen
from screens.learn_screen import LearnScreen
m = MathStepsScreen(); assert isinstance(m._lift, KeyboardLift) and m.step_in in m._lift._inputs
l = LearnScreen(); assert isinstance(l._lift, KeyboardLift)
print("keyboard inset OK")
