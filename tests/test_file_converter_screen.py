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
from kivy.uix.spinner import Spinner
import core.converter_core as cc
from screens.file_converter_screen import FileConverterScreen

def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        Clock.tick(); time.sleep(0.01)

def spinners(s):
    return {w for w in s._list.walk() if isinstance(w, Spinner)}

sm = ScreenManager(); s = FileConverterScreen(name="converter"); sm.add_widget(s); Window.add_widget(sm)
pump(0.2)
d = tempfile.mkdtemp(); out = os.path.join(d, "out"); s._out_dir = out
imgs = []
for i in range(3):
    p = os.path.join(d, f"img{i}.png"); Image.new("RGB", (64, 64), (i * 80, 0, 0)).save(p); imgs.append(p)
jp = os.path.join(d, "pic.jpg"); Image.new("RGB", (40, 40), "red").save(jp)
t1 = os.path.join(d, "a.txt"); t2 = os.path.join(d, "b.md")
open(t1, "w").write("hello"); open(t2, "w").write("# T\n\nbody")
vid = os.path.join(d, "clip.mp4"); open(vid, "wb").write(b"x")      # not real video: only for grouping
s._add_paths(imgs + [jp, t1, t2, vid, os.path.join(d, "nope.xyz")])
print(s._count_lbl.text)
assert len(s._files) == 7 and len(spinners(s)) == 3                 # image, video, doc groups
assert s._go.disabled and s._go.text == "Convert"                    # nothing chosen yet = nothing to convert
assert all(v == "-" for v in s._targets.values())

# choose targets per group; the video group stays on "-" (skipped)
s._set_target("image", "jpg"); s._set_target("doc", "md")
print("button:", s._go.text)
assert s._go.text == "Convert 6 files" and not s._go.disabled        # 4 images + 2 docs, video untouched
assert s._opts.height > 0
s._quality.value = 60; s._maxside.text = "32"
s._start(); assert s._running and s._go.disabled
pump(2.5)
print(s._status.text); print(s._results.text)
assert "4 converted" in s._status.text or "converted" in s._status.text
assert "SKIP  pic.jpg: already .jpg" in s._results.text              # same type is skipped, not failed
assert "SKIP  b.md: already .md" in s._results.text
files = sorted(os.listdir(out)); print("outputs:", files)
assert {"img0.jpg", "img1.jpg", "img2.jpg", "a.md"} <= set(files)
assert not any(f.startswith("clip") for f in files)                  # video group was skipped
assert all(os.path.exists(p) for p in imgs + [jp, t1, t2, vid])       # originals untouched

# an impossible combination can't even be selected: images never offer mp3
img_group_values = set()
for sp in spinners(s):
    if "jpg" in sp.values or "webp" in sp.values: img_group_values = set(sp.values)
assert "mp3" not in img_group_values and "jpg" in img_group_values

# android: video/audio groups say why and are locked, the others still work
s._clear(); cc._on_android = lambda: True
s._add_paths([imgs[0], vid]); pump(0.2)
vsp = [sp for sp in spinners(s) if sp.disabled]
print("android: locked spinners:", len(vsp), "| values:", [sp.values for sp in vsp])
assert len(vsp) == 1 and list(vsp[0].values) == ["-"]
assert any("ffmpeg" in getattr(w, "text", "") for w in s._list.walk())
s._set_target("image", "webp"); assert s._go.text == "Convert 1 file"
cc._on_android = lambda: False

# removing a file keeps the group's choice; removing the last one drops the group
s._clear(); s._add_paths(imgs); s._set_target("image", "jpg"); s._remove(imgs[0])
assert len(s._files) == 2 and s._targets["image"] == "jpg"
s._remove(imgs[1]); s._remove(imgs[2]); assert not s._targets and len(spinners(s)) == 0

# a failing file reports, the rest still convert
bad = os.path.join(d, "broken.png"); open(bad, "wb").write(b"not an image")
s._clear(); s._add_paths([bad, imgs[1]]); s._set_target("image", "webp"); s._start(); pump(1.5)
print(s._status.text); print(s._results.text)
assert "1 converted, 1 failed" in s._status.text

# pickers open (with the path bar) without errors
s._pick_files(); s._pick_folder(); s._pick_out_dir(); pump(0.5)
from kivy.uix.popup import Popup
print("popups open:", len([w for w in Window.children if isinstance(w, Popup)]))
print("file converter screen test passed")
