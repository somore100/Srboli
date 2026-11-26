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
    # ---- resize / upscale mode ----
    sc.clear(); sc.set_mode("resize"); assert "Add pictures" in sc.rprev.text
    sc.run(); assert "Add some" in sc.status.text
    sc.add_paths(ps)
    sc.rval_in.text = "200"
    assert sc.update_preview() == (600, 400) and "bigger" in sc.rprev.text and "+2 more" in sc.rprev.text, sc.rprev.text
    sc.rval_in.text = "0"
    assert sc.update_preview() is None
    sc.run(); assert not sc._running and "more than 0" in sc.status.text, sc.status.text
    sc.rval_in.text = "50"; sc.fmt_sp.text = "PNG"
    assert sc.update_preview() == (150, 100) and "smaller" in sc.rprev.text
    sc.rhow_sp.text = "Longest side"; sc.rval_in.text = "900"
    assert sc.update_preview() == (900, 600)
    sc.rhow_sp.text = "Exact size"; sc.rw_in.text = "100"; sc.rh_in.text = "100"; sc.fit_sp.text = "Fill (crop)"
    assert sc.update_preview() == (100, 100)
    sc.rw_in.text = ""; sc.rh_in.text = ""
    assert sc.update_preview() is None and "width or a height" in sc.rprev.text
    sc.rhow_sp.text = "By percent"; sc.rval_in.text = "300"; sc.sharp_sp.text = "Medium sharpening"; sc.fmt_sp.text = "PNG"
    sc.run(); wait(sc)
    outs = sorted(f for f in os.listdir(out) if f.endswith("-900x600.png") or f.endswith("-900x600-2.png") or "x600" in f)
    assert any(f.startswith("p0-900x600") for f in os.listdir(out)), os.listdir(out)
    assert "3 of 3 done" in sc.status.text, sc.status.text
    assert Image.open(os.path.join(out, "p1-900x600.png")).size == (900, 600)
    sc.remove(0); sc.remove(0); sc.remove(0)
    assert "Add pictures" in sc.rprev.text
print("image tools screen OK")
