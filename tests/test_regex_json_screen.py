# tests/test_regex_json_screen.py - xvfb-run -a python3 tests/test_regex_json_screen.py  (kivy screens.)
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.clock import Clock
from screens.regex_json_screen import RegexJsonScreen

def settle(n=40):
    for _ in range(n):
        Clock.tick(); time.sleep(0.02)

sc = RegexJsonScreen()
sc.pattern.text = r"(\d+)-(\w+)"
sc.text_in.text = "12-ab and 7-x"
sc.repl_in.text = r"\2:\1"
settle(30)
assert sc.summary.text.startswith("2 matches"), sc.summary.text
assert "12-ab" in sc.out.text and "ab:12" in sc._replaced and "[color=ffcc33]" in sc.out.text
sc.pattern.text = "("; settle(30)
assert "character" in sc.summary.text
sc.toggle_flag("i"); assert "i" in sc.flags
sc.set_tab("json")
sc.json_in.text = '{"users": [{"name": "Ana"}, {"name": "Bo"}], "n": 2}'
assert "Valid JSON" in sc.json_status.text and len(sc.tree.children) == 3
sc.pick_row(("users",), True); assert len(sc.tree.children) == 5 and sc.path_in.text == "users"
sc.path_in.text = "users[1].name"; sc.lookup(); assert "Bo" in sc.path_out.text
sc.path_in.text = "users[9]"; sc.lookup(); assert "Nothing at" in sc.path_out.text
sc.rewrite("minify"); assert sc.json_in.text == '{"users":[{"name":"Ana"},{"name":"Bo"}],"n":2}'
sc.toggle_sort(); sc.rewrite("pretty"); assert sc.json_in.text.index('"n"') < sc.json_in.text.index('"users"')
sc.json_in.text = "{oops"; assert "line 1" in sc.json_status.text and len(sc.tree.children) == 0
print("regex json screen OK")
