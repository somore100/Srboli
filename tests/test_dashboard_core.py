# tests/test_dashboard_core.py - no display needed (python3 tests/test_dashboard_core.py)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import dashboard_core as D
from screens.registry import SCREENS, LABELS, GROUPS, default_route_order

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

# the real registry: every tool is in exactly one section
grouped = [r for _k, _t, rs in GROUPS for r in rs]
check("every screen is in exactly one section", sorted(grouped), sorted(default_route_order()))
check("no duplicates", len(grouped), len(set(grouped)))
check("section keys unique", len({k for k, _t, _r in GROUPS}), len(GROUPS))
check("every screen has a label", [r for r in default_route_order() if r not in LABELS], [])

menu = [(r, LABELS[r]) for r in default_route_order()]
sec = D.group_menu(menu, GROUPS)
check("sections in registry order", [k for k, _t, _m in sec], [k for k, _t, _r in GROUPS])
check("all tools shown once", sorted(r for _k, _t, m in sec for r, _l in m), sorted(default_route_order()))

# hidden tools drop out; empty sections vanish
small = [("chess", "Chess"), ("minesweeper", "Minesweeper")]
check("only the fun section is left", [k for k, _t, _m in D.group_menu(small, GROUPS)], ["fun"])
check("nothing -> nothing", D.group_menu([], GROUPS), [])

# the USER's order wins inside a section
rev = list(reversed(menu))
fun = [m for k, _t, m in D.group_menu(rev, GROUPS) if k == "fun"][0]
check("user order kept inside a section", [r for r, _l in fun], [r for r, _l in rev if r in dict(fun)])

# a tool no section lists is not lost
extra = menu + [("brand_new", "Brand New")]
check("unlisted tool goes to Other", D.group_menu(extra, GROUPS)[-1], ("other", "Other", [("brand_new", "Brand New")]))

# search
check("empty query", D.search(menu, "  "), [])
check("substring, any case", [r for r, _l in D.search(menu, "EDIT")], ["text_editor", "full_editor"])
check("all words must match", [r for r, _l in D.search(menu, "file conv")], ["converter"])
check("matches the route name too", "fast_transfer" in [r for r, _l in D.search(menu, "fast transfer")], True)
check("starts-with first", D.search([("a", "Zoo Text"), ("b", "Text Zoo")], "text")[0][0], "b")
check("no match", D.search(menu, "qqqq"), [])

# recents
r = D.push_recent([], "chess")
r = D.push_recent(r, "music"); r = D.push_recent(r, "chess")
check("recent: newest first, no duplicates", r, ["chess", "music"])
many = []
for i in range(12): many = D.push_recent(many, f"r{i}")
check("recent: capped", (len(many), many[0]), (D.RECENT_KEPT, "r11"))
mm = [("chess", "Chess"), ("music", "Music Player")]
check("visible recent skips hidden/unknown tools", D.visible_recent(["gone", "music", "hidden", "chess"], mm), [("music", "Music Player"), ("chess", "Chess")])
check("visible recent limited", len(D.visible_recent(many, [(f"r{i}", "x") for i in range(12)])), D.RECENT_SHOWN)

# collapsing
c = D.toggle_collapsed([], "files"); check("collapse", c, ["files"])
check("expand again", D.toggle_collapsed(c, "files"), [])
check("toggle doesn't mutate", D.toggle_collapsed(c, "fun") is not c and c == ["files"], True)

# saved state is cleaned
check("clean_state", D.clean_state(["chess", "gone", "chess", 5], ["fun", "nope", 3], ["chess"], ["fun"]), (["chess"], ["fun"]))
check("clean_state junk", D.clean_state("x", None, [], []), ([], []))

# ── search aliases, pins, tiles ──
def _t3():
    menu = [("image_text", "File to Base64"), ("music", "Music Player")]
    assert D.search(menu, "base64") == [("image_text", "File to Base64")]
    assert D.search(menu, "mp3", {"music": ["mp3"]}) == [("music", "Music Player")]
    assert D.search(menu, "mp3") == []
    assert D.toggle_pin([], "a") == ["a"] and D.toggle_pin(["a", "b"], "a") == ["b"]
    assert D.clean_routes(["a", "zz", "a", 3, "b"], ["a", "b"]) == ["a", "b"]
    assert D.tile_columns(300) == 1 and D.tile_columns(900) == 4
    assert D.tile_columns(900, 2.0) == 2
    assert D.recent_shown(360) == 3 and D.recent_shown(900) == 4
    print("aliases / pins / tiles passed")
_t3()

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
