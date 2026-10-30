# Kivy-free pieces of phase 3: permissions, window state, capped logs.
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import permissions as P
from core import window_state as W
from core.logs import append_capped

asked = set()
assert P.needed("gallery", False, False, False, asked) is None            # not Android
assert P.needed("gallery", True, False, False, asked) == "storage"
assert P.needed("gallery", True, True, False, asked) is None              # already granted
assert P.needed("reminders", True, True, False, asked) == "notify"
assert P.needed("music", True, False, False, asked) is None               # needs nothing
assert P.needed("gallery", True, False, False, {"storage"}) is None       # never twice

assert W.valid({"width": 900, "height": 640, "left": 10, "top": 20}) == \
    {"width": 900, "height": 640, "left": 10, "top": 20}
assert W.valid({"width": 900, "height": 640}) == {"width": 900, "height": 640}
assert W.valid({"width": 5, "height": 640}) is None and W.valid("x") is None
assert W.valid({"width": 900, "height": 640, "left": "a", "top": 1}) == {"width": 900, "height": 640}

d = tempfile.mkdtemp()
for i in range(10):
    append_capped("x.log", "y" * 100 + "\n", max_bytes=450, folder=d)
assert sorted(os.listdir(d)) == ["x.log", "x.log.prev"]
assert os.path.getsize(os.path.join(d, "x.log")) <= 450 + 101
print("phase 3 core OK")
