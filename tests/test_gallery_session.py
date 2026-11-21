# tests/test_gallery_session.py - xvfb-run -a python3 tests/test_gallery_session.py
import os, sys, tempfile, time
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
from unittest.mock import MagicMock
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import gallery_session as gs
from screens.gallery_sorter_screen import GallerySorterScreen

def pump(cond, secs=6):
    t = time.time()
    while not cond() and time.time() - t < secs:
        Clock.tick(); time.sleep(0.01)
    return cond()

# core
assert gs.load() is None
src = tempfile.mkdtemp(); dst = tempfile.mkdtemp()
open(os.path.join(src, "a.jpg"), "wb").write(b"x"); open(os.path.join(src, "b.jpg"), "wb").write(b"y")
assert gs.save([], []) is False and gs.load() is None
assert gs.save([src, "/gone"], [{"label": "L", "path": dst, "subs": []}, {"label": "X", "path": "/gone"}], os.path.join(src, "b.jpg"))
s = gs.load(); assert s["sources"] == [src] and len(s["dest_tree"]) == 1 and s["current"].endswith("b.jpg")
assert "1 source folder, 1 destination" == gs.describe(s)
gs.clear(); assert gs.load() is None

# screen: work, leave, come back, continue
a = GallerySorterScreen(); a.manager = MagicMock(current="gallery")
a._sources = [src]; a._dest_tree = [{"label": "L", "path": dst, "subs": []}]
a._reload_files(); assert pump(lambda: len(a._files) == 2)
a._index = 1; a._show_current(); a._autosave_now()
b = GallerySorterScreen(); b.manager = MagicMock(current="gallery")
b._autosave_now(); assert gs.load() is not None            # a fresh screen never wipes the saved session
assert b._offer_resume() is True
b._resume(gs.load())
assert pump(lambda: len(b._files) == 2) and b._files[b._index].endswith("b.jpg"), (b._files, b._index)
assert b._dest_tree[0]["label"] == "L"
b._clear_loaded(destinations=True); assert gs.load() is None
c = GallerySorterScreen(); c.manager = MagicMock(current="gallery"); assert c._offer_resume() is False
print("gallery session OK")
