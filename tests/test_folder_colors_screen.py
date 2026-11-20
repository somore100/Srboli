# tests/test_folder_colors_screen.py - xvfb-run -a python3 tests/test_folder_colors_screen.py
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from unittest.mock import patch
from screens.folder_colors_screen import FolderColorsScreen
from core import folder_icons_core as core

s = FolderColorsScreen()
assert s.preview.source.endswith(".png")
s.apply(); assert "isn't a folder" in s.status.text
d = tempfile.mkdtemp(); os.mkdir(os.path.join(d, "sub"))
s.path_in.text = d
s.pick_color("#e5484d"); assert s.color == "#e5484d" and not s.use_picture
s.pick_color("zzz"); assert "not a colour" in s.status.text and s.color == "#e5484d"
with patch.object(core.subprocess, "run") as run:
    run.return_value.returncode = 0
    s.toggle_sub(); s.apply()
    assert "2 folders" in s.status.text, s.status.text
    assert os.path.exists(os.path.join(d, "sub", ".directory")) and core.current(d)
    s.reset(); assert "2 folders" in s.status.text and not core.current(d)
    s.toggle_sub(); s.apply(); assert "1 folder." in s.status.text
print("folder colors screen OK")
