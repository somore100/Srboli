# tests/test_studio_screen.py - xvfb-run -a python3 tests/test_studio_screen.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from kivy.clock import Clock
from screens import studio_screen as SS
from core import studio_core as core


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


def near(a, b, e=1.0):
    return abs(a - b) <= e


tmp = tempfile.mkdtemp()
Window.size = (2400, 1500)
scr = SS.StudioScreen()
scr._folder = lambda: tmp                      # never touch the real data folder
Window.add_widget(scr); scr.size = Window.size; Window.canvas.ask_update()
for _ in range(6): Clock.tick()
c, d = scr.canvas_w, scr.doc
assert scr.panel.parent is scr.main and c.width > 300, c.size


def pt(x, y):
    return c.S(x, y)


def drag(a, b, **kw):
    t = T(*a, **kw); c.on_touch_down(t); t.move(*b); c.on_touch_move(t); c.on_touch_up(t)


def tick():
    for _ in range(3): Clock.tick()


# create shapes with the tools
scr.set_tool("rect"); drag(pt(100, 100), pt(300, 250)); tick()
r1 = d.objects[-1]
assert r1["type"] == "shape" and r1["shape"] == "rect" and near(r1["x"], 100) and near(r1["w"], 200) and near(r1["h"], 150), r1
assert c.tool == "select" and c.sel == {r1["id"]}, "tool returns to select, new object selected"
scr.set_tool("ellipse"); drag(pt(400, 100), pt(500, 160)); tick()
e1 = d.objects[-1]
assert e1["shape"] == "ellipse" and near(e1["w"], 100)
scr.set_tool("arrow"); drag(pt(100, 400), pt(300, 350)); tick()
a1 = d.objects[-1]
assert a1["shape"] == "arrow" and near(a1["w"], 200) and near(a1["h"], 50) and a1["fy"] is True and a1["fx"] is False, a1
assert core.line_ends(a1)[1][1] < core.line_ends(a1)[0][1], "head is up-right of the tail"
scr.set_tool("text")
shown = []
c.on_edit_text = lambda o: shown.append(o)
drag(pt(500, 300), pt(500, 300)); tick()
t1 = d.objects[-1]
assert t1["type"] == "text" and shown == [t1], "a new text box opens the editor"
assert t1["h"] > 10 and t1["autofit"], t1
c.on_edit_text = scr.edit_text
scr.set_tool("rounded"); drag(pt(-300, -100), pt(-150, -20)); tick()
assert d.objects[-1]["shape"] == "rounded"

# undo / redo of a creation
n = len(d.objects)
scr.undo(); assert len(d.objects) == n - 1
scr.redo(); assert len(d.objects) == n
r1, e1, a1, t1 = (d.get(o["id"]) for o in (r1, e1, a1, t1))   # undo replaces the dicts

# move is one undo step
scr.set_tool("select"); c.set_sel(())
t = T(*pt(200, 175)); c.on_touch_down(t)
for k in range(1, 6):
    t.move(t.x + 10, t.y); c.on_touch_move(t)
c.on_touch_up(t); tick()
assert near(r1["x"], 150), r1["x"]
scr.undo()
assert near(d.get(r1["id"])["x"], 100)
scr.redo()
r1 = d.get(r1["id"]); assert near(r1["x"], 150)

# resize with the bottom-right handle
c.set_sel([r1["id"]])
o, hs = c._handles()
br = [h for h in hs if h[0] == ("r", 1, 1)][0]
drag(pt(br[1], br[2]), pt(br[1] + 50, br[2] + 30)); tick()
r1 = d.get(r1["id"])
assert near(r1["w"], 250) and near(r1["h"], 180) and near(r1["x"], 150), r1

# turn with the rotate handle (drag to the right of the centre = 90 degrees)
o, hs = c._handles()
rot = [h for h in hs if h[0] == ("rot",)][0]
cx, cy = core.center(r1)
drag(pt(rot[1], rot[2]), pt(cx + 200, cy)); tick()
r1 = d.get(r1["id"])
assert near(r1["rot"], 90, 0.5), r1["rot"]
scr.undo()
assert near(d.get(r1["id"])["rot"], 0, 0.5)

# arrow end handle
c.set_sel([a1["id"]])
o, hs = c._handles()
assert {h[0] for h in hs} == {("end", 0), ("end", 1)}
head = [h for h in hs if h[0] == ("end", 1)][0]
drag(pt(head[1], head[2]), pt(head[1] + 40, head[2] + 40)); tick()
a1 = d.get(a1["id"])
assert near(core.line_ends(a1)[1][0], 340, 1.5), core.line_ends(a1)

# frames adopt what is dropped inside and carry it along
scr.set_tool("frame"); drag(pt(-700, 200), pt(-300, 500)); tick()
fr = d.objects[-1]
assert fr["type"] == "frame" and near(fr["w"], 400) and fr["preset"] == "Custom"
scr.set_tool("rect"); drag(pt(-650, 250), pt(-600, 290)); tick()
inside = d.objects[-1]
assert inside["parent"] == fr["id"], "created inside a frame -> belongs to it"
c.set_sel([fr["id"]])
t = T(*pt(-700, 270)); c.on_touch_down(t)   # the left border, away from the handles
t.move(t.x + 100, t.y + 20); c.on_touch_move(t); c.on_touch_up(t); tick()
assert near(fr["x"], -600) and near(inside["x"], -550), (fr["x"], inside["x"])
# dragging the child out of the frame frees it
c.set_sel(())
t = T(*pt(inside["x"] + 10, inside["y"] + 10)); c.on_touch_down(t)
t.move(t.x + 600, t.y); c.on_touch_move(t); c.on_touch_up(t); tick()
assert inside["parent"] is None, inside

# marquee selects several, group/ungroup, align
c.set_sel(())
c.set_sel([r1["id"], e1["id"]])
scr.group(); tick()
g = [x for x in d.objects if x["type"] == "group"]
assert len(g) == 1 and c.sel == {g[0]["id"]}
t = T(*pt(g[0]["x"] + 5, g[0]["y"] + 5)); hit = d.hit_test(*c.W(t.pos), 3)
assert hit is g[0]
r1, e1, a1, t1 = (d.get(o["id"]) for o in (r1, e1, a1, t1))
d.settings["snap_objects"] = False
x0 = r1["x"]
t = T(*pt(r1["x"] + 100, r1["y"] + 90)); c.on_touch_down(t); t.move(t.x + 20, t.y); c.on_touch_move(t); c.on_touch_up(t)
assert near(d.get(r1["id"])["x"], x0 + 20) and near(d.get(e1["id"])["x"], 420), ("group moves as one", x0, r1["x"], d.get(r1["id"])["x"], d.get(e1["id"])["x"], c._mode, c.sel)
scr.ungroup(); tick()
assert not [x for x in d.objects if x["type"] == "group"] and c.sel == {r1["id"], e1["id"]}
scr.canvas_w.set_sel([r1["id"], e1["id"]])
scr.set_tab("props"); tick()
before_y = (d.get(r1["id"])["y"], d.get(e1["id"])["y"])
scr._edit(lambda: [core.translate_tree(d, o, dx, dy) for o, dx, dy in core.align(core.roots(d, c.sel), "top")])
assert near(d.get(r1["id"])["y"], d.get(e1["id"])["y"], 0.01)

# marquee selection with a real drag
c.set_sel(())
t = T(*pt(-800, -300)); c.on_touch_down(t); t.move(*pt(800, 320)); c.on_touch_move(t); c.on_touch_up(t); tick()
assert {r1["id"], e1["id"]} <= c.sel and fr["id"] not in c.sel, c.sel

# panel tabs and fields
c.set_sel([t1["id"]])
for tab in ("props", "layers", "doc"):
    scr.set_tab(tab); tick()
scr.set_tab("props")
assert "x" in scr._fields and "rot" in scr._fields
scr._apply_geom(t1, "x", "123"); assert near(d.get(t1["id"])["x"], 123, 1e-6)
scr._apply_geom(t1, "w", "abc"); assert near(d.get(t1["id"])["x"], 123, 1e-6)
scr._apply_geom(t1, "w", "2"); assert d.get(t1["id"])["w"] != 2, "too small refused"
scr._set(t1, "text", "# Heading\n- one\n- two"); tick()
scr._set(t1, "size", 30.0)
h_before = t1["h"]
scr._edit(lambda: (t1.__setitem__("text", "# Heading\n- one\n- two\n- three"), SS.refit_text(t1)))
assert t1["h"] > h_before
tex = c._text_texture(t1); assert tex is not None and tex.height > 30
assert "[b]" in SS.markup_for(t1, 1.0) and "•" in SS.markup_for(t1, 1.0)
t1["text"] = "[danger] & [b]"; t1["mode"] = "markdown"
SS.markup_for(t1, 1.0); c._text_texture(t1)                # brackets are escaped, no crash
for ob in list(d.objects):                                 # every property panel builds
    c.set_sel([ob["id"]]); scr.set_tab("props"); tick()
scr.set_tab("layers"); tick()
scr.set_tab("doc"); tick()
scr._setting("grid", False); tick(); assert d.settings["grid"] is False
scr._setting("grid", True)
scr.set_tab("props")

# layers: hide and lock
sel = d.objects[0]
scr._toggle(sel, "visible"); assert not d.get(sel["id"])["visible"]
scr._toggle(sel, "visible")

# keyboard: delete, nudge
c.set_sel([e1["id"]])
x_e = d.get(e1["id"])["x"]
scr._key_down(Window, 275, 0, "", [])
assert near(d.get(e1["id"])["x"], x_e + 1, 1e-6)

# duplicate then delete
n = len(d.objects)
scr.duplicate(); assert len(d.objects) == n + 1 and len(c.sel) == 1
scr.delete(); assert len(d.objects) == n

# zoom and pan
z0 = c.view.zoom
scr.canvas_w.zoom_by(1.25); assert c.view.zoom > z0 and "%" in scr.zoom_label.text
t = T(*pt(0, 0), button="scrollup"); c.on_touch_down(t); assert c.view.zoom > z0 * 1.25
scr.set_tool("pan"); ox = c.view.ox
t = T(300, 300); c.on_touch_down(t); t.move(350, 300); c.on_touch_move(t); c.on_touch_up(t)
assert c.view.ox < ox, "dragging right moves the picture right"
scr.set_tool("select")
a, b = T(300, 300), T(400, 300)
c.on_touch_down(a); c.on_touch_down(b)
a.move(250, 300); c.on_touch_move(a); b.move(450, 300); c.on_touch_move(b)
a.move(200, 300); c.on_touch_move(a); b.move(500, 300); c.on_touch_move(b)
c.on_touch_up(a); c.on_touch_up(b)
assert c._mode is None
c.fit(); assert c.view.zoom > 0

# save, recovery, open
path = os.path.join(tmp, "work")
scr._write(path)
assert os.path.exists(path + core.__dict__.get("EXT", ".srbcanvas")) and not scr.dirty
assert not core.has_recovery(tmp)
count = len(d.objects)
scr._edit(lambda: d.add(core.make("shape")))
scr._autosave(); assert core.has_recovery(tmp)
scr.load(path + ".srbcanvas")
assert len(scr.doc.objects) == count and not scr.dirty and scr.path.endswith(".srbcanvas")
# a damaged file falls back to the .bak copy
scr._write(path); scr._write(path)
open(path + ".srbcanvas", "wb").write(b"junk")
scr.load(path + ".srbcanvas")
assert len(scr.doc.objects) == count and "previous copy" in scr.hint_label.text, scr.hint_label.text
open(path + ".srbcanvas.bak", "wb").write(b"junk")
scr.load(path + ".srbcanvas")
assert "Could not open" in scr.hint_label.text

# new workspace resets
scr.dirty = False; scr.new_doc()
assert not scr.doc.objects and scr.path is None and c.doc is scr.doc
assert scr.title_label.text.startswith("[b]Untitled")

# narrow layout puts the panel under the canvas
Window.size = (600, 800); scr.size = Window.size; tick()
assert scr.panel.parent is not scr.main
scr.toggle_panel(); tick()
assert scr.panel.parent is scr.center_col
Window.size = (2400, 1500); scr.size = Window.size; tick()
assert scr.panel.parent is scr.main

print("studio screen OK")
