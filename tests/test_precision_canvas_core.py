import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import precision_canvas_core as pc  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name)


def near(a, b, e=1e-6):
    return abs(a - b) <= e


# calc: safe evaluator
check("calc basic", calc_ok := near(pc.calc("2+3*4"), 14))
check("calc pi", near(pc.calc("2*pi"), math.tau))
check("calc sqrt", near(pc.calc("sqrt(2)^2"), 2))
check("calc deg trig", near(pc.calc("sin(90)"), 1))
check("calc comma decimal", near(pc.calc("1,5*2"), 3))
for bad in ("", "1/0", "__import__('os')", "2**", "abc", "(1+2", "9^999", "1+", "sqrt(-1)"):
    try:
        pc.calc(bad)
        check("calc rejects " + bad, False)
    except ValueError:
        pass

# fmt
check("fmt int", pc.fmt(12.0) == "12")
check("fmt dec", pc.fmt(0.333333) == "0.33")
check("fmt big", pc.fmt(1234.5) == "1,234.5")
check("fmt nan", pc.fmt(float("nan")) == "n/a")

# geometry
check("rotate", near(pc.rotate_point(1, 0, 0, 0, 90)[1], 1))
p = pc.snap_angle((0, 0), (10, 1), 15)
check("angle snap", near(pc.angle_deg((0, 0), p), 0) and near(pc.dist((0, 0), p), math.hypot(10, 1)))
check("seg dist", near(pc.seg_dist((5, 3), (0, 0), (10, 0)), 3))

# objects and maths
r = pc.make("rect", w=10, h=5)
check("rect verts", pc.vertices(r)[2] == (10, 5))
rows = {x[0]: x for x in pc.math_rows(r)}
check("rect area", rows["Area"][3].startswith("50"))
c = pc.make("circle", r=1)
rows = {x[0]: x for x in pc.math_rows(c)}
check("circle area", rows["Area"][3].startswith("3.14"))
check("circle formula", "πr²" in rows["Area"][1])
hexa = pc.make("polygon", n=6, r=10)
check("hex side = r", near(pc.polygon_side(10, 6), 10))
rows = {x[0]: x for x in pc.math_rows(hexa)}
check("hex interior", rows["Interior angle"][3].startswith("120"))
check("square diag", pc.math_rows(pc.make("square", side=1))[2][3].startswith("1.41"))
for t in pc.TYPES:
    pc.math_rows(pc.make(t))  # never raises, even for empty polylines
    pc.bbox(pc.make(t))

# fields
l = pc.make("line", x2=3, y2=4)
check("length", near(pc.get_field(l, "length"), 5))
ok, _ = pc.set_field(l, "length", 10)
check("set length", ok and near(l["x2"], 6) and near(l["y2"], 8))
ok, msg = pc.set_field(c, "r", -1)
check("neg radius refused", not ok and c["r"] == 1)
ok, _ = pc.set_field(hexa, "n", 3.5)
check("fractional sides refused", not ok and hexa["n"] == 6)
ok, _ = pc.set_field(hexa, "side", 10)
check("set side", ok and near(hexa["r"], 10))
ok, _ = pc.set_field(c, "diameter", 8)
check("diameter", ok and c["r"] == 4)
a = pc.make("arrow")
check("arrow fields", len(pc.fields(a)) == 6)

# hit and move
d = pc.Document()
b = d.add(pc.make("rect", x=0, y=0, w=10, h=10, style={"fill": "#FF0000"}))
check("hit inside filled", d.hit_test(5, 5, 0.5) is b)
b2 = d.add(pc.make("circle", cx=50, cy=50, r=10))
check("hit circle outline", d.hit_test(60, 50, 0.5) is b2)
check("no hit inside empty circle", d.hit_test(50, 50, 0.5) is None)
b2["locked"] = True
check("locked not hit", d.hit_test(60, 50, 0.5) is None)
pc.translate(b, 5, 5)
check("translate", b["x"] == 5)
pc.rotate_object(b, 90)
check("rotate keeps centre", near(pc.center(b)[0], 10) and near(pc.center(b)[1], 10))

# undo / redo: one checkpoint per drag
d = pc.Document()
o = d.add(pc.make("circle"))
d.checkpoint()
for i in range(20):  # a drag = many small moves, one checkpoint
    pc.translate(o, 1, 0)
check("drag moved", o["cx"] == 20)
check("undo whole drag", d.undo() and d.objects[0]["cx"] == 0)
check("redo", d.redo() and d.objects[0]["cx"] == 20)
check("redo empty", not d.redo())
d.checkpoint()
d.remove([d.objects[0]["id"]])
check("undo delete", d.undo() and len(d.objects) == 1)
d.checkpoint()
check("new change clears redo", not d._redo)
check("undo empty", pc.Document().undo() is False)

# duplicate, order
d = pc.Document()
x = d.add(pc.make("point"))
y = d.add(pc.make("point"))
dup = d.duplicate([x["id"]])
check("duplicate", len(d.objects) == 3 and dup[0]["id"] not in (x["id"], y["id"]))
d.move_order(x["id"], 1)
check("reorder", d.objects[1] is x)
d.move_order(x["id"], 10)
check("reorder bounds", d.objects[1] is x)

# view
v = pc.View(2.0, 10, 20)
check("view roundtrip", all(near(a, b) for a, b in zip(v.to_doc(*v.to_screen(3, 4)), (3, 4))))
before = v.to_doc(100, 100)
v.zoom_at(100, 100, 1.5)
check("zoom keeps cursor point", all(near(a, b, 1e-6) for a, b in zip(before, v.to_doc(100, 100))))
v.zoom_at(0, 0, 1e9)
check("zoom clamped", v.zoom <= 200)
v.fit((0, 0, 100, 100), 300, 200)
check("fit", v.to_screen(0, 0)[0] > 0 and v.to_screen(100, 100)[1] < 200)

# snapping
d = pc.Document()
d.add(pc.make("line", x1=0, y1=0, x2=100, y2=0))
d.add(pc.make("rect", x=200, y=200, w=40, h=40))
d.add(pc.make("circle", cx=-100, cy=-100, r=10))
sx, sy, k = pc.snap(d, 99, 1, 5)
check("snap endpoint", (sx, sy, k) == (100, 0, "endpoint"))
sx, sy, k = pc.snap(d, 51, 2, 5)
check("snap midpoint", (sx, sy, k) == (50, 0, "midpoint"))
check("snap corner", pc.snap(d, 241, 239, 5)[2] == "corner")
check("snap center", pc.snap(d, -99, -101, 5)[2] == "center")
d.add(pc.make("line", x1=70, y1=-50, x2=70, y2=80))
check("snap intersection", pc.snap(d, 71, 1, 3)[2] == "intersection")
d2 = pc.Document()
d2.settings["grid_spacing"] = 20
check("snap grid", pc.snap(d2, 38, 22, 3) == (40, 20, "grid"))
check("snap off", pc.snap(d2, 38, 22, 3, grid=False)[2] is None)
d2.add(pc.make("point", x=7, y=900))
check("snap align", pc.snap(d2, 8, 300, 3, grid=False, points=False, align=True)[:3] == (7, 300, "align"))
check("snap excludes dragged", pc.snap(d, 99, 1, 5, exclude=[d.objects[0]["id"]])[2] != "endpoint")

# alignment
a1 = pc.make("rect", x=0, y=0, w=10, h=10)
a2 = pc.make("rect", x=30, y=20, w=20, h=10)
pc.align([a1, a2], "left")
check("align left", a1["x"] == a2["x"] == 0)
pc.align([a1, a2], "bottom")
check("align bottom", a1["y"] == a2["y"])
pc.align([a1, a2], "hcenter")
check("align hcenter", near(pc.center(a1)[0], pc.center(a2)[0]))

# save / load
d = pc.Document()
d.settings["grid_spacing"] = 25.0
d.add(pc.make("circle", r=7, style={"stroke": "#112233", "dash": "dashed"}))
d.add(pc.make("freehand", points=[[0, 0], [1, 2], [3, 4]]))
d.add(pc.make("text", text="héllo\nworld"))
d2 = pc.Document.from_json(d.to_json())
check("roundtrip objects", d2.objects == d.objects)
check("roundtrip settings", d2.settings["grid_spacing"] == 25.0)
check("ids continue", d2.add(pc.make("point"))["id"] == 4)
for bad in ("{", "[]", '{"format": "x"}', '{"format":"srbd","version":99}'):
    try:
        pc.Document.from_json(bad)
        check("reject " + bad, False)
    except ValueError:
        pass
evil = {"format": "srbd", "version": 1, "settings": {"width": "x", "grid_spacing": -5, "units": "<b>"},
        "objects": [{"type": "circle", "r": "nan"}, {"type": "bogus"}, 5,
                    {"type": "rect", "id": 3, "style": {"stroke": "red", "width": 1e9, "dash": "zig"}},
                    {"type": "rect", "id": 3}, {"type": "polygon", "n": 1}]}
d3 = pc.Document.from_dict(evil)
check("evil filtered", [o["type"] for o in d3.objects] == ["rect", "rect", "polygon"])
check("evil ids unique", len({o["id"] for o in d3.objects}) == 3)
check("evil style clamped", d3.objects[0]["style"]["width"] <= 200 and d3.objects[0]["style"]["stroke"] == "#202020")
check("evil settings", d3.settings["units"] == "u" and d3.settings["grid_spacing"] == 20.0)
check("evil polygon n", d3.objects[2]["n"] == 3)

# export
d = pc.Document()
d.settings.update(width=100.0, height=50.0)
d.add(pc.make("line", x1=0, y1=3, x2=10, y2=3))
d.add(pc.make("text", text="a<b & c", x=5, y=5))
d.add(pc.make("arrow"))
d.add(pc.make("rect", style={"dash": "dotted"}))
hidden = d.add(pc.make("circle"))
hidden["visible"] = False
svg = pc.to_svg(d)
check("svg y flipped", 'y1="47.000"' in svg)
check("svg escaped", "a&lt;b &amp; c" in svg and "a<b" not in svg)
check("svg hidden skipped", "<circle" not in svg)
check("svg header", svg.startswith("<svg") and svg.rstrip().endswith("</svg>"))
try:
    import PIL  # noqa: F401
    img = pc.render_png(d, 2.0)
    check("png size", img.size == (200, 100))
    timg = pc.render_png(d, 1.0, transparent=True)
    check("png alpha", timg.mode == "RGBA" and timg.getpixel((50, 25))[3] == 0)
    # the line (y=0) must be at the bottom row
    check("png y flipped", pc.render_png(d, 1.0).getpixel((5, 47)) != (255, 255, 255))
except ImportError:
    pass

check("exact circle", pc.exact(pc.make("circle", r=3), "Area") == "9π")
check("exact sqrt2", pc.exact(pc.make("square", side=2), "Diagonal") == "2√2")
check("exact none", pc.exact(pc.make("point"), "Area") == "")
check("exact line", pc.exact(pc.make("line", x2=1, y2=1), "Length") == "√2")

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
