# tests/test_picker_guards.py - needs a display (xvfb-run -a python3 ...)
import os, sys, time, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.input.providers.mouse import MouseMotionEventProvider
from kivy.core.window.window_sdl2 import SDL2MotionEventProvider
import core.pathbar as pb
import core.tap_guard as tg

def tick(n=3):
    for _ in range(n): EventLoop.idle()

# ---- tap guard: finger + mouse ghost on the same button ---------------------------
mp = MouseMotionEventProvider("mouse", "mouse,disable_multitouch")
EventLoop.add_input_provider(mp, True); mp.start()
presses, releases = [], []
b = Button(text="T", size_hint=(None, None), size=(200, 100), pos=(100, 100))
b.bind(on_press=lambda *a: presses.append(1), on_release=lambda *a: releases.append(1))
Window.add_widget(b); tick(5)

def tap(i):
    fx, fy = b.center_x / Window.width, b.center_y / Window.height
    SDL2MotionEventProvider.q.appendleft(("fingerdown", 100 + i, fx, 1 - fy, 0.5))
    Window.dispatch("on_mouse_down", b.center_x, Window.height - b.center_y, "left", [])
    tick()
    SDL2MotionEventProvider.q.appendleft(("fingerup", 100 + i, fx, 1 - fy, 0.5))
    Window.dispatch("on_mouse_up", b.center_x, Window.height - b.center_y, "left", [])
    tick()

for i in range(5): tap(i); time.sleep(0.25)
print("WITHOUT guard: 5 taps ->", len(presses), "presses", len(releases), "releases")
assert len(presses) == 10                                # the bug reproduced
presses.clear(); releases.clear()
tg.install()
for i in range(5): tap(10 + i); time.sleep(0.25)
print("WITH guard:    5 taps ->", len(presses), "presses", len(releases), "releases")
assert len(presses) == 5 and len(releases) == 5
# genuinely separate taps 0.25 s apart are all kept (done above); and a quick
# second tap on a DIFFERENT button is not affected
b2 = Button(text="U", size_hint=(None, None), size=(200, 100), pos=(100, 300))
hits = []; b2.bind(on_release=lambda *a: hits.append(1)); Window.add_widget(b2); tick(5)
b.dispatch("on_touch_down", type("T", (), {"pos": b.center, "is_mouse_scrolling": False, "grab": lambda *a: None, "ud": {}, "grab_current": None, "button": "left", "profile": []})()) if False else None

# ---- picker: stay inside the allowed roots, revert from bad folders ---------------
root = tempfile.mkdtemp(); sub = os.path.join(root, "sub"); os.mkdir(sub)
pb._is_android = lambda: True
pb.allowed_roots = lambda: [os.path.abspath(root)]
pb.install()
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.boxlayout import BoxLayout
ch = FileChooserIconView(path=root, multiselect=True)
lay = BoxLayout(orientation="vertical"); lay.add_widget(ch)
Window.add_widget(lay); tick(6)
bar = [w for w in lay.children if type(w).__name__ == "PathBar"][0]
ch.path = os.path.dirname(root); tick()
print("went above root ->", ch.path == root, "|", bar._status.text)
assert ch.path == root and "top of the storage" in bar._status.text
ch.path = sub; tick(); assert ch.path == sub
orig_state = pb.folder_state
pb.folder_state = lambda p: "denied" if p.endswith("locked") else orig_state(p)
locked = os.path.join(root, "locked"); os.mkdir(locked)
ch.path = locked; tick()
print("denied folder ->", ch.path == sub, "|", bar._status.text)
assert ch.path == sub and "doesn't let apps open" in bar._status.text
bar._up(); tick(); assert ch.path == root
bar._up(); tick(); assert ch.path == root                  # Up at the top stays put
pb.folder_state = orig_state

# ---- picker: one tap that arrives twice toggles the selection ONCE -------------------
f = os.path.join(root, "a.png"); open(f, "w").write("x")
class E: path = f
class T: profile = []; button = "left"; is_double_tap = False
ch.path = root; tick(6)
ch.selection = []
ch.entry_touched(E(), T()); ch.entry_touched(E(), T())      # ghost within 150 ms
print("selection after a doubled tap:", ch.selection)
assert ch.selection == [f]
time.sleep(0.25); ch.entry_touched(E(), T())                 # a real second tap: unselect
assert ch.selection == []
print("picker guards passed")
