# tests/test_startup_screen.py - xvfb-run -a python3 tests/test_startup_screen.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from screens.startup_screen import StartupScreen
from core import startup_core as core

with tempfile.TemporaryDirectory() as root:
    os.environ["XDG_CONFIG_HOME"] = root
    d = os.path.join(root, "autostart"); os.makedirs(d)
    open(os.path.join(d, "x.desktop"), "w").write("[Desktop Entry]\nName=Xapp\nExec=xapp\n")
    core.SYSTEM_DIRS[:] = []
    sc = StartupScreen()
    if core.is_supported():
        assert [e["name"] for e in sc.entries] == ["Xapp"]
        sc.toggle(sc.entries[0])
        assert not sc.entries[0]["enabled"], sc.entries
        sc.toggle(sc.entries[0])
        assert sc.entries[0]["enabled"]
print("startup screen OK")
