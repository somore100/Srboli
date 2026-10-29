# tests/test_table_core.py - no display needed (python3 tests/test_table_core.py)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import table_core as T

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

def table(*rows):
    return {"name": "t", "cells": [[{"t": v, "bg": "", "fg": ""} for v in r] for r in rows]}

# colours
check("norm 6", T.norm_color("#ff0aab"), "#FF0AAB")
check("norm 3", T.norm_color("f0a"), "#FF00AA")
check("norm bad", (T.norm_color("red"), T.norm_color(None), T.norm_color("#12")), ("", "", ""))

# normalize
t = T.normalize([{"name": "A", "cells": [[{"t": "1", "bg": "#fff"}], [5, None, "x"]]},
                 {"name": "A", "cells": [["q"]]}, {"cells": "bad"}, "junk"])
check("rectangular", [len(r) for r in t[0]["cells"]], [3, 3])
check("colour cleaned", t[0]["cells"][0][0]["bg"], "#FFFFFF")
check("non-dict cell text", (t[0]["cells"][1][0]["t"], t[0]["cells"][1][1]["t"]), ("5", ""))
check("unique names, junk dropped", [x["name"] for x in t], ["A", "A 2"])
check("normalize empty/garbage", (T.normalize(None), T.normalize([{"name": "x", "cells": []}])), ([], []))
check("limits", T.size(T.normalize([{"name": "b", "cells": [["x"] * 99] * 300}])[0]), (T.MAX_ROWS, T.MAX_COLS))

# old sheet import
check("sheet empty", T.from_sheet([["", ""], ["", ""]]), None)
s = T.from_sheet([["a", ""], ["", ""], ["", "b"], ["", ""]])
check("sheet trimmed", (T.size(s), s["cells"][2][1]["t"], s["name"]), ((3, 2), "b", "Sheet 1"))

# names
check("unique", T.unique_name([{"name": "X"}, {"name": "X 2"}], "X"), "X 3")
check("unique skip self", T.unique_name([{"name": "X"}], "X", skip=0), "X")
check("name strips brackets", T.unique_name([], "a[[b]]"), "ab")
check("find", T.find([{"name": "X"}], "X") is not None and T.find([], "X") is None, True)

# structure
t = T.blank_table("n", 2, 2)
check("add_row after 0", (T.add_row(t, 0), T.size(t)), (True, (3, 2)))
t["cells"][1][0]["t"] = "new?"
check("delete_row", (T.delete_row(t, 1), T.size(t)), (True, (2, 2)))
check("add_col end", (T.add_col(t), T.size(t)), (True, (2, 3)))
check("delete_col", (T.delete_col(t, 0), T.size(t)), (True, (2, 2)))
one = T.blank_table("o", 1, 1)
check("keep last row/col", (T.delete_row(one, 0), T.delete_col(one, 0)), (False, False))
big = T.blank_table("b", T.MAX_ROWS, T.MAX_COLS)
check("max size", (T.add_row(big), T.add_col(big)), (False, False))

# colours by scope
t = T.blank_table("c", 3, 3)
check("cell", T.set_color(t, 1, 1, "bg", "#f00"), [(1, 1)])
check("row", len(T.set_color(t, 1, 1, "bg", "#00ff00", "row")), 3)
check("col", sorted(T.set_color(t, 0, 2, "fg", "#000", "col")), [(0, 2), (1, 2), (2, 2)])
check("all clear", len(T.set_color(t, 0, 0, "bg", "", "all")), 3)   # only the 3 coloured change
check("no-op change reports nothing", T.set_color(t, 0, 0, "bg", "", "cell"), [])
try:
    T.set_color(t, 0, 0, "zz", "#fff"); check("bad key", False, True)
except ValueError:
    check("bad key", True, True)

# formulas
t = table(["1", "2", "x"], ["3", "", "4.5"], ["10", "20", "30"])
check("SUM", T.eval_formula(t, "SUM(A1:A3)"), 14.0)
check("sum 2d skips text/empty", T.eval_formula(t, "sum(a1:c2)"), 10.5)
check("AVG", T.eval_formula(t, "AVG(A1:A3)"), 14 / 3)
check("COUNT", T.eval_formula(t, "COUNT(A1:C3)"), 7)
check("MAX/MIN", (T.eval_formula(t, "MAX(A1:C3)"), T.eval_formula(t, "MIN(A1:C3)")), (30.0, 1.0))
check("reversed range", T.eval_formula(t, "SUM(A3:A1)"), 14.0)
check("empty AVG/MAX", (T.eval_formula(t, "AVG(B2:B2)"), T.eval_formula(t, "MAX(B2:B2)")), (0, 0))
check("arithmetic", T.eval_formula(t, "2*(3+4)-1"), 13)
check("cell refs", T.eval_formula(t, "A1+B1*2"), 5.0)
check("empty/text ref is 0", T.eval_formula(t, "B2+C1+1"), 1.0)
check("ref out of table", T.eval_formula(t, "Z9+1"), 1.0)
for bad in ("9**9**9", "__import__('os')", "FOO(A1)", "SUM(A1)", "1/0"):
    try:
        T.eval_formula(t, bad); check("rejects " + bad, False, True)
    except Exception:
        check("rejects " + bad, True, True)
check("format ints", (T.format_number(3.0), T.format_number(0.1 + 0.2), T.format_number(2.5), T.format_number(7)), ("3", "0.3", "2.5", "7"))

# output
t = table(["Day", "A|B"], ["Mon", ""])
t["cells"][0][0]["bg"] = "#112233"; t["cells"][0][0]["fg"] = "#FFFFFF"
check("markdown", T.to_markdown(t), "| Day | A\\|B |\n| --- | --- |\n| Mon |   |")
h = T.to_html(table(["<b>&"]))
check("html escaped", "&lt;b&gt;&amp;" in h and "<b>" not in h, True)
check("html colours", 'background:#112233;color:#FFFFFF;' in T.to_html(t), True)

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
