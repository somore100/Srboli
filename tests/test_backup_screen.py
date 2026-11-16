# tests/test_backup_screen.py - needs a display (kivy). The Backup screen
# drives the real engine against real folders: preview, back up, list, restore.
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from kivy.config import Config
Config.set("graphics", "width", "900"); Config.set("graphics", "height", "700")
from kivy.clock import Clock
import screens.backup_screen as bs
import core.backup_core as bc

root = tempfile.mkdtemp()
src, dst, out = (os.path.join(root, n) for n in ("src", "dst", "out"))
os.makedirs(src); os.makedirs(dst)
open(os.path.join(src, "a.txt"), "w").write("hello")

def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        Clock.tick()
        if cond(): return True
        time.sleep(0.02)
    return False

scr = bs.BackupScreen()
scr.run()                                           # nothing picked yet
assert "Pick the folder" in scr.status.text and not scr._busy
scr.source, scr.dest = src, dst
scr._set_kind("full")
scr.preview()
assert wait(lambda: not scr._busy and scr._plan is not None)
assert "1 of 1 files" in scr.status.text, scr.status.text
scr.run()
assert wait(lambda: not scr._busy and "Done" in scr.status.text), scr.status.text
rows = [w for w in scr.list_box.children]
assert len(rows) == 1 and "Full" in rows[0].children[-1].text
# the destination inside the source is refused
scr.dest = os.path.join(src, "in"); scr.run()
assert "inside" in scr.status.text; scr.dest = dst
# an incremental right after changes nothing
scr._set_kind("incr"); scr.run()
assert wait(lambda: not scr._busy and "Done" in scr.status.text and "0 file" in scr.status.text), scr.status.text
assert len(scr.list_box.children) == 2
# restore through the same path the button uses
sd = scr._set_dir(); name = bc.list_backups(sd)[0]["name"]
res = bc.run_restore(sd, name, out)
assert res.ok and open(os.path.join(out, "a.txt")).read() == "hello"
# settings survive a rebuild
scr2 = bs.BackupScreen()
assert scr2.source == src and scr2.dest == dst and scr2.kind == "incr"
print("backup screen passed")
