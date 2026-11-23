# tests/test_image_tools_screen.py - xvfb-run -a python3 tests/test_image_tools_screen.py  (kivy screens.)
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from kivy.clock import Clock
from screens.image_tools_screen import ImageToolsScreen

def wait(sc):
    for _ in range(200):
        Clock.tick()
        if not sc._running:
            return
        time.sleep(0.05)
    raise SystemExit("timeout")

with tempfile.TemporaryDirectory() as d:
    ps = []
    for i, c in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
        p = os.path.join(d, f"p{i}.png"); Image.new("RGB", (300, 200), c).save(p); ps.append(p)
    sc = ImageToolsScreen()
    sc.run(); assert "Add some" in sc.status.text
    sc.add_paths(ps + [os.path.join(d, "x.txt"), ps[0]])
    assert sc.paths == ps
    sc.move_up(1); assert sc.paths[0] == ps[1]
    sc.remove(0); assert len(sc.paths) == 2
    sc.add_paths(ps)
    sc.side_sp.text = "640 px"; sc.fmt_sp.text = "WEBP"
    sc.run(); wait(sc)
    out = os.path.join(d, "srboli_images")
    assert sorted(f for f in os.listdir(out) if f.endswith(".webp")) == ["p0.webp", "p1.webp", "p2.webp"], os.listdir(out)
    assert "3 of 3 done" in sc.status.text
    sc.set_mode("combine"); sc.layout_sp.text = "Side by side"; sc.size_sp.text = "800 px"
    sc.run(); wait(sc)
    im = Image.open(os.path.join(out, "combined.jpg"))
    assert im.height == 800 and im.width == 3 * 1200, im.size
    sc.clear(); sc.add_paths(ps[:1]); sc.run(); assert "at least two" in sc.status.text
print("image tools screen OK")
