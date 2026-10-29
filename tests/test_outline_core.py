# tests/test_outline_core.py - no display needed (python3 tests/test_outline_core.py)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import outline_core as O

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

def mk(spec):
    """'A B- C-- D' -> nodes; dashes = depth."""
    return [dict(O.blank_node(w.lstrip("-")), depth=len(w) - len(w.lstrip("-")))
            for w in spec.split()]
def show(o):
    return " ".join("-" * n["depth"] + n["title"] for n in o)

# normalize
check("normalize empty", len(O.normalize([])), 1)
check("normalize junk", len(O.normalize("x")), 1)
n = O.normalize([{"title": "a", "depth": 3}, {"title": "b", "depth": 9}])
check("depth clamped to prev+1", [x["depth"] for x in n], [0, 1])

# queries
o = mk("A -B --C -D E")
check("subtree_end A", O.subtree_end(o, 0), 4)
check("subtree_end B", O.subtree_end(o, 1), 3)
check("has_children", [O.has_children(o, i) for i in range(5)], [True, True, False, False, False])
check("parent", [O.parent_index(o, i) for i in range(5)], [None, 0, 1, 0, None])
o[1]["collapsed"] = True
check("visible with collapse", O.visible_indices(o), [0, 1, 3, 4])

# add
o = mk("A -B -C D")
i = O.add_sibling(o, 0, "X")
check("add_sibling goes after subtree", (show(o), i), ("A -B -C X D", 3))
i = O.add_child(o, 0, "Y")
check("add_child goes last under node", (show(o), i), ("A -B -C -Y X D", 3))

# delete
o = mk("A -B -C D")
i = O.delete_subtree(o, 0)
check("delete subtree", (show(o), i), ("D", 0))
check("last node kept", (O.delete_subtree(o, 0), len(o)), (0, 1))

# move
o = mk("A -a B -b -c C")
i = O.move(o, 0, +1)
check("move down swaps subtree", (show(o), i), ("B -b -c A -a C", 3))
i = O.move(o, 3, -1)
check("move up back", (show(o), i), ("A -a B -b -c C", 0))
check("move up at top", O.move(o, 0, -1), 0)
check("move last down", O.move(o, 5, +1), 5)
o = mk("A -a -b")
check("child can't leave its parent", (O.move(o, 2, +1), O.move(o, 1, -1)), (2, 1))

# indent / outdent
o = mk("A B -b C")
check("indent B under A", (O.indent(o, 1), show(o)), (True, "A -B --b C"))
check("first can't indent", O.indent(o, 0), False)
o = mk("A -x --y")
check("can't indent past previous+1", O.indent(o, 2), False)
o = mk("A -B --b -C")
check("outdent", (O.outdent(o, 1), show(o)), (True, "A B -b -C"))
check("outdent top", O.outdent(o, 0), False)
o = mk("A " + "-" * O.MAX_DEPTH + "B")
check("max depth", O.indent(o, 1), False)

# snippet
check("snippet plain", O.snippet("hello world"), "hello world")
check("snippet skips blank + strips markup",
      O.snippet("\n\n## **Big** [color=#ff0000]news[/color]\nlater"), "Big news")
check("snippet list + link", O.snippet("- see [docs](http://x.y)"), "see docs")
check("snippet rule/table lines skipped", O.snippet("---\n|---|\nreal"), "real")
check("snippet empty", O.snippet("  \n "), "")
check("snippet truncates", len(O.snippet("x" * 200)), 48)

# migration
md = O.paragraphs_to_markdown([
    {"text": "hello", "color": "#FF0000", "bold": True},
    {"text": "  "}, {"text": "plain", "color": "#FFFFFF"},
    {"image": "/x/a.png", "text": "[IMAGE:/x/a.png]"}])
check("paragraphs -> markdown", md,
      "[color=#FF0000]**hello**[/color]\n\nplain\n\n![image](/x/a.png)")

# output
o = [dict(O.blank_node("Intro"), body="# H\nsome **bold** and [color=#00ff00]green[/color]"),
     dict(O.blank_node("Sub", 1), body="- a\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |")]
check("to_markdown", O.to_markdown("T", o).splitlines()[:3], ["# T", "", "## Intro"])
h = O.to_html("T<", o)
check("html title escaped", "<h1>T&lt;</h1>" in h, True)
check("html heading levels", ("<h2>Intro</h2>" in h, "<h3>Sub</h3>" in h), (True, True))
check("html inline", ("<b>bold</b>" in h, 'style="color:#00ff00">green</span>' in h), (True, True))
check("html list + table", ("<ul><li><p>a</p></li>" in h, "<th" in h and "<td" in h), (True, True))
bad = O.markdown_to_html("<script>alert(1)</script> [x](https://a.b/\"onmouseover=1)")
check("html escapes", "<script>" not in bad and 'href="https://a.b/&quot;' in bad, True)

# placed tables
from core import table_core as T
tb = T.blank_table("Plan", 2, 2)
tb["cells"][0][0].update(t="Day", bg="#112233")
o = [dict(O.blank_node("A"), body="intro\n\n[[table:Plan]]\n\nafter"),
     dict(O.blank_node("B"), body="  [[table:Nope]]  ")]
check("referenced", O.referenced_tables(o), {"Plan", "Nope"})
h = O.to_html("T", o, [tb])
check("table in html is coloured and in place",
      ("background:#112233" in h, h.index("intro") < h.index("<table") < h.index("after")), (True, True))
check("missing table named", "missing table: Nope" in h, True)
check("no tables given: placeholder stays text", "<table" not in O.to_html("T", o) and "table:Plan" in O.to_html("T", o), True)
m = O.to_markdown("T", o, [tb])
check("markdown table", "| Day |" in m and "(missing table: Nope)" in m, True)
check("placeholder helper", O.table_placeholder("x"), "[[table:x]]")
check("inline mention is not a placeholder", O.referenced_tables([dict(O.blank_node("A"), body="see [[table:Plan]] here")]), set())

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
