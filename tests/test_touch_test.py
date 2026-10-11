# tests/test_touch_test.py - needs a display (xvfb-run -a python3 tests/test_touch_test.py)
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import core.touch_dedupe as td

# --- persisted switch + self-healing -------------------------------------
assert td.load_cfg() == {"enabled": False, "pending": False}      # default OFF
assert td.decide_at_startup() is False                            # stays off
td.set_enabled(True)
assert td.decide_at_startup() is True                             # starts, marks pending
assert td.load_cfg()["pending"] is True
# app "froze": no button ever reacted -> next start must disable itself
logs = []
assert td.decide_at_startup(logs.append) is False
assert td.load_cfg() == {"enabled": False, "pending": False} and logs
# healthy run: pending cleared once a button reacts
td.set_enabled(True); assert td.decide_at_startup() is True
td.mark_healthy(); assert td.load_cfg() == {"enabled": True, "pending": False}
assert td.decide_at_startup() is True                             # still on next time
td.set_enabled(False)

# --- the screen ---------------------------------------------------------------
from screens.touch_test_screen import TouchTestScreen
from kivy.uix.screenmanager import ScreenManager
from kivy.core.window import Window
from kivy.input.providers.mouse import MouseMotionEvent
sm = ScreenManager(); s = TouchTestScreen(name="touch_test"); sm.add_widget(s)
Window.add_widget(sm)
for _ in range(5): Clock.tick()
pad = s._pad
cx, cy = pad.center
def fake(device, x, y):
    t = MouseMotionEvent(device, 1, (x / Window.width, y / Window.height))
    t.device = device
    t.scale_for_screen(Window.width, Window.height)
    return t
import time
for i in range(4):                       # 4 taps, each arriving twice
    pad.on_touch_down(fake("sdl", cx, cy)); pad.on_touch_down(fake("mouse", cx, cy + 5))
    time.sleep(0.4)
print(s._summary.text.replace("\n", " | "))
assert s._taps == 4 and s._touches == 8 and "DUPLICATE" in s._summary.text
s._clear(); assert s._taps == 0
for i in range(4):                       # clean taps
    pad.on_touch_down(fake("sdl", cx, cy)); time.sleep(0.4)
assert "looks fine" in s._summary.text
s._toggle_filter(); assert td.load_cfg()["enabled"] is True
print("touch test passed")
