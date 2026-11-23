# tests/test_cursor_core.py - python3 tests/test_cursor_core.py
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import cursor_core as c

assert c.supported("win32") and not c.supported("linux") and not c.supported("darwin")
d = c.clean({"shape": "nope", "color": "red", "size": 9999, "thickness": 0, "opacity": 5, "visible": "x"})
assert d["shape"] == "ring" and d["color"] == "#FFD400" and d["size"] == 200 and d["thickness"] == 1
assert d["opacity"] == 1.0 and d["visible"] is True and c.clean(None) == c.DEFAULTS
assert c.clean({"color": "#abcdef", "opacity": 0.01})["color"] == "#ABCDEF" and c.clean({"opacity": 0.01})["opacity"] == 0.2
for shape in c.SHAPES:
    cfg = c.clean({"shape": shape, "size": 60, "thickness": 5})
    items = c.shape_items(cfg); n = c.canvas_size(cfg)
    assert items, shape
    for it in items:                                    # everything fits inside the window
        pts = it[1] if it[0] == "poly" else [(it[1], it[2]), (it[3], it[4])]
        for x, y in pts:
            assert -1 <= x <= n + 1 and -1 <= y <= n + 1, (shape, it, n)
    hx, hy = c.hotspot(cfg); assert 0 <= hx <= n and 0 <= hy <= n
assert c.hotspot(c.clean({"shape": "ring"}))[0] == c.canvas_size(c.clean({"shape": "ring"})) // 2
assert c.hotspot(c.clean({"shape": "arrow"}))[0] < 12
assert not c.start()[0] if not c.supported() else True
now = time.time()
import tempfile
c.alive_path = lambda: os.path.join(tempfile.gettempdir(), "srboli_alive_test")
if os.path.exists(c.alive_path()): os.remove(c.alive_path())
assert not c.is_running()
c.touch_alive(); assert c.is_running() and not c.is_running(now + 10)
os.remove(c.alive_path())
cmd = c.launch_cmd(); assert cmd[-1] == "--cursor"
print("cursor core OK")
