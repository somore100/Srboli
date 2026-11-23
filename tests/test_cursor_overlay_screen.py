# tests/test_cursor_overlay_screen.py - xvfb-run -a python3 tests/test_cursor_overlay_screen.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import cursor_core as core
saved = []
core.save = lambda cfg: saved.append(dict(cfg))           # never touch the real settings file
core.load = lambda: core.clean({})
from screens.cursor_overlay_screen import CursorOverlayScreen

sc = CursorOverlayScreen()
sc.shape_sp.text = "Crosshair"; assert sc.cfg["shape"] == "crosshair" and saved[-1]["shape"] == "crosshair"
sc.sliders["size"].value = 90; assert sc.cfg["size"] == 90
sc.sliders["opacity"].value = 50; assert abs(sc.cfg["opacity"] - 0.5) < 1e-9
sc.set_color("#E53935"); assert sc.cfg["color"] == "#E53935" and sc.hex_in.text == "#E53935"
sc.hex_in.text = "00ff00"; sc._hex(); assert sc.cfg["color"] == "#00FF00"
sc.hex_in.text = "zzz"; sc._hex(); assert "Not a colour" in sc.status.text
sc.toggle_flash(); assert sc.cfg["click_flash"] is False
sc.toggle_visible(); assert sc.cfg["visible"] is False and sc.show_btn.text == "Show"
for name in core.SHAPES.values():
    sc.shape_sp.text = name                                  # every shape draws without error
assert sc.run_btn.disabled == (not core.supported())
print("cursor overlay screen OK")
