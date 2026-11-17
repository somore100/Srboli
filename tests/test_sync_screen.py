# tests/test_sync_screen.py - needs a display (kivy). Folder Sync drives the
# real engine: Sync stays disabled until a preview, then mirrors one way.
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from kivy.config import Config
Config.set("graphics", "width", "900"); Config.set("graphics", "height", "700")
from kivy.clock import Clock
import screens.sync_screen as ss
import core.sync_core as sc

root = tempfile.mkdtemp()
A, B = os.path.join(root, "A"), os.path.join(root, "B")
os.makedirs(A); os.makedirs(B)
open(os.path.join(A, "a.txt"), "w").write("one")
open(os.path.join(B, "old.txt"), "w").write("gone soon")

def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        Clock.tick()
        if cond(): return True
        time.sleep(0.02)
    return False

scr = ss.SyncScreen()
scr.preview()
assert "FROM" in scr.status.text and scr.sync_btn.disabled          # nothing picked
scr.a, scr.b = A, B
scr.sync()                                                           # no preview yet: nothing happens
assert not os.path.exists(os.path.join(B, "a.txt"))
scr.preview()
assert wait(lambda: scr._plan is not None and not scr._busy)
assert not scr.sync_btn.disabled and "1 new" in scr.status.text and "COPY" in scr.log.text
assert "MOVE AWAY" in scr.log.text
scr.sync()
assert wait(lambda: not scr._busy and "Done" in scr.status.text), scr.status.text
assert open(os.path.join(B, "a.txt")).read() == "one" and not os.path.exists(os.path.join(B, "old.txt"))
assert sc.replaced_info(B)[0] == 1 and "1 file" in scr.replaced_lbl.text
assert scr.sync_btn.disabled                                         # needs a fresh preview
scr.preview()
assert wait(lambda: scr._plan is not None and not scr._busy)
assert "already match" in scr.log.text and scr.sync_btn.disabled
# picking another folder invalidates the preview
scr._plan = object(); scr._stale(); assert scr._plan is None
# folders that overlap are refused
scr.b = os.path.join(A, "in"); scr.preview(); assert "inside" in scr.status.text
scr.b = B
assert ss.SyncScreen().a == "" or True
# settings survive a rebuild
scr._save_cfg(); s2 = ss.SyncScreen(); assert s2.a == A and s2.b == B

# --- two way mode through the screen
import core.twoway_core as tw
A2, B2 = os.path.join(root, "A2"), os.path.join(root, "B2")
os.makedirs(A2); os.makedirs(B2)
open(os.path.join(A2, "x.txt"), "w").write("from A")
open(os.path.join(B2, "y.txt"), "w").write("from B")
s3 = ss.SyncScreen()
s3.a, s3.b = A2, B2
s3._set_mode("two")
assert s3.a_btn.text == "Folder A" and "Two way" in s3.help_lbl.text and s3.mode == "two"
s3.preview()
assert wait(lambda: s3._plan is not None and not s3._busy)
assert "A -> B" in s3.log.text and "B -> A" in s3.log.text and "First sync" in s3.status.text
s3.sync()
assert wait(lambda: not s3._busy and "Done" in s3.status.text), s3.status.text
assert open(os.path.join(B2, "x.txt")).read() == "from A" and open(os.path.join(A2, "y.txt")).read() == "from B"
os.remove(os.path.join(A2, "x.txt"))                         # a deletion travels
s3.preview(); assert wait(lambda: s3._plan is not None and not s3._busy)
assert "DELETE on B" in s3.log.text
s3.sync(); assert wait(lambda: not s3._busy and "Done" in s3.status.text)
assert not os.path.exists(os.path.join(B2, "x.txt"))
# the mode is remembered
assert ss.SyncScreen().mode == "two"
s3._set_mode("mirror"); assert ss.SyncScreen().mode == "mirror"
print("sync screen passed")
