# tests/test_qr_screen.py - xvfb-run -a python3 tests/test_qr_screen.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from screens.qr_screen import QRScreen
from core import qr_core as core

sc = QRScreen()
assert sc.matrix is None
sc.input.text = "https://example.com"
assert sc.matrix and len(sc.matrix) >= 21
sc.set_mode("wifi")
assert sc.matrix is None                      # no network name yet
sc.ssid.text, sc.pw.text = "home", "secret"
assert sc.text == "WIFI:T:WPA;S:home;P:secret;;" and sc.matrix
sc.set_mode("text")
sc.input.text = "x" * 400
assert sc.matrix is None and "Too long" in sc.status.text
sc.toggle_level(); assert sc.level == "L"
sc.input.text = "short"
assert sc.matrix
if core.can_scan():
    with tempfile.TemporaryDirectory() as d:
        p = core.to_png(core.make("round trip"), os.path.join(d, "q.png"))
        sc.read_path(p)
        assert sc.input.text == "round trip", sc.input.text
print("qr screen OK")
