# tests/test_shortcut_screen.py - needs a display (xvfb-run -a python3 tests/test_shortcut_screen.py)
# Writes only under a temp dir: HOME / XDG_DATA_HOME point there.
import os, sys, tempfile
home = tempfile.mkdtemp()
os.environ["HOME"] = home
os.environ["XDG_DATA_HOME"] = os.path.join(home, "share")
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from core import desktop_entry as D
import screens.shortcut_screen as ss

D.desktop_dir = lambda: None                      # never touch a real Desktop
scr = ss.ShortcutScreen(name="shortcut")

scr._create()                                     # empty form: explains, writes nothing
assert "name" in scr._status.text.lower() and D.list_created() == []

scr._cmd.text = 'sh -c "echo hi there"'
scr._name.text = "Hello Tool"
scr._comment.text = "says hi"
scr._terminal.active = True
scr._cats["Game"].state = "down"
text, problems = scr._entry_text()
assert problems == [] and "Terminal=true" in text and "Categories=Utility;Game;" in text
scr._create()
assert D.exists("hello-tool.desktop") and "Created:" in scr._status.text
(path, entry), = D.list_created()
assert entry["argv"] == ["sh", "-c", "echo hi there"] and entry["name"] == "Hello Tool"

scr._clear()                                      # edit the saved one
assert scr._name.text == ""
scr._load(entry, "hello-tool.desktop")
assert scr._cmd.text == "sh -c 'echo hi there'" and scr._terminal.active
scr._name.text = "Hello Renamed"
scr._create()                                     # keeps the file name, updates the content
assert [e["name"] for _, e in D.list_created()] == ["Hello Renamed"]
assert len(os.listdir(D.applications_dir())) == 1

scr._clear(); scr._cmd.text = 'broken "quote'; scr._name.text = "x"
scr._create()
assert "unclosed quote" in scr._status.text

scr._clear(); scr._fill_this_app()                # "This app"
assert scr._name.text == "Srboli" and scr._cmd.text.strip() and scr._comment.text

scr._preview(); scr._show_mine()                  # popups open without errors
D.delete("hello-tool.desktop")
assert D.list_created() == []
print("shortcut screen OK")
