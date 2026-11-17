# tests/test_bulk_rename_core.py - python3 tests/test_bulk_rename_core.py
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import bulk_rename_core as b

R = lambda op, a="", bb="": {"op": op, "a": a, "b": bb}
ap = lambda rules, name, i=0, m=0: b.apply_rules(rules, name, i, m, "Dir")
assert ap([R("replace", "x", "y")], "axb.txt") == "ayb.txt"
assert ap([R("regex", r"(\d+)", r"<\1>")], "a12.txt") == "a<12>.txt"
assert ap([R("upper")], "ab.txt") == "AB.txt" and ap([R("lower")], "AB.TXT") == "ab.TXT"
assert ap([R("title")], "hi there.txt") == "Hi There.txt"
assert ap([R("prefix", "p_"), R("suffix", "_s")], "a.txt") == "p_a_s.txt"
assert ap([R("cut_start", "2")], "abcd.txt") == "cd.txt" and ap([R("cut_end", "1")], "abcd.txt") == "abc.txt"
assert ap([R("cut_end", "0")], "abcd.txt") == "abcd.txt"
assert ap([R("spaces")], "a b c.txt") == "a_b_c.txt" and ap([R("spaces", "-")], "a b.txt") == "a-b.txt"
assert ap([R("clean")], "a#b$c!.txt") == "abc.txt"
assert ap([R("trim")], " a. .txt") == "a.txt"
assert ap([R("number", "1", "3")], "a.txt", 4) == "a_005.txt"
assert ap([R("number_front", "10")], "a.txt", 1) == "11_a.txt"
d = time.mktime((2026, 11, 17, 12, 0, 0, 0, 0, -1))
assert ap([R("date")], "a.txt", 0, d) == "2026-11-17_a.txt"
assert ap([R("date_end", "%d.%m.%Y")], "a.txt", 0, d) == "a_17.11.2026.txt"
assert ap([R("template", "{parent}_{n}_{name}")], "a.txt", 2) == "Dir_3_a.txt"
assert ap([R("ext_lower")], "A.JPG") == "A.jpg" and ap([R("ext_set", ".png")], "a.jpg") == "a.png"
assert ap([R("ext_set", "md")], "noext") == "noext.md"
assert ap([R("upper")], ".bashrc") == ".BASHRC"
assert ap([R("replace", "a", "b"), R("upper")], "aa.txt") == "BB.txt"      # chain order

for bad in ([R("replace")], [R("regex", "(")], [R("regex", "a", r"\9")], [R("cut_start", "x")],
            [R("number", "-1")], [R("template")], [R("ext_set", ".")], [{"op": "zzz"}]):
    try:
        b.check_rules(bad); raise SystemExit(f"should fail {bad}")
    except b.RenameError:
        pass

assert b.problem_with("ok.txt") == "" and b.problem_with("a/b") and b.problem_with("")
assert b.problem_with("a.") and b.problem_with("CON.txt") and b.problem_with("x" * 300)

tmp = tempfile.mkdtemp(); undo = os.path.join(tmp, "undo.json")
w = os.path.join(tmp, "w"); os.mkdir(w); os.mkdir(os.path.join(w, "sub"))
def mk(n, text=None):
    open(os.path.join(w, n), "w").write(text or n)
for n in ("img2.jpg", "img10.jpg", "img1.jpg", "note.txt"):
    mk(n)
names = lambda: sorted(os.listdir(w))
assert [x[0] for x in b.list_files(w)] == ["img1.jpg", "img2.jpg", "img10.jpg", "note.txt"]
assert [x[0] for x in b.list_files(w, "*.JPG")] == ["img1.jpg", "img2.jpg", "img10.jpg"]
assert [x[0] for x in b.list_files(w, "*.txt, *.png")] == ["note.txt"]
assert [x[0] for x in b.list_files(w, "", "name", True)][0] == "note.txt"

plan = b.build_plan(w, [R("template", "pic_{n}")], "*.jpg")
assert [p["new"] for p in plan] == ["pic_1.jpg", "pic_2.jpg", "pic_3.jpg"], plan
assert all(p["status"] == "ok" for p in plan) and names()[0] == "img1.jpg"   # preview touched nothing
assert b.apply_plan(plan, undo) == 3
assert names() == ["note.txt", "pic_1.jpg", "pic_2.jpg", "pic_3.jpg", "sub"]
assert open(os.path.join(w, "pic_1.jpg")).read() == "img1.jpg"
assert b.undo_info(undo)[0] == 3
assert b.undo_last(undo) == 3 and names() == ["img1.jpg", "img10.jpg", "img2.jpg", "note.txt", "sub"]
assert b.undo_info(undo) is None
try:
    b.undo_last(undo); raise SystemExit("nothing to undo")
except b.RenameError:
    pass

# duplicates inside the plan, and a clash with a file outside it
plan = b.build_plan(w, [R("template", "same")], "*.jpg")
assert {p["status"] for p in plan} == {"conflict"}
try:
    b.apply_plan(plan, undo); raise SystemExit("conflict applied")
except b.RenameError:
    pass
plan = b.build_plan(w, [R("template", "note"), R("ext_set", "txt")], "img1.jpg")
assert [p["status"] for p in plan] == ["conflict"], plan          # note.txt already exists
plan = b.build_plan(w, [R("template", "bad:name")], "img1.jpg")
assert plan[0]["status"] == "invalid"
plan = b.build_plan(w, [R("upper")], "*.jpg")
assert all(p["new"].startswith("IMG") for p in plan)

# swap / chain: a -> b and b -> c while c exists and is also renamed
v = os.path.join(tmp, "v"); os.mkdir(v)
for n in "abc":
    open(os.path.join(v, n + ".txt"), "w").write(n)
plan = b.build_plan(v, [R("replace", "a", "TMP"), R("replace", "b", "a"), R("replace", "TMP", "b")], "a.txt b.txt")
assert [(p["old"], p["new"], p["status"]) for p in plan] == [("a.txt", "b.txt", "ok"), ("b.txt", "a.txt", "ok")], plan
b.apply_plan(plan, undo)
assert open(os.path.join(v, "a.txt")).read() == "b" and open(os.path.join(v, "b.txt")).read() == "a"
assert b.undo_last(undo) == 2 and open(os.path.join(v, "a.txt")).read() == "a"

# case-only rename works
u = os.path.join(tmp, "u"); os.mkdir(u); open(os.path.join(u, "hello.txt"), "w").write("x")
plan = b.build_plan(u, [R("upper")]); assert plan[0]["new"] == "HELLO.txt" and plan[0]["status"] == "ok"
b.apply_plan(plan, undo); assert os.listdir(u) == ["HELLO.txt"]
b.undo_last(undo)

# a failure half way puts everything back
import unittest.mock as mock
plan = b.build_plan(v, [R("prefix", "z_")])
real = os.rename; calls = {"n": 0}
def flaky(s, d):
    calls["n"] += 1
    if calls["n"] == 5:
        raise OSError(13, "Permission denied")
    return real(s, d)
with mock.patch("os.rename", flaky):
    try:
        b.apply_plan(plan, undo); raise SystemExit("should fail")
    except b.RenameError as e:
        assert "put back" in str(e)
assert sorted(os.listdir(v)) == ["a.txt", "b.txt", "c.txt"], os.listdir(v)
assert b.undo_info(undo) is None

# undo refuses when things changed since
plan = b.build_plan(v, [R("prefix", "z_")]); b.apply_plan(plan, undo)
os.remove(os.path.join(v, "z_a.txt"))
try:
    b.undo_last(undo); raise SystemExit("undo should refuse")
except b.RenameError:
    pass
assert os.path.exists(os.path.join(v, "z_b.txt"))
print("bulk rename core: all ok")
