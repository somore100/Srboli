# needs a display: xvfb-run -a python3 tests/test_navigation.py
import os, sys, time
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.core.window import Window
from kivy.uix.screenmanager import Screen, NoTransition
from kivy.uix.modalview import ModalView
from core.navigation import GuardedScreenManager, open_screen, install_keys, LOADING

def pump(n=6):
    for _ in range(n): EventLoop.idle(); time.sleep(0.03)

sm = GuardedScreenManager(transition=NoTransition())
sm.add_widget(Screen(name="dashboard"))
built = []
def ensure(r):
    built.append(r); sm.add_widget(Screen(name=r)); return True

open_screen(sm, "tool", ensure)
assert sm.current == LOADING and built == []        # shown first, built next frame
pump(); assert sm.current == "tool" and built == ["tool"]
open_screen(sm, "tool", ensure); assert sm.current == "tool" and built == ["tool"]   # no rebuild

sm.current = "dashboard"
open_screen(sm, "broken", lambda r: False); pump()
assert sm.current == "dashboard"                    # failure: back where we were

class T:                                            # a touch right after a switch is ignored
    pos = (1, 1); is_mouse_scrolling = False; button = "left"
    def push_attrs(self, *a): pass
    def pop_attrs(self, *a): pass
    def apply_transform_2d(self, f): pass
sm.current = "tool"
assert sm.on_touch_down(T()) is True
time.sleep(0.25)

handler = install_keys(Window, sm, focus_search=lambda: focused.append(1))
focused = []
assert handler(Window, 27, 0, "", []) is True and sm.current == "dashboard"    # Esc leaves a tool
sm.current = "tool"
assert handler(Window, 107, 0, "k", ["ctrl"]) is True and sm.current == "dashboard"
pump(); assert focused == [1]
mv = ModalView(); mv.open(); sm.current = "tool"
assert handler(Window, 27, 0, "", []) is False and sm.current == "tool"       # popup owns Esc
mv.dismiss()
print("navigation OK")
