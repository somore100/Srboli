# tests/test_drawing_core.py - python3 tests/test_drawing_core.py
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.drawing_core import Drawing, hex_rgb

d = Drawing((100, 80), (255, 255, 255))
assert d.is_empty() and not d.undo() and not d.redo()
d.begin("brush", (255, 0, 0), 10, False, (10, 10)); d.move((50, 10)); d.move((50, 10)); d.end()
assert len(d.strokes[0]["points"]) == 2 and not d.is_empty()
img = d.render()
assert img.size == (100, 80) and img.getpixel((30, 10)) == (255, 0, 0) and img.getpixel((30, 60)) == (255, 255, 255)
# eraser paints the background, even after the background changes
d.begin("eraser", None, 20, False, (30, 10)); d.move((31, 10)); d.end()
assert d.render().getpixel((30, 10)) == (255, 255, 255)
d.set_background((0, 0, 0))
assert d.render().getpixel((30, 10)) == (0, 0, 0) and d.render().getpixel((5, 70)) == (0, 0, 0)
# shapes
d.begin("rect", (0, 0, 255), 4, True, (60, 40)); d.move((90, 70)); d.end()
assert d.render().getpixel((75, 55)) == (0, 0, 255)
d.begin("oval", (0, 255, 0), 3, False, (5, 40)); d.move((45, 78)); d.end()
# a tap makes a dot
d2 = Drawing((40, 40)); d2.begin("brush", (0, 0, 0), 10, False, (20, 20)); d2.end()
assert d2.render().getpixel((20, 20)) == (0, 0, 0)
# undo / redo / clear
n = len(d.strokes)
assert d.undo() and len(d.strokes) == n - 1 and d.redo() and len(d.strokes) == n
d.clear(); assert d.is_empty() and d.render().getpixel((10, 10)) == (0, 0, 0)
d.undo(); assert not d.is_empty()
d.undo()                                     # drops the oval; redo list now has 1
d.begin("line", (1, 2, 3), 2, False, (0, 0)); d.move((9, 9)); d.end()
assert d.redo_list == []                     # drawing again forgets the redo history
assert d.begin("brush", (0, 0, 0), 999, False, (0, 0))["width"] == 80
try: d.begin("spray", (0, 0, 0), 1, False, (0, 0)); raise SystemExit("no error")
except ValueError: pass
with tempfile.TemporaryDirectory() as t:
    p = d2.save(os.path.join(t, "sub", "a.png")); assert os.path.getsize(p) > 0
assert hex_rgb("#FF8000") == (255, 128, 0)
print("drawing core OK")
