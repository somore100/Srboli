# tests/test_pause_recovery.py - python3 tests/test_pause_recovery.py (needs kivy)
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from types import SimpleNamespace
from core import kivy_patches as kp

class Win:
    """Fake SDL window: hands out a script of events, one per wait_event."""
    def __init__(self, events):
        self.events = list(events); self.cur = None
    def wait_event(self): self.cur = self.events.pop(0) if self.events else "stuck"
    def poll(self):
        assert self.cur != "stuck", "would block forever"
        return self.cur

def run(events, paused=True):
    w = SimpleNamespace(_pause_loop=paused, _win=Win(events), drops=[], woke=[])
    w._dispatch_drop_event = lambda a, args: w.drops.append(a)
    ran = []
    kp.pause_mainloop(w, lambda win: ran.append(1), lambda a: w.woke.append(a))
    return w, ran

# a touch ends a stuck pause, then the normal loop runs
w, ran = run([None, ("mousemotion", 1, 2), ("fingerdown", 0, 0.5, 0.5, 1.0)])
assert not w._pause_loop and w.woke == ["fingerdown"] and ran == [1]
# a drop while paused is still delivered
w, ran = run([("dropfile", b"x"), ("keydown", 4)])
assert w.drops == ["dropfile"] and w.woke == ["keydown"]
# not paused: straight to the normal loop
w, ran = run([], paused=False); assert ran == [1] and not w.woke
# the real foreground event (sets _pause_loop False elsewhere) still works
class Win2(Win):
    def wait_event(self): self.owner._pause_loop = False
w = SimpleNamespace(_pause_loop=True, woke=[]); w._win = Win2([]); w._win.owner = w
ran = []; kp.pause_mainloop(w, lambda win: ran.append(1), lambda a: w.woke.append(a))
assert ran == [1] and not w.woke
print("pause recovery OK")
