# tests/test_cleanup_screen.py - xvfb-run -a python3 tests/test_cleanup_screen.py  (kivy screens.)
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.clock import Clock
from screens import cleanup_screen as cs
from core import cleanup_core as core

def settle(sc):
    for _ in range(100):
        Clock.tick(); time.sleep(0.02)
        if not sc._busy:
            Clock.tick(); return
    raise SystemExit("timeout")

with tempfile.TemporaryDirectory() as d:
    root = os.path.join(d, "cache"); os.makedirs(root)
    old = time.time() - 5 * 86400
    for i in range(3):
        p = os.path.join(root, f"f{i}.bin"); open(p, "wb").write(b"x" * 1000); os.utime(p, (old, old))
    core.categories = lambda *a, **k: [core.Category("cache", "Test cache", root, "note", 24),
                                       core.Category("trash", "Test trash", os.path.join(d, "none"), "", 0, default_on=False)]
    sc = cs.CleanupScreen()
    sc.scan(); settle(sc)
    assert [r["key"] for r in sc.results] == ["cache", "trash"] and sc.results[0]["total"] == 3000
    assert sc.sel == {"cache": True, "trash": False} and not sc.clean_btn.disabled
    assert "2.9 KB" in sc.total.text
    sc.toggle("cache"); assert sc.clean_btn.disabled and sc.total.text == "Nothing selected."
    sc.toggle("cache")
    sc.run_clean(sc._selected()); settle(sc)
    assert "Freed 2.9 KB" in sc.status.text and not os.listdir(root), (sc.status.text, os.listdir(root))
    sc.set_tab("memory"); assert sc.holder.children[0] is sc.mem_panel
    if cs.psutil: assert "Memory in use" in sc.mem_info.text
    sc.free_own(); assert "released" in sc.mem_status.text
print("cleanup screen OK")
