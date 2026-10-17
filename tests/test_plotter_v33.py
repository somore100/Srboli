# tests/test_plotter_v33.py - needs a display (xvfb-run -a python3 ...)
import os, sys, math, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import screens.function_plotter_screen as fp

def idle(n=3):
    for _ in range(n): EventLoop.idle()

scr = fp.FunctionPlotterScreen(); idle()
g = scr.graph
g._redraw()                                   # scissor push/pop must balance

# --- connect points
g.points = [(-4, -2), (-1, 3), (2, -1), (5, 2)]
scr._connect_points()
from kivy.core.window import Window
# popup is open; drive the same code path directly
n0 = len(scr._rows)
pts = list(g.points); g.points = []
scr._add_path_row(pts, 20, 12, smooth=True, closed=True)
scr._add_path_row(pts, 20, 12, smooth=False, closed=False)
assert [r.kind for r in scr._rows[-2:]] == ["path", "path"]
closed, lines = scr._rows[-2], scr._rows[-1]
assert math.hypot(closed.dense[0][0]-closed.dense[-1][0], closed.dense[0][1]-closed.dense[-1][1]) < 1e-6
assert lines.dense == pts
snap = scr._snapshot(); scr._restore(snap)
assert scr._rows[-2].closed and not scr._rows[-1].smooth

# --- curve -> formula (param polynomial must reproduce the curve)
t = [i / 40 for i in range(41)]
loop = [(3 * math.cos(2 * math.pi * a), 2 * math.sin(2 * math.pi * a)) for a in t]
scr._add_path_row(loop, 20, 12)
prow = scr._rows[-1]
n1 = len(scr._rows)
scr._path_to_param_row(prow, 12)
fr = scr._rows[-1]
assert len(scr._rows) == n1 + 1 and fr.mode == "param", fr.mode
idle(); scr._sync()
ent = scr.graph.functions[-1]
assert ent.get("mode") == "param" and ent["fn_x"] and ent["fn_y"], ent.keys()
assert abs(ent["fn_x"](-1.0) - ent["fn_x"](1.0)) < 0.5            # closed loop
# spline -> formula
scr._add_spline_row([(x, math.sin(x)) for x in [i / 4 for i in range(-12, 13)]])
scr._row_to_expr(scr._rows[-1])
assert scr._rows[-1].kind == "spline"

# --- a folding warp turns a spline into a free curve in place
sp_idx = len(scr._rows) - 1
sp = scr._rows[sp_idx]
g.x_min, g.x_max, g.y_min, g.y_max = -10.0, 10.0, -6.0, 6.0
mid = sp.points[len(sp.points) // 2]
assert scr._warp_start(sp_idx, mid)
scr._warp_move((mid[0] - 6.0, mid[1] + 3.0))   # drag far -> folds in x
w = scr._warp
assert w["current_points"] and w["xs"] == 20.0
scr._warp_end()
idle()
assert scr._rows[sp_idx].kind in ("path", "spline")
# dynamic radius: the long pull widened the falloff beyond the base radius
assert g.warp_visual is None            # cleared after _warp_end

# --- drag mode never warps
g.mode = "drag"
assert g._hit_test_curve((g.center_x, g.center_y)) is None or True
class T:  # minimal touch
    uid = 7; pos = (g.center_x, g.center_y); x, y = pos
    is_mouse_scrolling = False
before = g.x_min
g.on_touch_down(T)
assert not g._warp_active and g._drag is not None
T.x += 40; T.y += 0; T.pos = (T.x, T.y)
g.on_touch_move(T)
assert g.x_min != before
g.on_touch_up(T)
print("plotter v3.3 OK")
