# needs a display: xvfb-run -a python3 tests/test_open_with_screens.py
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from screens.text_editor_screen import TextEditorScreen
d = tempfile.mkdtemp(); p = os.path.join(d, "n.txt"); open(p, "w").write("hello")
t = TextEditorScreen(name="t"); t.open_path(p)
assert t._ed.text == "hello" and t._file is None and "another app" in t._status.text
print("open-with screens OK")
