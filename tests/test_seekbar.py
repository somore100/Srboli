# tests/test_seekbar.py - needs a display (xvfb-run -a python3 tests/test_seekbar.py)
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from core.seekbar import SeekBar, tick_step

assert tick_step(60) == 10 and tick_step(180) == 30 and tick_step(3600) == 300
assert tick_step(10 ** 6) == 3600

bar = SeekBar(pos=(0, 0), size=(400, 44))
bar.max = 200
assert bar.value_at(bar.x + bar._pad) == 0                    # left end
assert abs(bar.value_at(bar.x + bar.width - bar._pad) - 200) < 1e-6
assert bar.value_at(-50) == 0 and bar.value_at(5000) == 200   # clamped
mid = bar.x + bar.width / 2
assert abs(bar.value_at(mid) - 100) < 1e-6

class T:                                   # minimal touch
    def __init__(self, x, y): self.x, self.y, self.pos = x, y, (x, y); self.grab_current = None
    def grab(self, w): self.grab_current = w
    def ungrab(self, w): self.grab_current = None

scrubs, seeks = [], []
bar.bind(on_scrub=lambda b, v: scrubs.append(v), on_seek=lambda b, v: seeks.append(v))
t = T(mid, 22)
assert bar.on_touch_down(t) and bar.scrubbing
t.x = bar.x + bar.width - bar._pad; t.pos = (t.x, 22)
bar.on_touch_move(t)
assert not seeks                                       # nothing until release
assert bar.on_touch_up(t) and not bar.scrubbing
assert len(seeks) == 1 and abs(seeks[0] - 200) < 1e-6 and len(scrubs) >= 2
idle = T(mid, 22)
bar.max = 0
assert not bar.on_touch_down(idle)                     # no track: ignores touches
print("seekbar OK")
