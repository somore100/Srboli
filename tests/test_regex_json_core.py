# tests/test_regex_json_core.py - python3 tests/test_regex_json_core.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import regex_json_core as c

r = c.find_matches(r"(\d+)-(?P<w>\w+)", "", "12-ab 7-x nope")
assert r["count"] == 2 and r["matches"][0]["groups"] == ["12", "ab"] and r["matches"][0]["named"] == {"w": "ab"}
assert r["matches"][1]["start"] == 6
assert c.find_matches("A", "", "a")["count"] == 0 and c.find_matches("A", "i", "a")["count"] == 1
assert c.find_matches("^b", "m", "a\nb")["count"] == 1 and c.find_matches("a.b", "s", "a\nb")["count"] == 1
bad = c.find_matches("(", "", "x"); assert "character" in bad["error"] and bad["matches"] == []
assert c.find_matches("", "", "x")["error"] == "" and c.find_matches("", "", "x")["count"] == 0
big = c.find_matches("a", "", "a" * 500); assert big["count"] == 500 and len(big["matches"]) == 200 and big["truncated"]
assert c.replace_all(r"(\w)(\d)", "", r"\2\1", "a1 b2") == ("1a 2b", 2, "")
assert "Bad replacement" in c.replace_all("a", "", r"\9", "a")[2]
assert c.replace_all("(", "", "x", "t")[1:] == (0, c.compile_pattern("(")[1])
h = c.highlight_markup("a[b]c", [{"start": 2, "end": 3}])
assert "[color=ffcc33][b]&bl;b&br;[/b][/color]" in h or "b" in h and "&bl;" in h

v, e = c.parse('{"a": [1, {"b c": null}], "d": "x"}'); assert e == ""
assert c.parse("{")[1].startswith("Expecting") and "line 3" in c.parse("{\n\n")[1]
assert c.parse("  ")[1] == "Nothing to read."
assert c.minify(v) == '{"a":[1,{"b c":null}],"d":"x"}' and '\n  "a"' in c.pretty(v)
assert c.pretty({"b": 1, "a": 2}, sort_keys=True).index('"a"') < c.pretty({"b": 1, "a": 2}, sort_keys=True).index('"b"')
assert c.pretty({"s": "š"}) == '{\n  "s": "š"\n}'
assert [c.kind(x) for x in ({}, [], "s", True, None, 3, 1.5)] == ["object", "array", "string", "bool", "null", "number", "number"]
assert c.preview({"a": 1}) == "{1}" and c.preview([1, 2]) == "[2]" and c.preview("x" * 100).endswith("...")

R = c.rows(v, set())
assert [(r[0], r[1]) for r in R] == [(0, "$"), (1, "a"), (1, "d")]
R = c.rows(v, {("a",)})
assert [r[1] for r in R] == ["$", "a", "[0]", "[1]", "d"] and R[1][5] and R[1][6]
assert not [r for r in R if r[1] == "d"][0][5]                  # a string is not expandable
assert len(c.rows(list(range(5000)), set())) == 600            # capped

assert c.parse_path("a.b[0][\"x y\"]") == ("a", "b", 0, "x y") and c.parse_path("$") == () and c.parse_path("$.a[1]") == ("a", 1)
assert c.parse_path("[2].k") == (2, "k")
for bad in ("a[", "a[x]", "a..b"):
    try: c.parse_path(bad); raise SystemExit(f"no error {bad}")
    except ValueError: pass
assert c.get_path(v, "a[1][\"b c\"]") == (None, "")
assert c.get_path(v, "a[0]") == (1, "") and c.get_path(v, "d") == ("x", "")
assert "Nothing at" in c.get_path(v, "a[9]")[1] and "Nothing at" in c.get_path(v, "zz")[1]
assert c.path_text(("a", 1, "x y")) == 'a[1]["x y"]' and c.path_text(()) == "$"
print("regex json core OK")
