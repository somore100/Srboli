import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import studio_core as sc  # noqa: E402
from core import studio_export as se  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name)


d = sc.Document()
f1 = d.add(sc.make("frame", w=1280.0, h=720.0))
f2 = d.add(sc.make("frame", x=2000.0, w=800.0, h=800.0))
f3 = d.add(sc.make("frame", x=4000.0))
a = d.add(sc.make("shape", x=10, y=10), parent=f2["id"])
loose = d.add(sc.make("shape", x=9000))
g = d.add(sc.make("shape", x=11), parent=f2["id"])
f3["visible"] = False
check("slides are visible frames in order", se.slides(d) == [f1, f2])
check("start default", se.start_index(d) == 0 and se.start_index(d, [loose["id"]]) == 0)
check("start on frame", se.start_index(d, [f2["id"]]) == 1)
check("start on child", se.start_index(d, [a["id"]]) == 1)
check("start ignores missing id", se.start_index(d, [999]) == 0)
check("reorder changes slides", (d.move_order(f1["id"], 1), se.slides(d))[1] == [f2, f1])
check("slide holds children", se.slide_ids(d, f2) == {f2["id"], a["id"], g["id"]})
check("pixels", se.slide_pixels(f1) == (1280, 720) and se.slide_pixels(f1, scale=2) == (2560, 1440))
big = sc.make("frame", w=10000.0, h=5000.0)
check("pixels capped", se.slide_pixels(big) == (4096, 2048))
check("stem", se.file_stem("a b/c?") == "a_b_c" and se.file_stem("///") == "slides")
check("no slides", sc.Document() and se.slides(sc.Document()) == [])
try:
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp:
        ps = []
        for i, col in enumerate(("red", "green")):
            p = os.path.join(tmp, f"{i}.png")
            Image.new("RGB", (10, 10), col).save(p)
            ps.append(p)
        out = se.images_to_pdf(ps, os.path.join(tmp, "o.pdf"))
        data = open(out, "rb").read()
        check("pdf written", data.startswith(b"%PDF") and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 1)
        try:
            se.images_to_pdf([], os.path.join(tmp, "x.pdf"))
            check("empty refused", False)
        except ValueError:
            pass
except ImportError:
    pass
print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
