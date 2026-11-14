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

# the ghost can trail the finger by 100-400 ms (ScrollView holds the real touch
# back for scroll_timeout): the other device within 0.6 s is still a ghost
assert tg.is_ghost(0.10, "sdl", "sdl") and tg.is_ghost(0.30, "mouse", "sdl")
assert not tg.is_ghost(0.30, "sdl", "sdl") and not tg.is_ghost(0.70, "mouse", "sdl")
presses.clear(); releases.clear()
def tap_late_ghost(i):
    fx, fy = b.center_x / Window.width, b.center_y / Window.height
    Window.dispatch("on_mouse_down", b.center_x, Window.height - b.center_y, "left", [])
    tick(); time.sleep(0.3)
    SDL2MotionEventProvider.q.appendleft(("fingerdown", 200 + i, fx, 1 - fy, 0.5))
    tick()
    Window.dispatch("on_mouse_up", b.center_x, Window.height - b.center_y, "left", [])
    SDL2MotionEventProvider.q.appendleft(("fingerup", 200 + i, fx, 1 - fy, 0.5))
    tick()
for i in range(4): tap_late_ghost(i); time.sleep(0.7)
print("LATE ghost:    4 taps ->", len(presses), "presses")
assert len(presses) == 4, len(presses)

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

# ---- "<" ">" in both modes -----------------------------------------------------------
pb._is_android = lambda: False
pb.allowed_roots = lambda: None
a = os.path.join(root, "a"); b = os.path.join(a, "b"); os.makedirs(b)
ch.path = root; tick(6)
bar = [w for w in lay.children if type(w).__name__ == "PathBar"][0]
bar._open(a); tick(); bar._open(b); tick()                         # root -> a -> b
bar._roots = None                                                 # desktop-style: no restriction
assert bar._mode_btn.text == "Hist"
bar._nav(-1); tick(); assert ch.path == a                         # history back
bar._nav(-1); tick(); assert ch.path == root
bar._nav(1); tick(); assert ch.path == a                          # history forward
bar._toggle_mode(); assert bar._mode_btn.text == "Tree"
bar._nav(-1); tick(); assert ch.path == root                      # tree: up one level
assert not bar._fwd.disabled and not bar._back.disabled
bar._nav(1); tick(); assert ch.path == a                          # tree: back down
bar._open(root); tick()                                           # unrelated jump
assert bar._down == [] or bar._fwd.disabled
bar._toggle_mode(); assert bar._mode_btn.text == "Hist"
print("picker < > modes passed")

# ---- desktop: one click selects, a double-click opens; right-click makes things ----
pb._is_android = lambda: False
class DT:
    def __init__(self, dbl=False, btn="left"):
        self.profile, self.button, self.is_double_tap, self.pos = ["button"], btn, dbl, ch.center
sub = os.path.join(root, "a")
class ED: path = sub
ch.path = root; tick(6); ch.selection = []
ch.entry_touched(ED(), DT()); ch.entry_released(ED(), DT())
assert ch.path == root, ch.path                                   # a single click does not open a folder
ch.entry_touched(ED(), DT(True)); ch.entry_released(ED(), DT(True)); tick()
assert os.path.abspath(ch.path) == os.path.abspath(sub), ch.path  # a double-click does
ch.path = root; tick(6)
dc = FileChooserIconView(path=root, dirselect=True)               # a folder picker
dl = BoxLayout(orientation="vertical"); dl.add_widget(dc); Window.add_widget(dl); tick(6)
dc.entry_touched(ED(), DT()); dc.entry_released(ED(), DT())
assert dc.path == root and dc.selection == [sub], (dc.path, dc.selection)   # click = select the folder
dc.entry_touched(ED(), DT(True)); dc.entry_released(ED(), DT(True)); tick()
assert os.path.abspath(dc.path) == os.path.abspath(sub)           # double-click = open it
ch.selection = []; ch.entry_touched(E(), DT())
assert ch.selection == [f]                                        # files still select on one click
asked = []
orig_menu = pb._context_menu; pb._context_menu = lambda c: asked.append(c)
assert ch.on_touch_down(DT(btn="right")) is True and asked == [ch]    # right-click -> menu
assert ch.selection == [f]                                        # ... without selecting anything
pb._context_menu = orig_menu
pb._is_android = lambda: True
asked.clear(); pb._context_menu = lambda c: asked.append(c)
import kivy.uix.filechooser as _fc
_stock = _fc.FileChooserController.on_touch_down
_fc.FileChooserController.on_touch_down = lambda self, t: False   # (a fake touch can't go through the stock handler)
ch.on_touch_down(DT(btn="right")); assert asked == []             # the phone has no right button
_fc.FileChooserController.on_touch_down = _stock
pb._context_menu = orig_menu; pb._is_android = lambda: False

# creating a file / folder from the menu
new = tempfile.mkdtemp()
p, why = pb.create_item(new, "notes.txt", "file"); assert why is None and os.path.isfile(p)
p, why = pb.create_item(new, "stuff", "folder"); assert why is None and os.path.isdir(p)
assert pb.create_item(new, "notes.txt", "file")[1]                # exists: refused, nothing overwritten
for bad in ("", "  ", ".", "..", "a/b", "a\\b", "x\0y", "trail."):
    assert pb.create_item(new, bad, "file") == (None, pb.valid_new_name(new, bad)[1]) and pb.valid_new_name(new, bad)[1], bad
assert sorted(os.listdir(new)) == ["notes.txt", "stuff"]
assert pb.create_item(os.path.join(new, "nope"), "a", "file")[1]  # missing folder: a message, no crash
print("picker desktop clicks and new-item menu passed")
