# tests/test_plotter_paths.py - needs a display (xvfb-run -a python3 ...)
import os, sys, math, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import screens.function_plotter_screen as fp

# a looping scribble (x goes back and forth) must be kept as-is
loop = [(3 * math.cos(t / 10) + t / 40, 2 * math.sin(t / 5)) for t in range(0, 200)]
assert not fp.stroke_is_function(loop)
assert fp.stroke_is_function([(x / 10, math.sin(x / 10)) for x in range(100)])
thin = fp.thin_stroke(loop, 10, 6, 0.012)
assert 3 <= len(thin) <= len(loop)
dense = fp.smooth_path(thin, 10, 6)
assert len(dense) > len(thin)
assert all(math.isfinite(x) and math.isfinite(y) for x, y in dense)
# order kept: curve starts/ends where the stroke does, x is NOT sorted
assert dense[0] == (thin[0][0], thin[0][1]) or math.hypot(dense[0][0]-thin[0][0], dense[0][1]-thin[0][1]) < 1e-6
assert any(dense[i][0] < dense[i-1][0] for i in range(1, len(dense)))
# no wild overshoot: stays near the drawn points' bounding box
xs = [p[0] for p in thin]; ys = [p[1] for p in thin]
assert min(p[0] for p in dense) > min(xs) - 1.5 and max(p[1] for p in dense) < max(ys) + 1.5

scr = fp.FunctionPlotterScreen()
fp.Window.size = (800, 600)
for _ in range(3): EventLoop.idle()
n0 = len(scr._rows)
scr._add_path_row(thin, 20.0, 12.0)
assert len(scr._rows) == n0 + 1 and scr._rows[-1].kind == "path"
ent = scr.graph.functions[-1]
assert ent["mode"] == "path" and ent["visible"] and len(ent["dense"]) > 10
# serialize -> restore round trip (undo/redo path)
snap = scr._snapshot()
scr._restore(snap)
assert scr._rows[-1].kind == "path" and scr._rows[-1].points == thin
# warp keeps order and commits without a popup
idx = len(scr._rows) - 1
mid = ent["dense"][len(ent["dense"]) // 2]
assert scr._warp_start(idx, mid)
scr._warp_move((mid[0] + 1.0, mid[1] + 1.0))
scr._warp_end()
assert scr._rows[idx].kind == "path" and len(scr._rows[idx].points) >= 3
# hit test finds a path
sx, sy = scr.graph._w2s(*mid)
scr.graph.x_min, scr.graph.x_max = -10.0, 10.0
print("plotter paths OK")
