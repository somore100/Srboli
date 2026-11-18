# tests/test_disk_space_screen.py - xvfb-run -a python3 tests/test_disk_space_screen.py
import os, sys, tempfile, time
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from screens.disk_space_screen import DiskSpaceScreen

def pump(cond, secs=8):
    t = time.time()
    while not cond() and time.time() - t < secs:
        Clock.tick(); time.sleep(0.01)
    return cond()

r = tempfile.mkdtemp()
def mk(rel, size):
    p = os.path.join(r, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(b"x" * size)
mk("big/a.mp4", 9000); mk("big/sub/b.jpg", 1000); mk("small/c.txt", 100)
s = DiskSpaceScreen()
texts = lambda: [b.text for b in s.list_box.children][::-1]
s.start(os.path.join(r, "nope")); assert "isn't a folder" in s.status.text and not s._busy
s.start(r); assert s._busy and s.scan_btn.text == "Stop"
assert pump(lambda: s.result is not None), "scan never finished"
assert not s._busy and s.scan_btn.text == "Scan" and "9.9 KB in 3 files" in s.summary.text, s.summary.text
rows = texts()
assert "[-]" in rows[0] and "big" in rows[0], rows          # the big folder opened by itself
assert any("sub" in t and t.startswith("    ") for t in rows), rows     # its child is indented under it
assert any("small" in t for t in rows) and any("a.mp4" in t or "files in this folder" in t for t in rows)
s.list_box.children[-1].dispatch("on_release")           # tap "big": it closes
rows = texts(); assert "[+]" in rows[0] and not any("sub" in t for t in rows), rows
s.open_all(); assert any("sub" in t for t in texts())
s.close_all(); assert len(texts()) == 2
s.open_big(); assert len(texts()) > 2
s.show_tab("files"); lines = texts()
assert "big" in lines[0] and "a.mp4" in lines[0] and "b.jpg" in lines[1], lines
assert s.nav.height == 0
s.show_tab("types"); assert "Video" in texts()[0] and "Pictures" in texts()[1]
s.show_tab("folders"); assert s.nav.height > 0
s.copy(); from kivy.core.clipboard import Clipboard
assert "Biggest files:" in Clipboard.paste()
s.start(r); assert pump(lambda: not s._busy) and s.result is not None
print("disk space screen: all ok")
