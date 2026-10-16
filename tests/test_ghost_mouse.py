# tests/test_ghost_mouse.py - needs a display (xvfb-run -a python3 ...)
# One physical tap = SDL finger touch + synthesised mouse touch. With the mouse
# provider set up the way main.py configures it, a widget must see ONE press.
import os, re, sys, time
os.environ["KIVY_NO_ARGS"] = "1"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
cfg = re.search(r'Config\.set\("input", "mouse", "([^"]+)"\)', open(os.path.join(ROOT, "main.py")).read()).group(1)
assert "disable_on_activity" in cfg, cfg
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.input.providers.mouse import MouseMotionEventProvider
from kivy.core.window.window_sdl2 import SDL2MotionEventProvider

def tick(n=3):
    for _ in range(n): EventLoop.idle()

mp = MouseMotionEventProvider("mouse", cfg)
EventLoop.add_input_provider(mp, True); mp.start()
P, R = [], []
b = Button(size_hint=(None, None), size=(200, 100), pos=(100, 100))
b.bind(on_press=lambda *a: P.append(1), on_release=lambda *a: R.append(1))
Window.add_widget(b); tick(5)

def tap(i, hold):
    fx, fy = b.center_x / Window.width, b.center_y / Window.height
    SDL2MotionEventProvider.q.appendleft(("fingerdown", 100 + i, fx, 1 - fy, 0.5)); tick(1)
    Window.dispatch("on_mouse_down", b.center_x, Window.height - b.center_y, "left", []); tick()
    time.sleep(hold)
    SDL2MotionEventProvider.q.appendleft(("fingerup", 100 + i, fx, 1 - fy, 0.5)); tick(1)
    Window.dispatch("on_mouse_up", b.center_x, Window.height - b.center_y, "left", []); tick()

for i in range(5): tap(i, 0.05); time.sleep(0.25)
print("5 taps ->", len(P), "presses", len(R), "releases")
assert len(P) == 5 and len(R) == 5 and not EventLoop.touches
# a real mouse click (no finger active) must still work
P.clear()
Window.dispatch("on_mouse_down", b.center_x, Window.height - b.center_y, "left", []); tick()
Window.dispatch("on_mouse_up", b.center_x, Window.height - b.center_y, "left", []); tick()
assert len(P) == 1, "real mouse click broken"
print("OK")
