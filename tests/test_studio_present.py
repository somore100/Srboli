# tests/test_studio_present.py - xvfb-run -a python3 tests/test_studio_present.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from kivy.clock import Clock
from screens import studio_screen as SS
from core import studio_core as core
from core import studio_export as se


class T:
    def __init__(self, x, y, button="left"):
        self.pos = (x, y); self.x, self.y = x, y; self.button = button; self.uid = 1
        self.dx = self.dy = 0; self.is_double_tap = False
    def grab(self, w): pass
    def ungrab(self, w): pass


tmp = tempfile.mkdtemp()
Window.size = (1500, 900)
scr = SS.StudioScreen(); scr._folder = lambda: tmp
Window.add_widget(scr); scr.size = Window.size
for _ in range(6): Clock.tick()
d = scr.doc


def tick():
    for _ in range(4): Clock.tick()


scr.present()
assert "Draw a frame first" in scr.hint_label.text and scr._popups == 0
scr.export_dialog(); assert "Nothing to export" in scr.hint_label.text

f1 = d.add(core.make("frame", x=0, y=0, w=640.0, h=360.0, bg="#FFFFFF"))
f2 = d.add(core.make("frame", x=1000, y=0, w=400.0, h=400.0, bg="#223355"))
t = d.add(core.make("text", x=1040, y=40, text="# Slide two", color="#FFFFFF"), parent=f2["id"])
d.add(core.make("shape", x=50, y=50, w=100, h=80, fill="#FF0000"), parent=f1["id"])
d.add(core.make("shape", x=5000, y=5000))                     # outside every slide
scr.canvas_w.set_sel([t["id"]]); tick()

scr.present(); tick()
show = scr._show
assert scr._popups == 1 and show.i == 1, (scr._popups, show.i, scr.canvas_w.sel)
cv = show.cv
assert cv.only == {f2["id"], t["id"]}, cv.only
b = core.bbox(f2)
x0, y0 = cv.view.to_screen(b[0], b[3]); x1, y1 = cv.view.to_screen(b[2], b[1])
assert abs((x1 - x0) - 400 * cv.view.zoom) < 1 and cv.view.zoom > 0
# the frame fills the height (letterboxed): zoom = height / 400
assert abs(cv.view.zoom - cv.height / 400) < 1e-6 or abs(cv.view.zoom - cv.width / 400) < 1e-6
cv.on_touch_down(T(cv.x + 5, cv.y + 5)); assert show.i == 0, "tap on the left goes back"
cv.on_touch_down(T(cv.right - 5, cv.y + 5)); assert show.i == 1
cv.on_touch_down(T(cv.right - 5, cv.y + 5)); assert show.i == 1, "stops on the last slide"
cv.on_touch_down(T(cv.x + 50, cv.y + 50, "scrollup")); assert show.i == 0
show._key(Window, 275); assert show.i == 1
show._key(Window, 278); assert show.i == 0
show._key(Window, 279); assert show.i == 1
show._key(Window, 276); assert show.i == 0
assert "1 / 2" in show.count.text
show._key(Window, 27); tick()
assert scr._popups == 0

# export
t0 = scr.export_slides(se.slides(d), "png", 1.0)
files = sorted(os.listdir(t0))
assert files == ["slide-01.png", "slide-02.png"], files
try:
    from PIL import Image
    im1 = Image.open(os.path.join(t0, "slide-01.png")).convert("RGB")
    assert im1.size == (640, 360), im1.size
    assert im1.getpixel((100, 100)) == (255, 0, 0), im1.getpixel((100, 100))   # the red shape
    assert im1.getpixel((10, 10)) == (255, 255, 255), "frame colour"
    im2 = Image.open(os.path.join(t0, "slide-02.png")).convert("RGB")
    assert im2.size == (400, 400) and im2.getpixel((5, 395)) == (0x22, 0x33, 0x55)
    big = scr.export_slides([f1], "png", 2.0)
    assert Image.open(os.path.join(big, "slide-01.png")).size == (1280, 720)
    pdf = scr.export_slides(se.slides(d), "pdf", 1.0)
    assert os.path.exists(os.path.join(pdf, "..", "Untitled.pdf")) or pdf.endswith(".pdf"), pdf
    assert open(pdf, "rb").read(4) == b"%PDF"
except ImportError:
    pass
scr.export_dialog(); tick()
from kivy.uix.popup import Popup
pops = [w for w in Window.children if isinstance(w, Popup)]
assert pops; pops[0].dismiss(); tick()
print("studio present OK")
