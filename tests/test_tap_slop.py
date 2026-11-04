# tests/test_tap_slop.py - needs a display (xvfb-run -a python3 tests/test_tap_slop.py)
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.core.window import Window
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from core import tap_slop
tap_slop.install(); tap_slop.install()       # idempotent

def touch(x, y):
    t = MouseMotionEvent("mouse", 1, (x / Window.width, y / Window.height))
    t.scale_for_screen(Window.width, Window.height)
    return t

def gesture(btn, dx, dy):
    """press in the middle of btn, move by (dx, dy), lift."""
    cx, cy = btn.center
    t = touch(cx, cy)
    btn.on_touch_down(t)
    t.move(((cx + dx) / Window.width, (cy + dy) / Window.height))
    t.scale_for_screen(Window.width, Window.height)
    t.grab_current = btn
    btn.on_touch_move(t)
    btn.on_touch_up(t)
    t.grab_current = None

def make(cls=Button):
    b = cls(pos=(100, 100), size=(200, 120))
    hits = []
    b.bind(on_release=lambda *a: hits.append(1))
    return b, hits

b, hits = make(); gesture(b, 0, 0); assert hits == [1], "a plain tap still clicks"
b, hits = make(); gesture(b, 3, 3); assert hits == [1], "a little jitter still clicks"
b, hits = make(); gesture(b, 0, 40); assert hits == [], "a drag that ends on the button is no click"
assert b.state == "normal"
b, hits = make(); gesture(b, 0, 300); assert hits == [], "a drag off the button is no click"
print("tap slop OK")
