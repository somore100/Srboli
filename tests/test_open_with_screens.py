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

# Music Player: a file handed over by "Open with" joins the playlist and plays
import tempfile as _tf
from unittest.mock import patch as _patch
from screens.music_screen import MusicScreen
_m = MusicScreen(); _mp = os.path.join(_tf.mkdtemp(), "song.mp3"); open(_mp, "wb").write(b"ID3")
with _patch.object(MusicScreen, "_play_current") as _pc:
    _m.play(_mp); _m.play(_mp)
assert _m.playlist == [_mp] and _m.current_index == 0 and _pc.call_count == 2
_m.play("/no/such.mp3"); assert _m.playlist == [_mp]
print("music open-with OK")
