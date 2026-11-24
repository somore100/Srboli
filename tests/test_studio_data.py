import os
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import studio_core as sc  # noqa: E402
from core import studio_data as sd  # noqa: E402

fails = 0


def check(name, cond):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name)


def near(a, b, e=1e-6):
    return abs(a - b) <= e


def png(w, h):
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# formulas
cells = [["Item", "Qty", "Price", "Total"], ["a", "2", "3", "=B2*C2"], ["b", "4", "1.5", "=B3*C3"],
         ["Sum", "", "", "=SUM(D2:D3)"], ["bad", "", "", "=1/0"], ["x", "", "", "=ZZ"], ["", "", "", "=D4+1"]]
g = sd.display_grid(cells)
check("formula product", g[1][3] == "6" and g[2][3] == "6")
check("sum of formulas", g[3][3] == "12")
check("formula chain", g[6][3] == "13")
check("error shown", g[4][3] == "#ERR")
check("raw kept", cells[1][3] == "=B2*C2")
cyc = [["=B1", "=A1"]]
sd.display_grid(cyc)       # a loop must not hang or raise

# table edits
t = sc.make("table")
n0, h0 = len(t["cells"]), t["h"]
check("add row", sd.add_row(t) and len(t["cells"]) == n0 + 1 and near(t["h"], h0 * (n0 + 1) / n0))
check("add row after", sd.add_row(t, 0) and t["cells"][1] == [""] * 3)
check("delete row", sd.delete_row(t, 1) and len(t["cells"]) == n0 + 1)
check("add col", sd.add_col(t) and len(t["cells"][0]) == 4)
check("delete col", sd.delete_col(t, 3) and len(t["cells"][0]) == 3)
one = sc.make("table", cells=[["x"]])
check("keeps last row and col", not sd.delete_row(one, 0) and not sd.delete_col(one, 0))
big = sc.make("table", cells=[["x"]] * sd.MAX_ROWS)
check("row limit", not sd.add_row(big))
check("set cell", sd.set_cell(t, 0, 0, "Name") and t["cells"][0][0] == "Name" and not sd.set_cell(t, 99, 0, "x"))

# sort and filter
t = sc.make("table", cells=[["n", "v"], ["b", "10"], ["a", "9"], ["c", "100"], ["d", "x"]])
sd.sort_rows(t, 1)
check("numeric sort, text last", [r[1] for r in t["cells"]] == ["v", "9", "10", "100", "x"])
sd.sort_rows(t, 0, desc=True)
check("text sort desc keeps header", [r[0] for r in t["cells"]] == ["n", "d", "c", "b", "a"])
check("sort bad column", not sd.sort_rows(t, 9))
t["fcol"], t["ftext"] = 0, "B"
check("filter keeps header", sd.visible_rows(t) == [0, 3])
t["ftext"] = ""
check("no filter all rows", sd.visible_rows(t) == [0, 1, 2, 3, 4])

# parse
check("tsv", sd.parse_table_text("a\tb\n1\t2") == [["a", "b"], ["1", "2"]])
check("csv quotes", sd.parse_table_text('a,b\n"x,y",2') == [["a", "b"], ["x,y", "2"]])
check("semicolon", sd.parse_table_text("a;b\n1;2")[1] == ["1", "2"])
check("markdown", sd.parse_table_text("| a | b |\n|---|---|\n| 1 | 2 |") == [["a", "b"], ["1", "2"]])
check("ragged padded", sd.parse_table_text("a,b,c\n1,2") == [["a", "b", "c"], ["1", "2", ""]])
for bad in ("", "  \n ", "\n".join(["a,b"] * 101)):
    try:
        sd.parse_table_text(bad)
        check("reject " + repr(bad[:5]), False)
    except ValueError:
        pass
check("csv export", sd.to_csv([["a", "b"], ["x,y", "=1+1"]]) == 'a,b\n"x,y",2\n')
check("col parse", sd.parse_col("c") == 2)
try:
    sd.parse_col("AB")
    check("col reject", False)
except ValueError:
    pass

# chart data and layout
d = sc.Document()
tb = d.add(sc.make("table", cells=[["Region", "2024", "2025"], ["N", "12", "15"], ["S", "9", "11"], ["W", "14", "x"]]))
ch = d.add(sc.make("chart", source=tb["id"], value_cols=[1, 2]))
sc.refresh_charts(d)
cd = sd.chart_data(ch, tb)
check("labels from table", cd["labels"] == ["N", "S", "W"] and cd["names"] == ["2024", "2025"])
check("series values", cd["series"] == [[12, 9, 14], [15, 11, 0]])
check("cached in chart", ch["data"]["series"][0] == [12, 9, 14])
sc.set_geom(d, tb, "x", 5)
sd.set_cell(tb, 1, 1, "20")
sc.refresh_charts(d)
check("chart follows table edit", ch["data"]["series"][0][0] == 20)
tb["fcol"], tb["ftext"] = 0, "s"
sc.refresh_charts(d)
check("chart follows filter", ch["data"]["labels"] == ["S"])
tb["ftext"] = ""
sc.refresh_charts(d)
d.remove([tb["id"]])
sc.refresh_charts(d)
check("deleted source falls back to cache", ch["source"] is None and ch["data"]["labels"] == ["N", "S", "W"])
check("chart without table uses own data", sd.chart_data(sc.make("chart"), None)["labels"] == ["A", "B", "C", "D"])

tk = sd.nice_ticks(0, 23)
check("nice ticks", tk[0] == 0 and tk[-1] >= 23 and all(near(tk[i + 1] - tk[i], tk[1] - tk[0], 1e-9) for i in range(len(tk) - 1)))
check("nice ticks flat", sd.nice_ticks(5, 5)[-1] > 5)
check("nice ticks negative", sd.nice_ticks(-7, 3)[0] <= -7)
data = {"labels": ["a", "b", "c"], "names": ["s1", "s2"], "series": [[1, 2, 3], [3, 2, -1]]}
oc = sc.make("chart", kind="bar")
lay = sd.chart_layout(oc, data, 400, 300)
check("bars per value", len(lay["bars"]) == 6)
px, py, pw, ph = lay["plot"]
check("bars inside plot", all(px <= b[0] and b[0] + b[2] <= px + pw + 1e-6 and py - 1e-6 <= b[1] and b[1] + b[3] <= py + ph + 1e-6 for b in lay["bars"]))
check("negative bar goes below zero line", lay["bars"][5][1] >= lay["zero_y"] - 1e-6)
check("legend for two series", len(lay["legend"]) == 2)
oc["kind"] = "line"
check("lines", len(sd.chart_layout(oc, data, 400, 300)["lines"]) == 2)
oc["kind"] = "pie"
pie = sd.chart_layout(oc, {"labels": ["a", "b"], "names": ["s"], "series": [[1, 3]]}, 300, 300)
check("pie slices sum", near(sum(s[1] for s in pie["slices"]), 360) and near(pie["slices"][0][1], 90))
check("pie zeros", sd.chart_layout(oc, {"labels": ["a"], "names": ["s"], "series": [[0]]}, 300, 300)["slices"] == [])
oc["title"] = "T"
check("title makes room", sd.chart_layout(oc, data, 400, 300)["plot"][1] > 20)
check("clean data junk", sd.clean_chart_data({"labels": 5})["labels"] == ["A", "B", "C", "D"])
check("clean data pads", sd.clean_chart_data({"labels": ["a", "b"], "names": [], "series": [[1]]})["series"] == [[1.0, 0.0]])

# images
check("png size", sd.image_size(png(7, 3)) == (7, 3))
check("gif size", sd.image_size(b"GIF89a" + struct.pack("<HH", 5, 6) + b"\0" * 8) == (5, 6))
jpg = b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0" + b"\0" * 9 + b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", 20, 30) + b"\0" * 10
check("jpeg size", sd.image_size(jpg) == (30, 20))
check("not an image", sd.image_size(b"hello world, not a picture") is None and sd.image_size(b"") is None)
check("asset names", sd.safe_asset_name("../../etc/pass wd.PNG") == "pass_wd.png"
      and sd.safe_asset_name("a.png", {"a.png"}) == "a_2.png" and sd.safe_asset_name("x.exe").endswith(".png"))

d = sc.Document()
img = sc.add_image(d, "photo.png", png(100, 50))
check("image object", img["asset"] == "photo.png" and img["w"] == 100 and img["h"] == 50 and "photo.png" in d.assets)
big = sc.add_image(d, "photo.png", png(1000, 500))
check("image scaled and renamed", big["w"] == 480 and big["h"] == 240 and big["asset"] == "photo_2.png")
for bad in (b"junk", b"\x89PNG\r\n\x1a\n" + b"\0" * 4):
    try:
        sc.add_image(d, "x.png", bad)
        check("reject image", False)
    except ValueError:
        pass
d.add(img)

# package round trip with assets, unused ones dropped
d.add(sc.make("table"))
tb2 = d.objects[-1]
d.add(sc.make("chart", source=tb2["id"]))
d.add(sc.make("text"))
sc.refresh_charts(d)
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "a.srbcanvas")
    sc.save_package(d, p)
    import zipfile
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
    check("used asset stored, unused not", "assets/photo.png" in names and "assets/photo_2.png" not in names)
    d2, _, _ = sc.load_package(p)
    check("assets loaded", d2.assets.get("photo.png") == d.assets["photo.png"])
    check("objects equal", d2.objects == d.objects)
    check("chart link survives", [o for o in d2.objects if o["type"] == "chart"][0]["source"] == tb2["id"])
    with zipfile.ZipFile(os.path.join(tmp, "evil.srbcanvas"), "w") as z:
        z.writestr("manifest.json", '{"format":"srbcanvas","version":1}')
        z.writestr("canvas.json", '{"version":1,"objects":[]}')
        z.writestr("assets/notimage.png", b"junk")
        z.writestr("assets/../../escape.png", png(2, 2))
    d3, _, _ = sc.load_package(os.path.join(tmp, "evil.srbcanvas"))
    check("junk asset skipped, path stripped", "notimage.png" not in d3.assets and "escape.png" in d3.assets)

# sanitising untrusted objects
evil = {"version": 1, "objects": [
    {"type": "table", "id": 1, "cells": [["a", None, 5], "oops", ["b"]], "fcol": 99, "size": 1e5, "hdr_bg": "red"},
    {"type": "table", "id": 2, "cells": "nope"},
    {"type": "chart", "id": 3, "source": 99, "kind": "radar", "value_cols": [1, "x", -2, 30, 2], "data": {"labels": "x"}},
    {"type": "chart", "id": 4, "source": 1, "label_col": 500},
    {"type": "chart", "id": 5, "source": 3},
    {"type": "image", "id": 6, "asset": "../../x.png"}]}
dd = sc.Document.from_dict(evil)
tbl = dd.get(1)
check("table made rectangular", all(len(r) == 3 for r in tbl["cells"]) and tbl["cells"][0] == ["a", "", "5"])
check("table fcol/size/colour clamped", tbl["fcol"] == -1 and tbl["size"] <= 200 and tbl["hdr_bg"] == "#2F5597")
check("bad cells replaced", dd.get(2)["cells"] == sd.default_cells())
c3 = dd.get(3)
check("chart dangling source cleared", c3["source"] is None and c3["kind"] == "bar")
check("chart value cols cleaned", c3["value_cols"] == [1, 2])
check("chart data cleaned", c3["data"]["labels"] == ["A", "B", "C", "D"])
check("chart label col clamped", dd.get(4)["label_col"] <= 25 and dd.get(4)["source"] == 1)
check("chart cannot source a chart", dd.get(5)["source"] is None)
check("asset path stripped", dd.get(6)["asset"] == "x.png")

# duplicate remaps the link
d = sc.Document()
tb = d.add(sc.make("table"))
ch = d.add(sc.make("chart", source=tb["id"]))
dup = d.duplicate([tb["id"], ch["id"]])
newt = [o for o in dup if o["type"] == "table"][0]
newc = [o for o in dup if o["type"] == "chart"][0]
check("duplicate relinks chart", newc["source"] == newt["id"])
dup2 = d.duplicate([ch["id"]])
check("lone chart copy keeps source", dup2[0]["source"] == tb["id"])
snap = d._snap()
d.checkpoint()
sd.set_cell(tb, 1, 1, "99")
d.undo()
check("undo restores table", d.get(tb["id"])["cells"][1][1] == "12")

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
