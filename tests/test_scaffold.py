# needs a display: xvfb-run -a python3 tests/test_scaffold.py
import os, sys, tempfile
from unittest.mock import MagicMock
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.core.window import Window
from kivy.uix.button import Button
from core import theme
theme.install()
from screens.binary_screen import BinaryScreen, text_to_codes

s = BinaryScreen(name="binary")
assert s.title_label.text == "[b]Binary / Hex / Decimal[/b]"
s.manager = MagicMock()
backs = [w for w in s.walk() if isinstance(w, Button) and w.text == "< Back"]
assert len(backs) == 1                       # exactly one Back, in the top bar
backs[0].dispatch("on_release"); assert s.manager.current == "dashboard"
# content is capped on a wide window
s.size = (3000, 800); EventLoop.idle(); EventLoop.idle()
assert s.body.width <= theme.MAX_CONTENT_W + 1, s.body.width
s.size = (400, 800); EventLoop.idle(); EventLoop.idle()
assert s.body.width <= 400
s.input.text = "Hi"; s._enc(); assert s.output.text == text_to_codes("Hi", "Binary")
print("scaffold OK")
