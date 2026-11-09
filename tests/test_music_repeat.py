# tests/test_music_repeat.py - needs a display (it imports screens.music_screen)
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from screens.music_screen import next_index, REPEAT_ORDER

assert next_index("all", 0, 3) == 1 and next_index("all", 2, 3) == 0     # loops the list
assert next_index("one", 1, 3) == 1                                      # same track again
assert next_index("off", 0, 3) == 1 and next_index("off", 2, 3) is None  # stops at the end
assert next_index("all", None, 3) is None and next_index("all", 0, 0) is None
assert REPEAT_ORDER[0] == "all"                                          # the old AutoNext behaviour stays the default
print("music repeat OK")
