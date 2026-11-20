# needs a display: xvfb-run -a python3 tests/test_permissions_block.py
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from core import permissions
r = permissions.rows(True, False)
assert [x[0] for x in r] == ["storage", "notify"] and r[0][2] is True and r[1][2] is False
from screens.permissions_block import PermissionsBlock
b = PermissionsBlock()          # off Android: both "allowed" (nothing to ask), no Allow buttons
from kivy.uix.button import Button
assert not [w for row in b.children for w in getattr(row, "children", []) if isinstance(w, Button)]
print("permissions block OK")
