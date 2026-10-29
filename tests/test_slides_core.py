# tests/test_slides_core.py - no display needed (python3 tests/test_slides_core.py)
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import outline_core as O, slides_core as S, table_core as T

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

def node(title, depth=0, body="", **slide):
    n = dict(O.blank_node(title, depth), body=body)
    if slide:
        n["slide"] = slide
    return n

o = [node("Intro", 0, "hello"), node("Goals", 1, "- a\n- b"), node("More", 1, "text"),
     node("Plan", 0, "![pic](/x/p.png)\nafter")]

# separate mode: one slide per section, plus the title slide
s = S.build_slides("Doc", o, [])
check("separate titles", [x["title"] for x in s], ["Doc", "Intro", "Goals", "More", "Plan"])
check("separate nodes", [x["node"] for x in s], [None, 0, 1, 2, 3])
check("defaults", (s[1]["bg"], s[1]["fg"], s[1]["skip"]), (S.DEFAULT_BG, S.DEFAULT_FG, False))
check("no title slide", [x["title"] for x in S.build_slides("Doc", o, [], title_slide=False)][0], "Intro")

# bullets mode: top-level sections only, children become bullets
s = S.build_slides("Doc", o, [], mode="bullets")
check("bullets titles", [x["title"] for x in s], ["Doc", "Intro", "Plan"])
check("bullets body", s[1]["body"], "hello\n\n- Goals\n  - a\n  - b\n- More\n  text")
o2 = [node("A", 0), node("B", 1), node("C", 2, "deep"), node("D", 1)]
check("bullets nest by depth", S.build_slides("T", o2, [], "bullets", False)[0]["body"],
      "- B\n  - C\n    deep\n- D")
check("bullets skip a child", S.build_slides("T", [node("A"), node("B", 1, slide=None), dict(node("C", 1), slide={"skip": True})],
                                              [], "bullets", False)[0]["body"], "- B")

# overrides
o3 = [node("A", 0, "x", bg="#f00", fg="zz", image="/i.png", skip=True, junk=1)]
s = S.build_slides("T", o3, [], title_slide=False)[0]
check("override applied/cleaned", (s["bg"], s["fg"], s["image"], s["skip"]), ("#FF0000", S.DEFAULT_FG, "/i.png", True))
check("visible drops skipped", [x["title"] for x in S.visible(S.build_slides("T", o3, []))], ["T"])
check("title style", S.build_slides("T", o3, [], title_style={"bg": "#00ff00"})[0]["bg"], "#00FF00")
check("clean_style junk", S.clean_style("x"), {})

# body extraction: tables and the first image
tb = T.blank_table("Plan", 1, 1)
o4 = [node("A", 0, "intro\n\n[[table:Plan]]\n\n![one](/a.png)\n![two](/b.png)\n[[table:Nope]]")]
s = S.build_slides("T", o4, [tb], title_slide=False)[0]
check("tables collected, missing ignored", [t["name"] for t in s["tables"]], ["Plan"])
check("first image taken", s["image"], "/a.png")
check("rest of body kept", ("[[table" in s["body"], "![two](/b.png)" in s["body"], "![one]" in s["body"]), (False, True, False))
check("override image wins", S.build_slides("T", [node("A", 0, "![x](/a.png)", image="/o.png")], [], title_slide=False)[0]["image"], "/o.png")

# markup
m = S.body_markup("# Big\n\nsome **bold** and [color=#ff0000]red[/color]\n\n- one\n  - two\n- [x] done\n\n1. a\n2. b\n\n> quoted\n\n```\ncode [x]\n```\n\n| h1 | h2 |\n|---|---|\n| 1 | 2 |", 20)
check("heading", "[size=32][b]Big[/b][/size]" in m, True)
check("inline", ("[b]bold[/b]" in m, "[color=ff0000]red[/color]" in m), (True, True))
check("bullets", ("• one" in m, "    • two" in m, "&bl;x&br; done" in m), (True, True, True))
check("ordered", ("1. a" in m and "2. b" in m), True)
check("quote/code", ("[i]quoted[/i]" in m, "code &bl;x&br;" in m), (True, True))
check("table rows", ("[b]h1 | h2[/b]" in m, "1 | 2" in m), (True, True))
# markup tags balance (Kivy breaks on a stray closer)
for tag in ("b", "i", "size", "font", "color"):
    check(f"balanced [{tag}]", (len(re.findall(rf"\[{tag}[=\]]", m)), m.count(f"[/{tag}]")),
          (m.count(f"[/{tag}]"), m.count(f"[/{tag}]")))
check("empty body", S.body_markup(""), "")

# importing old hand-written slides
check("blank old slides -> nothing", S.import_slides([{"title": "Slide 1", "body": "", "color": "#FFFFFF", "bg": "#1A1A2E", "image": None}]), [])
check("junk -> nothing", (S.import_slides(None), S.import_slides(["x"])), ([], []))
imp = S.import_slides([{"title": "Slide 1", "body": "", "bg": "#1A1A2E"},
                       {"title": "Hello", "body": "text", "bg": "#112233", "color": "#FFFFFF", "image": "/p.png"},
                       {"title": "Slide 3", "body": "kept?"}])
check("imported shape", [(n["title"], n["depth"]) for n in imp], [("Slides (imported)", 0), ("Hello", 1), ("Slide 3", 1)])
check("imported style: defaults dropped", imp[1]["slide"], {"bg": "#112233", "image": "/p.png"})
check("imported plain slide has no style", "slide" not in imp[2], True)
check("imported outline is valid", O.normalize(imp) == imp or [n["depth"] for n in O.normalize(imp)] == [0, 1, 1], True)

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
