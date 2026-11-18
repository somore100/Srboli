# tests/test_disk_usage_core.py - python3 tests/test_disk_usage_core.py
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import disk_usage_core as c

r = tempfile.mkdtemp()
def mk(rel, size):
    p = os.path.join(r, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f: f.write(b"x" * size)
    return p
mk("a.txt", 100); mk("movie.mp4", 5000); mk("pics/p1.jpg", 2000); mk("pics/p2.png", 1000)
mk("pics/raw/deep.jpg", 300); mk("docs/d.pdf", 700); mk("docs/empty/.keep", 0); mk("weird.zzz", 50)
os.makedirs(os.path.join(r, "emptydir"))
if hasattr(os, "symlink"):
    os.symlink(os.path.join(r, "movie.mp4"), os.path.join(r, "link.mp4"))      # must not count
    os.symlink(r, os.path.join(r, "loop"))                                    # no endless loop

seen = []
s = c.scan(r, progress=lambda f, b: seen.append((f, b)))
assert s.total == 100 + 5000 + 2000 + 1000 + 300 + 700 + 50 == 9150, s.total
assert s.files == 8 and s.root.files == 8 and s.errors == 0 and not s.stopped
assert s.folders == 6, s.folders                   # root, pics, raw, docs, empty, emptydir
by = {n.name: n for n in s.root.children}
assert by["pics"].size == 3300 and by["pics"].files == 3 and by["docs"].size == 700
assert by["pics"].children[0].name == "raw" and by["pics"].children[0].size == 300
assert by["emptydir"].size == 0 and by["docs"].files == 2
assert s.root.own == 5150 and seen[-1] == (8, 9150)
assert s.largest[0] == (5000, os.path.join(r, "movie.mp4")) and len(s.largest) == 8
assert [x[0] for x in s.largest] == sorted((x[0] for x in s.largest), reverse=True)
t = {k: v for k, v in s.types.items()}
assert t["Video"] == [5000, 1] and t["Pictures"] == [3300, 3] and t["Documents"] == [800, 2] and t["Other"][0] == 50
rs = c.rows(s.root)
assert [x[3] for x in rs].count("files") == 1
assert rs[0][0] == "[3 files in this folder]" and rs[0][1] == 5150, rs[0]
assert rs[1][0] == "pics" and abs(rs[1][2] - 3300 / 9150) < 1e-9
pr = c.rows(by["pics"])
assert [(x[0], x[1]) for x in pr] == [("[2 files in this folder]", 3000), ("raw", 300)], pr
assert sum(x[1] for x in rs) == s.total
assert c.rows(by["emptydir"]) == []

small = c.scan(r, top=2)
assert [x[0] for x in small.largest] == [5000, 2000]
stop = c.scan(r, cancelled=lambda: True)             # checked every 500 entries
assert stop.stopped == "" and stop.files == 8        # small tree: finished before the first check
big = tempfile.mkdtemp()
for i in range(1100):
    open(os.path.join(big, f"f{i}"), "w").write("y")
cut = c.scan(big, cancelled=lambda: True)
assert cut.stopped == "cancelled" and 0 < cut.files < 1100 and cut.total == cut.files
lim = c.scan(big, max_entries=50); assert lim.stopped == "limit" and lim.files == 50

# a folder we can't read counts as an error, not a crash (skip when running as root)
if hasattr(os, "geteuid") and os.geteuid() != 0:
    locked = os.path.join(r, "locked"); os.mkdir(locked); os.chmod(locked, 0)
    ls = c.scan(r); os.chmod(locked, 0o755)
    assert ls.errors == 1 and any(n.denied for n in ls.root.children)
    assert any("(no access)" in x[0] for x in c.rows(ls.root, 50))
try:
    c.scan(os.path.join(r, "a.txt")); raise SystemExit("file isn't a folder")
except NotADirectoryError:
    pass
assert c.kind_of("X.JPG") == "Pictures" and c.kind_of("noext") == "Other" and c.kind_of("a.tar") == "Archives"
assert c.bar(0.5, 10) == "#####....." and c.bar(0) == "." * 12 and c.bar(2, 4) == "####"
tr = c.type_rows(s); assert tr[0][0] == "Video" and abs(sum(x[3] for x in tr) - 1) < 1e-9
rep = c.report(s)
assert "Total: 8.9 KB in 8 files" in rep and "Biggest folders:" in rep and "movie.mp4" in rep and "Video" in rep
assert s.free is not None and "free of" in rep
# the tree view: children follow an opened folder, indented by depth
fl = c.flatten(s.root, set())
assert [x[1] for x in fl] == ["[3 files in this folder]", "pics", "docs", "emptydir"], fl
exp = {s.root.path, by["pics"].path}
fl = c.flatten(s.root, exp)
names = [(x[0], x[1]) for x in fl]
assert names.index((0, "pics")) < names.index((1, "raw")) < names.index((0, "docs")), names
assert (1, "[2 files in this folder]") in names
assert all(0 <= x[3] <= 1 for x in fl) and all(x[5] in ("folder", "files", "more") for x in fl)
capped = c.flatten(s.root, set(), per_folder=2)
assert capped[-1][5] == "more" and capped[-1][1] == "[2 more smaller entries]" and len(capped) == 3
assert c.big_paths(s.root, 0.2) == {s.root.path, by["pics"].path}        # pics holds 36%
assert c.big_paths(s.root, 0.9) == {s.root.path} and by["pics"].path in c.big_paths(s.root, 0.0, 3)
print("disk usage core: all ok")
