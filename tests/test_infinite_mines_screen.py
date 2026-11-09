# tests/test_infinite_mines_screen.py - needs a display (xvfb-run -a python3 tests/test_infinite_mines_screen.py)
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
from core import infinite_mines_core as im
import screens.infinite_mines_screen as ims

tmp = os.path.join(tempfile.mkdtemp(), "world.json")
ims.save_path = lambda: tmp                              # never touch the real data folder

def tick(n=3):
    for _ in range(n): Clock.tick()

s = ims.InfiniteMinesScreen(name="i"); tick()
m = s.map; m.size = (420, 640); m.pos = (0, 0); m.redraw()
assert s.world.dug > 0 and len(m.canvas.children) > 30
assert "Points 0" in s.status.text and "Dug" in s.status.text

# coordinates: the middle of the map is the middle of cell (0, 0) at the start
assert m.cell_at(*m.center) == (0, 0)
assert m.cell_at(*m.pos_of(5, -3)) == (5, -3)
m.cx, m.cy = 10.5, -4.5; assert m.cell_at(*m.center) == (10, -5)
m.go_home(); assert m.cell_at(*m.center) == (0, 0)

# zoom keeps the point under the finger, and stays in range
anchor = m.pos_of(4, 4); before = m.cell_at(*anchor)
m.zoom_by(1.5, anchor); assert m.cell_at(*anchor) == before
for _ in range(30): m.zoom_by(1.3)
assert m.zoom == ims.MAX_ZOOM
for _ in range(60): m.zoom_by(1 / 1.3)
assert m.zoom == ims.MIN_ZOOM
m.zoom = 1.0; m.go_home(); m.redraw()

# modes and actions
s.mode_btns["flag"].dispatch("on_release"); assert m.mode == "flag"
out = m.act(m.pos_of(30, 30), "flag"); assert out.kind == "flag" and s.world.view(30, 30) == im.FLAG
out = m.act(m.pos_of(30, 30), "dig"); assert out.kind == "flagged" and "flag" in s.msg.text
m.act(m.pos_of(30, 30), "flag"); assert s.world.view(30, 30) == im.HIDDEN
s.mode_btns["dig"].dispatch("on_release"); assert m.mode == "dig"

# a blast shows up in the message, the status line and on the canvas
w = s.world
mx = next(x for x in range(20, 200) if w.is_mine(x, 0))
m.cx, m.cy = mx + 0.5, 0.5; m.redraw()
out = m.act(m.pos_of(mx, 0), "dig")
assert out.kind == "blast" and "BOOM" in s.msg.text and "Craters 1" in s.status.text
assert w.view(mx, 0) == im.CRATER
n = len(m.canvas.children)
out = m.act(m.pos_of(mx, 0), "dig"); assert out.kind == im.CRATER and "crater" in s.msg.text
sx, sy = next(iter(w.scorch)); m.act(m.pos_of(sx, sy), "dig"); assert "Scorched" in s.msg.text
m.act(m.pos_of(sx, sy), "repair"); assert "costs" in s.msg.text and (sx, sy) in w.scorch
w.points = 9
m.act(m.pos_of(sx, sy), "repair"); assert "Repaired" in s.msg.text and (sx, sy) not in w.scorch
m.zoom = 0.5; m.cx, m.cy = 0.5, 0.5; m.redraw()           # zoomed far out still draws

# touch: one finger arrives twice on Android (finger + mouse). It must stay ONE
# finger: a tap acts once, a drag pans, a hold flags - never a phantom pinch.
import time
class FT:
    n = 0
    def __init__(self, dev, x, y):
        FT.n += 1
        self.uid, self.device, self.x, self.y = FT.n, dev, x, y
        self.pos, self.dx, self.dy = (x, y), 0, 0
        self.is_mouse_scrolling, self.ud, self.grab_current = False, {}, None
    def grab(self, w): self.grab_current = w
    def ungrab(self, w): self.grab_current = None
    def go(self, x, y):
        self.dx, self.dy, self.x, self.y, self.pos = x - self.x, y - self.y, x, y, (x, y)
m.zoom = 1.0; m.cx = m.cy = 40.5; m.mode = "flag"            # look at cell 40, far from the opened start
px, py = m.pos_of(40, 40)
f, g = FT("sdl", px, py), FT("mouse", px, py)
m.on_touch_down(f); m.on_touch_down(g)
assert len(m._touches) == 1 and m._pinch is None            # the ghost is not a second finger
m.on_touch_up(g); m.on_touch_up(f)
assert s.world.view(40, 40) == im.FLAG                      # flagged once, not toggled back off
f, g = FT("sdl", px, py), FT("mouse", px, py)
m.on_touch_down(g); m.on_touch_down(f)                      # the ghost may also come first
m.on_touch_up(f); m.on_touch_up(g)
assert s.world.view(40, 40) == im.HIDDEN                    # a second real tap toggles it off
m.mode = "dig"
f, g = FT("sdl", px, py), FT("mouse", px, py)
m.on_touch_down(f); m.on_touch_down(g)
f.go(px + 120, py + 60); g.go(px + 120, py + 60)
m.on_touch_move(f); m.on_touch_move(g)
assert m.cx < 40.5 and m.cy < 40.5                            # dragging pans (the world follows the finger)
m.on_touch_up(g); m.on_touch_up(f)
assert s.world.view(40, 40) == im.HIDDEN                    # and a drag is not a tap
m.cx = m.cy = 41.5
px, py = m.pos_of(41, 41)
f, g = FT("sdl", px, py), FT("mouse", px, py)
m.on_touch_down(f); m.on_touch_down(g)
assert f.ud.get("lp") is not None                           # the hold timer is running
m._long(f)                                                  # (what the timer calls; a tick would re-lay out the map)
m.on_touch_up(g); m.on_touch_up(f)
assert s.world.view(41, 41) == im.FLAG                      # holding in Dig mode flags
m.cx = m.cy = 41.5
a, b2 = FT("sdl", m.center_x - 60, m.center_y), FT("sdl", m.center_x + 60, m.center_y)
z0 = m.zoom
m.on_touch_down(a); m.on_touch_down(b2)
assert len(m._touches) == 2                                 # two real fingers still pinch
a.go(m.center_x - 120, m.center_y); b2.go(m.center_x + 120, m.center_y)
m.on_touch_move(a); m.on_touch_move(b2)
assert m.zoom > z0
m.on_touch_up(a); m.on_touch_up(b2)
m.zoom = 1.0; m.go_home(); m.redraw(); s.world.toggle_flag(41, 41)

# saving: leaving writes the file and a second screen picks the same world up
s.on_leave(); assert os.path.exists(tmp)
t = ims.InfiniteMinesScreen(name="j"); tick()
assert t.world.seed == w.seed and t.world.craters == w.craters and t.world.points == w.points

# New world needs two taps
seed = s.world.seed
s._new_press(); assert s.world.seed == seed and "Sure" in s.new_btn.text
s._new_press(); assert s.world.seed != seed and s.new_btn.text == "New world" and not s.world.craters
print("infinite mines screen OK")
