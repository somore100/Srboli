# tests/test_kivy_patches.py - needs a display (xvfb-run -a python3 tests/test_kivy_patches.py)
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.core.window import Window
from core import kivy_patches as kp

assert kp.missing_internals() == [], kp.missing_internals()
logged = []
assert kp.check(logged.append) == [] and not logged, logged

# the patches must install without NameErrors and keep the callbacks' names
from kivy.uix.behaviors.button import ButtonBehavior
from kivy.uix.modalview import ModalView
kp.apply_android(Window, None)
assert ButtonBehavior._do_release.__name__ == "_do_release"
assert ModalView.open.__name__ == "open" and ModalView.dismiss.__name__ == "dismiss"

# a Kivy that lost an internal is reported, not ignored
kp.INTERNALS = kp.INTERNALS + (("kivy.uix.spinner", "Spinner", "_gone"),)
assert kp.missing_internals() == ["Spinner._gone"]
print("kivy_patches OK")
