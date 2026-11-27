# tests/test_json_repair.py - tolerant JSON reading for AI-written courses
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.json_repair import loads_tolerant
from core import learn_core as L

FAILS = []
def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + (f" - {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

d, n = loads_tolerant('{"a": 1}')
check("plain json untouched", d == {"a": 1} and n == [])
d, n = loads_tolerant('Here you go:\n```json\n{"a": [1, 2,],}\n```\nEnjoy')
check("fence + trailing commas", d == {"a": [1, 2]}, n)
d, n = loads_tolerant('{“a”: 1}')
check("curly quotes", d == {"a": 1} and "replaced curly quotes" in n, n)
d, n = loads_tolerant('{"a": 1, // note\n "b": "x//y"}')
check("comments removed, strings kept", d == {"a": 1, "b": "x//y"}, d)
d, n = loads_tolerant('Sure! {"a": 1} hope it helps')
check("chatter around json", d == {"a": 1})
try:
    loads_tolerant('{\n "a": 1\n "b": 2\n}')
    check("broken json raises", False)
except ValueError as e:
    check("error names line and shows it", "Line 3" in str(e) and '"b": 2' in str(e), str(e))
for bad in ("", "no json here"):
    try:
        loads_tolerant(bad); check("raises for " + repr(bad), False)
    except ValueError:
        check("raises for " + repr(bad), True)
plan, w = L.parse_plan('```json\n{"title":"T","units":[{"title":"U","lessons":[{"title":"L","items":[{"type":"tf","q":"Q?","answer":true},],}],}],}\n```')
check("course with trailing commas imports", plan["title"] == "T", plan)

print("ALL OK" if not FAILS else f"FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
