# tests/test_studio_data_screen.py - xvfb-run -a python3 tests/test_studio_data_screen.py  (kivy screens.)
import os, struct, sys, tempfile, zlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.popup import Popup
from screens import studio_screen as SS
from core import studio_core as core
from core import studio_data as sd


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


def png(w, h):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def popups():
    return [w for w in Window.children if isinstance(w, Popup)]


tmp = tempfile.mkdtemp()
Window.size = (2400, 1500)
scr = SS.StudioScreen()
scr._folder = lambda: tmp
Window.add_widget(scr); scr.size = Window.size; Window.canvas.ask_update()
for _ in range(6): Clock.tick()
c, d = scr.canvas_w, scr.doc


def tick():
    for _ in range(3): Clock.tick()


def drag(a, b):
    t = T(*a); c.on_touch_down(t); t.move(*b); c.on_touch_move(t); c.on_touch_up(t)


# table tool, then a chart tool with the table selected links to it
scr.set_tool("table"); drag(c.S(-600, -300), c.S(-200, -120)); tick()
tb = d.objects[-1]
assert tb["type"] == "table" and abs(tb["w"] - 400) < 1 and c.tool == "select"
scr.set_tool("chart"); drag(c.S(0, -300), c.S(300, -50)); tick()
ch = d.objects[-1]
assert ch["type"] == "chart" and ch["source"] == tb["id"], ch["source"]
assert ch["data"]["labels"] == ["North", "South", "West"]
scr.set_tool("chart"); c.set_sel(()); drag(c.S(400, -300), c.S(600, -100)); tick()
free = d.objects[-1]
assert free["source"] is None and free["data"]["labels"] == ["A", "B", "C", "D"]

# editing the table updates the chart
scr._edit(lambda: sd.set_cell(tb, 1, 1, "40"))
assert d.get(ch["id"])["data"]["series"][0][0] == 40

# every kind draws, every panel builds
for kind in sd.CHART_KINDS:
    scr._set(d.get(ch["id"]), "kind", kind); tick()
    scr._set(d.get(free["id"]), "kind", kind); tick()
for ob in list(d.objects):
    c.set_sel([ob["id"]]); scr.set_tab("props"); tick()
scr.set_tab("props")

# table panel buttons
tb = d.get(tb["id"])
c.set_sel([tb["id"]]); tick()
n = len(tb["cells"])
scr._fields["t_row"].text = "2"; scr._fields["t_col"].text = "B"
scr._table_do(tb, {}, "row+"); assert len(tb["cells"]) == n + 1
scr._fields["t_row"].text = "3"
scr._table_do(tb, {}, "row-"); assert len(tb["cells"]) == n
scr._table_do(tb, {}, "col+"); assert len(tb["cells"][0]) == 4
scr._fields["t_col"].text = "C"
scr._table_do(tb, {}, "col-"); assert len(tb["cells"][0]) == 3
scr._fields["t_col"].text = "A"
scr._table_do(tb, {}, "desc"); assert [r[0] for r in tb["cells"][1:]] == ["West", "South", "North"], tb["cells"]
scr._fields["t_col"].text = "Z"
scr._table_do(tb, {}, "col+"); assert "does not exist" in scr.hint_label.text
scr._fields["t_col"].text = "A"
scr._fields["t_filter"].text = "so"; scr._fields["t_filter"].dispatch("on_text_validate")
tb = d.get(tb["id"])
assert tb["ftext"] == "so" and tb["fcol"] == 0 and sd.visible_rows(tb) == [0, 2], (tb["ftext"], tb["fcol"])
assert d.get(ch["id"])["data"]["labels"] == ["South"], "chart follows the filter"
scr._edit(lambda: (tb.__setitem__("ftext", ""), tb.__setitem__("fcol", -1)))

# paste data replaces the table, errors are shown
scr._apply_cells(tb, sd.parse_table_text("a,b,c,d\n1,2,3,4\n5,6,7,8"))
tb = d.get(tb["id"])
assert len(tb["cells"]) == 3 and len(tb["cells"][0]) == 4 and tb["fcol"] == -1
scr.paste_dialog(tb); tick()
assert popups(); popups()[0].dismiss(); tick()
scr.edit_table(tb); tick()
assert popups(); popups()[0].dismiss(); tick()

# own chart data from pasted cells
fr = d.get(free["id"])
scr._apply_chart_cells(fr, sd.parse_table_text("x,s1,s2\np,1,2\nq,3,4"))
fr = d.get(free["id"])
assert fr["data"]["labels"] == ["p", "q"] and fr["data"]["names"] == ["s1", "s2"] and fr["data"]["series"][1] == [2, 4]

# csv export / import
out = os.path.join(tmp, "t.csv")
scr._chooser_popup = lambda title, save, cb, default_name="", exts=(), start=None: cb(out)
scr.export_csv(tb)
assert open(out).read().startswith("a,b,c,d\n1,2,3,4")
open(out, "w").write("k;v\nx;1\ny;2\n")
scr.import_csv(tb)
assert d.get(tb["id"])["cells"] == [["k", "v"], ["x", "1"], ["y", "2"]]

# text markup is really interpreted (a regression: raw [b] tags once showed on screen)
tx = core.make("text", text="**x**", size=24.0)
d.add(tx)
from kivy.core.text.markup import MarkupLabel
assert isinstance(SS._core_label(tx, 1.0), MarkupLabel)   # a plain label would print the tags

# pictures
img_path = os.path.join(tmp, "pic.png")
open(img_path, "wb").write(png(40, 20))
scr.add_image(img_path); tick()
im = d.objects[-1]
assert im["type"] == "image" and im["w"] == 40 and im["h"] == 20 and "pic.png" in d.assets
assert c._asset_texture("pic.png") is not None, "the picture decodes"
im["h"] = 99
scr._image_props(im)
open(os.path.join(tmp, "bad.png"), "wb").write(b"nope")
scr.add_image(os.path.join(tmp, "bad.png")); assert "Could not add" in scr.hint_label.text
assert d.objects[-1] is im
scr.add_image(os.path.join(tmp, "missing.png")); assert "Could not add" in scr.hint_label.text
c.set_sel([im["id"]]); scr.set_tab("props"); tick()

# save and reopen keeps everything
path = os.path.join(tmp, "all")
scr._write(path)
scr.load(path + ".srbcanvas")
kinds = sorted(o["type"] for o in scr.doc.objects)
assert kinds.count("image") == 1 and kinds.count("chart") == 2 and kinds.count("table") == 1, kinds
assert "pic.png" in scr.doc.assets and scr.canvas_w._asset_texture("pic.png") is not None
tick()
print("studio data screen OK")
