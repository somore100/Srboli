# tests/test_precision_canvas_screen.py - xvfb-run -a python3 tests/test_precision_canvas_screen.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from kivy.clock import Clock
from screens.precision_canvas_screen import PrecisionCanvasScreen
from core import precision_canvas_core as pc


class T:
    _n = 0
    def __init__(self, x, y, button="left"):
        T._n += 1
        self.uid = T._n; self.pos = (x, y); self.x, self.y = x, y; self.dx = self.dy = 0
        self.button = button; self.is_double_tap = False
    def grab(self, w): pass
    def ungrab(self, w): pass
    def move(self, x, y):
        self.dx, self.dy = x - self.x, y - self.y
        self.pos = (x, y); self.x, self.y = x, y


Window.size = (1300, 800)
sc = PrecisionCanvasScreen()
Window.add_widget(sc); sc.size = Window.size; Window.canvas.ask_update()
for _ in range(6): Clock.tick()
assert sc.inspector.parent is sc.main
c, d = sc.canvas_w, sc.doc
assert c.width > 200 and c.height > 200, c.size


def drag(a, b, **kw):
    t = T(*a, **kw); c.on_touch_down(t); t.move(*b); c.on_touch_move(t); c.on_touch_up(t)


def to_screen(x, y):
    sx, sy = c.S(x, y); return sx, sy

# draw a line with a drag: snaps to grid, angle-locks, one undo step
sc.set_tool("line")
drag(to_screen(20, 20), to_screen(101, 43))
assert len(d.objects) == 1 and d.objects[0]["type"] == "line", d.objects
ln = d.objects[0]
assert (ln["x1"], ln["y1"]) == (20, 20) and abs(pc.get_field(ln, "angle") - 15) < 1e-6, ln
sc.undo(); assert not d.objects
sc.redo(); assert len(d.objects) == 1

# shapes
sc.set_tool("circle"); drag(to_screen(200, 200), to_screen(240, 200))
assert d.objects[-1]["type"] == "circle" and abs(d.objects[-1]["r"] - 40) < 1e-6
sc.set_tool("rect"); drag(to_screen(300, 100), to_screen(380, 160))
assert d.objects[-1]["w"] == 80 and d.objects[-1]["h"] == 60
sc.set_tool("polygon"); drag(to_screen(400, 300), to_screen(400, 340))
assert d.objects[-1]["n"] == 6
sc.set_tool("point"); drag(to_screen(60, 300), to_screen(60, 300))
assert d.objects[-1]["type"] == "point"
n = len(d.objects)
sc.set_tool("polyline")
for p in ((100, 400), (160, 400), (160, 460)):
    t = T(*to_screen(*p)); c.on_touch_down(t); c.on_touch_up(t)
t = T(*to_screen(160, 460)); t.is_double_tap = True; c.on_touch_down(t); c.on_touch_up(t)
assert len(d.objects) == n + 1 and len(d.objects[-1]["points"]) == 3, d.objects[-1]
sc.set_tool("freehand")
drag(to_screen(500, 100), to_screen(560, 160))
assert d.settings["mode"] == "free" and d.objects[-1]["type"] == "freehand"
d.settings["mode"] = "strict"

# select, move (one undo step), inspector edit with maths
sc.set_tool("select")
circ = [o for o in d.objects if o["type"] == "circle"][0]
before = circ["cx"]
t = T(*to_screen(240, 200)); c.on_touch_down(t)
for k in range(1, 6):
    t.move(t.x + 8, t.y); c.on_touch_move(t)
c.on_touch_up(t)
assert circ["id"] in c.sel and circ["cx"] != before, circ
moved = circ["cx"]; sc.undo(); assert sc.doc.get(circ["id"])["cx"] == before
sc.redo()
circ = d.get(circ["id"])
sc._apply(circ, "r", "2*10")
assert circ["r"] == 20
sc._apply(circ, "r", "-4"); assert circ["r"] == 20            # refused
sc._apply(circ, "r", "1/0"); assert circ["r"] == 20
sc.set_tab("maths"); assert len(sc.panel.children) > 3
sc.set_tab("layers"); sc.set_tab("doc"); sc.set_tab("props")

# marquee select all, align, delete, copy / paste, duplicate
sc.set_tool("select")
c.set_sel([o["id"] for o in d.objects]); assert len(c.sel) == len(d.objects)
sc.copy(); k = len(d.objects); sc.paste(); assert len(d.objects) == 2 * k
sc.undo(); assert len(d.objects) == k
c.set_sel([d.objects[0]["id"]]); sc.duplicate(); assert len(d.objects) == k + 1
sc.delete(); assert len(d.objects) == k

# zoom keeps the point under the cursor; pan; pinch
b = c.view.to_doc(300, 300); zb = c.view.zoom
t = T(c.x + 300, c.y + 300, "scrollup"); c.on_touch_down(t)
a = c.view.to_doc(300, 300); assert abs(a[0] - b[0]) < 1e-6 and c.view.zoom > zb
ox = c.view.ox; sc.set_tool("pan"); drag((c.x + 50, c.y + 50), (c.x + 90, c.y + 50)); assert c.view.ox > ox
sc.set_tool("select")
t1, t2 = T(c.x + 100, c.y + 100), T(c.x + 200, c.y + 100)
c.on_touch_down(t1); c.on_touch_down(t2)
z0 = c.view.zoom
t2.move(c.x + 210, c.y + 100); c.on_touch_move(t2); t2.move(c.x + 300, c.y + 100); c.on_touch_move(t2)
c.on_touch_up(t1); c.on_touch_up(t2)
assert c.view.zoom > z0 and not c._touches

# layers, document settings, narrow layout
o = d.objects[0]; sc._edit(lambda: o.__setitem__("visible", False)); sc.undo(); assert sc.doc.get(o["id"])["visible"]
sc._set_setting("grid_spacing", 10.0); assert d.settings["grid_spacing"] == 10
Window.size = (500, 700)
for _ in range(5): Clock.tick()
sc.size = Window.size; sc._relayout(); assert sc._narrow and sc.inspector.parent is None
sc.toggle_panel(); assert sc.inspector.parent is sc.center_col
sc.toggle_panel(); Window.size = (1300, 800)
for _ in range(5): Clock.tick()
sc.size = Window.size; sc._relayout(); assert sc.inspector.parent is sc.main

# save / open / export through temp files (never the real data folder)
tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "t.srbd"); sc._write(path)
assert not sc.dirty and sc.path == path
sc2 = len(d.objects); sc._reset(); assert not d.objects if False else not sc.doc.objects
sc.load(path); assert len(sc.doc.objects) == sc2 and not sc.dirty
sc.load(os.path.join(tmp, "missing.srbd")); assert "Could not open" in sc.hint_label.text
with open(os.path.join(tmp, "x.svg"), "w") as f: f.write(pc.to_svg(sc.doc))
print("precision canvas screen OK")
