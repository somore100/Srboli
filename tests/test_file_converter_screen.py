# tests/test_file_converter_screen.py - needs a display (xvfb-run -a python3 ...)
import os, sys, time, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
from kivy.core.window import Window
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from PIL import Image
from kivy.uix.screenmanager import ScreenManager
from screens.file_converter_screen import FileConverterScreen

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        Clock.tick(); time.sleep(0.01)

sm = ScreenManager(); s = FileConverterScreen(name="converter"); sm.add_widget(s); Window.add_widget(sm)
pump(0.2)
d = tempfile.mkdtemp(); out = os.path.join(d, "out"); s._out_dir = out
imgs = []
for i in range(3):
    p = os.path.join(d, f"img{i}.png"); Image.new("RGB", (64, 64), (i * 80, 0, 0)).save(p); imgs.append(p)
open(os.path.join(d, "notes.xyz"), "w").write("x")
s._add_paths(imgs + [os.path.join(d, "notes.xyz")])
print("count:", s._count_lbl.text, "| targets:", list(s._target.values))
assert len(s._files) == 3 and "jpg" in s._target.values and "png" not in s._target.values
assert not s._go.disabled and s._opts.height > 0
s._target.text = "jpg"; s._quality.value = 60; s._maxside.text = "32"
s._start(); assert s._running and s._go.disabled
pump(2.0)
print("status:", s._status.text); print(s._results.text)
assert not s._running and "Done: 3 converted" in s._status.text
files = sorted(os.listdir(out)); print("outputs:", files)
assert files == ["img0.jpg", "img1.jpg", "img2.jpg"] and max(Image.open(os.path.join(out, "img0.jpg")).size) == 32
assert all(os.path.exists(p) for p in imgs)                     # originals untouched
# mixed kinds with no common target
txt = os.path.join(d, "a.txt"); open(txt, "w").write("hello")
mp3 = os.path.join(d, "a.mp3"); open(mp3, "wb").write(b"x")
s._add_paths([mp3]); print("mixed:", s._notice.text[:60])
assert s._target.text == "-" and s._go.disabled and "in common" in s._notice.text
s._clear(); assert not s._files and s._go.disabled
s._add_paths([txt, imgs[0]]); assert s._target.text == "pdf" or "pdf" in s._target.values   # common target exists
# docs
s._clear()
s._add_paths([txt]); s._target.text = "html"; s._start(); pump(1.0)
assert "Done: 1 converted" in s._status.text, s._status.text
# remove one file via its X
s._clear(); s._add_paths(imgs); s._remove(imgs[0]); assert len(s._files) == 2
# failing file reports, others still convert
bad = os.path.join(d, "broken.png"); open(bad, "wb").write(b"not an image")
s._clear(); s._add_paths([bad, imgs[1]]); s._target.text = "webp"; s._start(); pump(1.5)
print(s._status.text); print(s._results.text)
assert "1 converted, 1 failed" in s._status.text
# pickers open (with the path bar) without errors
s._pick_files(); s._pick_folder(); s._pick_out_dir()
pump(0.5)
from kivy.uix.popup import Popup
print("popups open:", len([w for w in Window.children if isinstance(w, Popup)]))
print("file converter screen test passed")
