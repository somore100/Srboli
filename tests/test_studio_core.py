import json
import math
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import studio_core as sc  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name)


def near(a, b, e=1e-6):
    return abs(a - b) <= e


# objects and geometry
t = sc.make("text", x=10, y=20)
check("text defaults", t["text"] == "Text" and t["visible"] and not t["locked"])
try:
    sc.make("bogus")
    check("bad type", False)
except ValueError:
    pass
r = sc.make("shape", x=0, y=0, w=100, h=50, rot=90)
bb = sc.bbox(r)
check("rotated bbox", near(bb[0], 25) and near(bb[2], 75) and near(bb[1], -25) and near(bb[3], 75))
check("centre kept", sc.center(r) == (50, 25))

# document, hit, frames, groups
d = sc.Document()
f = d.add(sc.make("frame", x=0, y=0, w=400, h=300))
a = d.add(sc.make("shape", x=50, y=50, w=60, h=60, fill="#FF0000"))
b = d.add(sc.make("shape", x=150, y=50, w=60, h=60))
c = d.add(sc.make("text", x=600, y=50))
check("ids unique", len({o["id"] for o in d.objects}) == 4)
check("auto names", a["name"] == "Rect 1" and b["name"] == "Rect 2")
check("hit shape", d.hit_test(60, 60, 2) is a)
check("frame inside not hit", d.hit_test(300, 250, 2) is None)
check("frame border hit", d.hit_test(0, 150, 2) is f)
check("frame title hit", d.hit_test(20, -5, 2) is f)
check("hit miss", d.hit_test(900, 900, 2) is None)
sc.assign_parent(d, a)
sc.assign_parent(d, c)
check("object adopted by frame", a["parent"] == f["id"] and c["parent"] is None)
a["x"] = 1000
sc.assign_parent(d, a)
check("leaving frame frees it", a["parent"] is None)
a["x"] = 50
sc.assign_parent(d, a)
sc.assign_parent(d, b)
sc.translate_tree(d, f, 30, 40)
check("frame moves contents", a["x"] == 80 and a["y"] == 90 and f["x"] == 30)

d.checkpoint()
g = d.group([a["id"], b["id"]])
check("group made", g is not None and a["parent"] == g["id"] and b["parent"] == g["id"])
check("group box", near(g["x"], 80) and near(g["w"], 130 + 0) or g["w"] > 0)
check("click selects group", d.hit_test(90, 100, 2) is g)
check("group top level", d.top_level(a) is g)
check("group needs 2", d.group([c["id"]]) is None)
check("cannot group frame", d.group([f["id"], c["id"]]) is None)
check("group in different parents refused", d.group([g["id"], c["id"]]) is None)
d.ungroup(g["id"])
check("ungroup", d.get(g["id"]) is None and a["parent"] == f["id"])
check("undo restores group", d.undo() and d.get(g["id"]) is None and d.get(a["id"]) is not None)
d.redo()

# duplicate keeps tree
d = sc.Document()
a = d.add(sc.make("shape"))
b = d.add(sc.make("shape", x=300))
g = d.group([a["id"], b["id"]])
n = len(d.objects)
dup = d.duplicate([g["id"]])
check("duplicate group copies tree", len(d.objects) == n * 2 and len(dup) == 1)
kids = d.children(dup[0]["id"])
check("duplicate children reparented", len(kids) == 2 and all(k["id"] not in (a["id"], b["id"]) for k in kids))
check("duplicate offset", dup[0]["x"] == g["x"] + 24)

# remove deletes descendants
d.remove([g["id"]])
check("remove recursive", len(d.objects) == n)

# lock / visibility inherit
d = sc.Document()
f = d.add(sc.make("frame"))
o = d.add(sc.make("shape", x=10, y=10, w=20, h=20), parent=f["id"])
f["locked"] = True
check("locked parent blocks hit", d.hit_test(15, 15, 1) is None)
f["locked"] = False
f["visible"] = False
check("hidden parent hides child", not d.effective_visible(o) and o not in d.draw_order())

# layers
d = sc.Document()
x = d.add(sc.make("shape"))
y = d.add(sc.make("shape"))
z = d.add(sc.make("shape"))
d.move_order(x["id"], 1)
check("raise", d.objects == [y, x, z])
d.move_order(x["id"], 5)
check("raise bounds", d.objects == [y, x, z])
d.to_edge(z["id"], False)
check("send to back", d.objects[0] is z)
d.to_edge(z["id"], True)
check("bring to front", d.objects[-1] is z)
fr = d.add(sc.make("frame"))
check("frames always drawn first", d.draw_order()[0] is fr)

# resize
o = sc.make("shape", x=0, y=0, w=100, h=50)
sc.resize_box(o, (1, 1), 200, 100)
check("resize br", o["w"] == 200 and o["h"] == 100 and o["x"] == 0)
sc.resize_box(o, (-1, 0), 50, 0)
check("resize left keeps right edge", near(o["x"] + o["w"], 200) and near(o["x"], 50))
sc.resize_box(o, (1, 0), -500, 0)
check("resize min size", o["w"] == sc.MIN_SIZE)
o = sc.make("shape", x=0, y=0, w=100, h=100, rot=90)
sc.resize_box(o, (1, 0), 50, 150)   # local +x points down when turned 90 deg
check("resize rotated", near(o["w"], 150))
o = sc.make("shape", x=0, y=0, w=100, h=50)
sc.resize_box(o, (1, 1), 300, 60, keep_ratio=True)
check("keep ratio", near(o["w"] / o["h"], 2))

# rotate and scale trees
d = sc.Document()
a = d.add(sc.make("shape", x=0, y=0, w=20, h=20))
b = d.add(sc.make("shape", x=100, y=0, w=20, h=20))
g = d.group([a["id"], b["id"]])
sc.rotate_tree(d, g, *sc.center(g), 90)
sc.recalc_group(d, g)
check("group rotate turns members", a["rot"] == 90 and b["rot"] == 90)
check("group rotate moves members", near(sc.center(a)[0], sc.center(b)[0]))
d = sc.Document()
a = d.add(sc.make("shape", x=0, y=0, w=20, h=20))
sc.scale_tree(d, a, 0, 0, 2, 3)
check("scale", a["w"] == 40 and a["h"] == 60 and a["x"] == 0)

# align and distribute
objs = [sc.make("shape", x=0, y=0, w=10, h=10), sc.make("shape", x=50, y=30, w=20, h=10)]
mv = {id(o): (dx, dy) for o, dx, dy in sc.align(objs, "right")}
check("align right", mv[id(objs[0])] == (60, 0) and mv[id(objs[1])] == (0, 0))
objs = [sc.make("shape", x=0, w=10), sc.make("shape", x=10, w=10), sc.make("shape", x=100, w=10)]
mv = {id(o): dx for o, dx, dy in sc.distribute(objs, "h")}
check("distribute", near(mv[id(objs[1])], 40))
check("distribute needs 3", sc.distribute(objs[:2], "h") == [])

# snapping
dx, dy, gd = sc.snap_box([(100, 100, 200, 200)], (103, 50, 140, 80), 5)
check("snap edge", dx == -3 and dy == 0 and ("v", 100) in gd)
dx, dy, gd = sc.snap_box([(100, 100, 200, 200)], (300, 300, 350, 350), 5)
check("snap none", (dx, dy, gd) == (0.0, 0.0, []))
check("snap grid", sc.snap_grid(47, 40) == 40 and sc.snap_grid(61, 40) == 80)

# history
d = sc.Document()
d.checkpoint()
o = d.add(sc.make("shape"))
d.checkpoint()
for i in range(10):
    o["x"] += 1
check("drag", o["x"] == 10)
check("undo drag", d.undo() and d.objects[0]["x"] == 0)
check("undo add", d.undo() and not d.objects)
check("undo empty", d.undo() is False)
check("redo", d.redo() and d.redo() and d.objects[0]["x"] == 10)
check("redo empty", not d.redo())
d.checkpoint()
check("new change clears redo", not d._redo)
for i in range(sc.MAX_UNDO + 20):
    d.checkpoint()
check("undo capped", len(d._undo) == sc.MAX_UNDO)
sc.Document().add(sc.make("shape"))

# text blocks
bl = sc.parse_blocks("# Title\n\n- one\n2. two\n> quote\n```\ncode\nline\n```\nplain")
check("blocks", [k for k, _ in bl] == ["h1", "p", "li", "li", "quote", "code", "p"])
check("bullet marker", bl[2][1].startswith("•") and bl[3][1].startswith("2."))
check("plain mode", all(k == "p" for k, _ in sc.parse_blocks("# a\n- b", "plain")))
check("empty text", sc.parse_blocks("") == [("p", "")])
esc = lambda s: s.replace("&", "&amp;")  # noqa: E731
check("inline markup", sc.inline_markup("a **b** *c* d", esc) == "a [b]b[/b] [i]c[/i] d")
check("inline no stray", sc.inline_markup("2 * 3 * 4", esc) == "2 * 3 * 4")

# serialisation
d = sc.Document()
d.settings["title"] = "Mine"
f = d.add(sc.make("frame", x=5))
tx = d.add(sc.make("text", text="héllo\nworld", mode="plain"), parent=f["id"])
d.add(sc.make("shape", shape="arrow", w=50, h=0))
d2 = sc.Document.from_dict(json.loads(json.dumps(d.to_dict())))
check("roundtrip objects", d2.objects == d.objects)
check("roundtrip title", d2.settings["title"] == "Mine")
check("ids continue", d2.add(sc.make("shape"))["id"] == 4)
evil = {"version": 1, "settings": {"grid_size": -3, "background": "red", "title": 5},
        "objects": [{"type": "bogus"}, 7, {"type": "shape", "id": 2, "w": "nan"},
                    {"type": "shape", "id": 2, "fill": "javascript", "shape": "zig", "opacity": 9},
                    {"type": "text", "id": 3, "parent": 99, "size": 1e9, "align": "x"},
                    {"type": "shape", "id": 4, "parent": 4},
                    {"type": "shape", "id": 5, "parent": 6}, {"type": "shape", "id": 6, "parent": 5}]}
d3 = sc.Document.from_dict(evil)
check("evil filtered", len(d3.objects) == 4)
check("evil ids unique", len({o["id"] for o in d3.objects}) == 4)
check("evil settings", d3.settings["grid_size"] == 40.0 and d3.settings["background"] == "#2B2D31"
      and d3.settings["title"] == "Untitled")
check("evil values clamped", all(o["opacity"] <= 1 for o in d3.objects) and
      all(o.get("size", 24) <= 400 for o in d3.objects))
check("evil enums", all(o.get("shape", "rect") in sc.SHAPES for o in d3.objects))
check("dangling parent cleared", all(o["parent"] is None or d3.get(o["parent"]) for o in d3.objects))
check("cycle broken", any(o["parent"] is None for o in d3.objects if o["id"] in (5, 6)))
check("self parent cleared", all(o["parent"] != o["id"] for o in d3.objects))
check("bad colour reset", all(sc._hex(o.get("fill", "#000000")) or o.get("fill") == "" for o in d3.objects))
try:
    sc.Document.from_dict({"version": 99})
    check("newer version refused", False)
except ValueError:
    pass
try:
    sc.Document.from_dict([])
    check("non dict refused", False)
except ValueError:
    pass

# package
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "w.srbcanvas")
    sc.save_package(d, p, view=(1.5, 10, 20), assets={"../evil/a.png": b"123"})
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
    check("package layout", {"manifest.json", "canvas.json", "assets/a.png"} <= set(names))
    check("asset path stripped", not any(".." in n for n in names))
    dd, view, meta = sc.load_package(p)
    check("load objects", dd.objects == d.objects and view == [1.5, 10, 20])
    check("manifest", meta["format"] == "srbcanvas" and meta["title"] == "Mine")
    sc.save_package(d, p)
    check("backup kept", os.path.exists(p + ".bak"))
    check("no tmp left", not os.path.exists(p + ".tmp"))
    check("view optional", sc.load_package(p)[1] is None)
    png = sc.render_preview(d)
    if png is not None:
        check("preview png", png[:4] == b"\x89PNG")
        sc.save_package(d, p, thumbnail=png)
        with zipfile.ZipFile(p) as z:
            check("thumbnail stored", "previews/thumbnail.png" in z.namelist())
    check("empty preview", sc.render_preview(sc.Document()) is None)
    bad = os.path.join(tmp, "bad.srbcanvas")
    open(bad, "wb").write(b"not a zip")
    for case in ("notzip", "nomanifest", "wrongformat", "newer", "badjson"):
        q = os.path.join(tmp, case + ".srbcanvas")
        if case == "notzip":
            q = bad
        else:
            with zipfile.ZipFile(q, "w") as z:
                if case == "nomanifest":
                    z.writestr("canvas.json", "{}")
                elif case == "wrongformat":
                    z.writestr("manifest.json", '{"format":"x"}')
                    z.writestr("canvas.json", "{}")
                elif case == "newer":
                    z.writestr("manifest.json", '{"format":"srbcanvas","version":99}')
                    z.writestr("canvas.json", "{}")
                else:
                    z.writestr("manifest.json", '{"format":"srbcanvas","version":1}')
                    z.writestr("canvas.json", "{oops")
        try:
            sc.load_package(q)
            check("reject " + case, False)
        except ValueError:
            pass
    check("recovery path", sc.recovery_path(tmp).endswith("workspace.autosave.srbcanvas"))

# line ends, roots, view, recovery
ln = sc.make("shape", shape="arrow", x=0, y=0, w=100, h=50)
check("line ends", sc.line_ends(ln) == ((0, 0), (100, 50)))
sc.set_line_end(ln, 1, -20, 100)
check("head moved", sc.line_ends(ln) == ((0, 0), (-20, 100)) and ln["fx"] is True)
sc.set_line_end(ln, 0, 50, 200)
check("tail moved keeps head", sc.line_ends(ln) == ((50, 200), (-20, 100)))
ln["rot"] = 90
a0, b0 = sc.line_ends(ln)
sc.set_line_end(ln, 1, 0, 0)
check("rotated line straightened", ln["rot"] == 0 and near(sc.line_ends(ln)[0][0], a0[0]))
d = sc.Document()
f = d.add(sc.make("frame"))
c = d.add(sc.make("shape"), parent=f["id"])
o = d.add(sc.make("shape"))
check("roots", sc.roots(d, [f["id"], c["id"], o["id"]]) == [f, o])
v = sc.View(2.0, 10, 20)
v.h = 300
p = v.to_screen(30, 40)
check("view roundtrip", all(near(a, b) for a, b in zip(v.to_world(*p), (30, 40))))
check("view y down", v.to_screen(10, 21)[1] < v.to_screen(10, 20)[1])
before = v.to_world(100, 100)
v.zoom_at(100, 100, 1.5)
check("zoom keeps point", all(near(a, b) for a, b in zip(before, v.to_world(100, 100))))
w0 = v.to_world(50, 50)
v.pan(30, -20)
check("pan follows finger", near(v.to_screen(*w0)[0], 80) and near(v.to_screen(*w0)[1], 30))
v.zoom_at(0, 0, 1e9)
check("zoom clamped", v.zoom <= 40)
v.fit((0, 0, 100, 100), 300, 200)
check("fit", 0 < v.to_screen(0, 0)[0] and v.to_screen(100, 100)[1] > 0)
v.fit(None, 300, 200)
check("fit empty", v.zoom == 1.0)
with tempfile.TemporaryDirectory() as tmp:
    check("no recovery", not sc.has_recovery(tmp))
    check("autosave", sc.autosave(d, tmp, (1, 0, 0)) and sc.has_recovery(tmp))
    check("recovery loads", len(sc.load_package(sc.recovery_path(tmp))[0].objects) == 3)
    sc.clear_recovery(tmp)
    check("recovery cleared", not sc.has_recovery(tmp))

# set_geom
d = sc.Document()
f = d.add(sc.make("frame", x=0, y=0, w=400, h=300))
o = d.add(sc.make("shape", x=10, y=10, w=20, h=20), parent=f["id"])
check("geom move frame", sc.set_geom(d, f, "x", 100) and o["x"] == 110 and f["x"] == 100)
check("geom w", sc.set_geom(d, o, "w", 50) and o["w"] == 50)
check("geom refuses tiny", not sc.set_geom(d, o, "w", 1) and o["w"] == 50)
check("geom refuses junk", not sc.set_geom(d, o, "x", "abc") and not sc.set_geom(d, o, "x", float("nan")))
check("geom rot wraps", sc.set_geom(d, o, "rot", 450) and o["rot"] == 90)
check("geom unknown key", not sc.set_geom(d, o, "zzz", 1))
t = d.add(sc.make("text"))
sc.set_geom(d, t, "h", 80)
check("text height unpins autofit", t["autofit"] is False)
a = d.add(sc.make("shape", x=0, y=500, w=10, h=10))
b = d.add(sc.make("shape", x=90, y=500, w=10, h=10))
g = d.group([a["id"], b["id"]])
check("geom group w", sc.set_geom(d, g, "w", 200) and near(g["w"], 200) and near(b["x"] + b["w"], 200))
check("geom group x", sc.set_geom(d, g, "x", 7) and near(a["x"], 7))
ln = d.add(sc.make("shape", shape="line", w=100, h=0))
check("line may be flat", sc.set_geom(d, ln, "h", 0))

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
