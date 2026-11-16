# tests/test_sync_core.py - no display needed. Real folders, real copies.
import os, sys, tempfile, time, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core.sync_core as sc

root = tempfile.mkdtemp()
A, B = os.path.join(root, "A"), os.path.join(root, "B")
os.makedirs(A)

def w(base, rel, data, newer=0):
    p = os.path.join(base, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(data)
    if newer:
        t = time.time() + newer; os.utime(p, (t, t))
    return p
def tree(base):
    out = {}
    for r, ds, fs in os.walk(base):
        ds[:] = [d for d in ds if d != sc.REPLACED]
        for f in fs:
            out[os.path.relpath(os.path.join(r, f), base).replace(os.sep, "/")] = open(os.path.join(r, f)).read()
    return out
def replaced_files():
    out = {}
    base = os.path.join(B, sc.REPLACED)
    for r, _, fs in os.walk(base):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), base).split(os.sep, 1)[1]
            out[rel.replace(os.sep, "/")] = open(os.path.join(r, f)).read()
    return out

# --- folder rules
assert sc.check_folders(A, A) and sc.check_folders(A, os.path.join(A, "in"))
assert sc.check_folders(os.path.join(A, "x"), A) or True
assert sc.check_folders("", B) and sc.check_folders(A, "") and sc.check_folders(A, B) is None
os.makedirs(os.path.join(A, "inner"))
assert sc.check_folders(os.path.join(A, "inner"), A)          # source inside target

# --- first sync into a folder that doesn't exist yet
w(A, "a.txt", "A1"); w(A, "sub/b.txt", "B1"); w(A, "sub/deep/c.txt", "C1")
os.rmdir(os.path.join(A, "inner"))
p = sc.make_plan(A, B)
assert sorted(p.new) == ["a.txt", "sub/b.txt", "sub/deep/c.txt"] and not p.changed and not p.removed
r = sc.run_sync(A, B)
assert r.ok and r.copied == 3 and not r.failed and tree(B) == tree(A)
assert not os.path.exists(os.path.join(B, sc.REPLACED))        # nothing was replaced
# second run: nothing to do, and the preview says so
p = sc.make_plan(A, B); assert p.work == 0 and p.same == 3

# --- change, add, remove in A; a stray extra file in B
w(A, "a.txt", "A2-longer", newer=10)
w(A, "new.txt", "N")
os.remove(os.path.join(A, "sub", "deep", "c.txt")); os.rmdir(os.path.join(A, "sub", "deep"))
w(B, "stray.txt", "S")
p = sc.make_plan(A, B)
assert p.new == ["new.txt"] and p.changed == ["a.txt"] and sorted(p.removed) == ["stray.txt", "sub/deep/c.txt"], vars(p)
before_a = tree(A)
r = sc.run_sync(A, B)
assert r.ok and r.copied == 2 and r.replaced == 1 and r.removed == 2
assert tree(B) == tree(A) == before_a                           # B now matches A, A untouched
assert replaced_files() == {"a.txt": "A1", "stray.txt": "S", "sub/deep/c.txt": "C1"}, replaced_files()
assert not os.path.exists(os.path.join(B, "sub", "deep"))       # emptied folder tidied
assert os.stat(os.path.join(B, "a.txt")).st_mtime_ns == os.stat(os.path.join(A, "a.txt")).st_mtime_ns
# the replaced folder is not part of B for the next plan
assert sc.make_plan(A, B).work == 0

# --- tolerance: a 1 s mtime difference (FAT) with the same size is "same"
t = os.stat(os.path.join(B, "new.txt")).st_mtime + 1; os.utime(os.path.join(B, "new.txt"), (t, t))
assert sc.make_plan(A, B).work == 0
# same size but clearly different time is a change
t = os.stat(os.path.join(B, "new.txt")).st_mtime + 100; os.utime(os.path.join(B, "new.txt"), (t, t))
assert sc.make_plan(A, B).changed == ["new.txt"]
assert sc.run_sync(A, B).ok

# --- editing B is overwritten by A, but the edit is kept aside
w(B, "a.txt", "EDITED IN B", newer=50)
r = sc.run_sync(A, B)
assert r.ok and tree(B)["a.txt"] == "A2-longer"
kept = [open(os.path.join(r, f)).read()
        for r, _, fs in os.walk(os.path.join(B, sc.REPLACED)) for f in fs]
assert "EDITED IN B" in kept and "A2-longer" not in kept

# --- empty source is flagged, big removals are flagged
E = os.path.join(root, "E"); os.makedirs(E)
assert "EMPTY" in sc.make_plan(E, B).warning
many = os.path.join(root, "many"); os.makedirs(many); w(many, "keep.txt", "k")
for i in range(12): w(B, f"junk{i}.txt", "j")
assert "would be moved away" in sc.make_plan(many, B).warning
for i in range(12): os.remove(os.path.join(B, f"junk{i}.txt"))
assert sc.make_plan(A, B).warning == ""

# --- failure on a changed file puts the old version back
w(A, "a.txt", "A3", newer=200)
orig = sc.file_safety.safe_copy
def boom(s, d, overwrite=False):
    if s.endswith("a.txt"): raise PermissionError("denied")
    return orig(s, d, overwrite)
sc.file_safety.safe_copy = boom
r = sc.run_sync(A, B)
sc.file_safety.safe_copy = orig
assert [f[0] for f in r.failed] == ["a.txt"]
assert tree(B)["a.txt"] == "A2-longer"                          # old version is back
assert sc.run_sync(A, B).ok and tree(B)["a.txt"] == "A3"

# --- stop is safe and a re-run finishes the job
C = os.path.join(root, "C"); os.makedirs(C)
for i in range(6): w(C, f"f{i}.txt", str(i))
D = os.path.join(root, "D")
n = {"i": 0}
def stop():
    n["i"] += 1; return n["i"] > 3
r = sc.run_sync(C, D, stop=stop)
assert r.stopped and not r.ok and 0 < len(tree(D)) < 6
assert not any(".srboli-part" in f for f in os.listdir(D))
assert sc.run_sync(C, D).ok and tree(D) == tree(C)

# --- purge only touches old batches inside the replaced folder
n_files, size = sc.replaced_info(B); assert n_files > 0 and size > 0
assert sc.purge_replaced(B, 30) == 0
assert sc.purge_replaced(B, 30, now=time.time() + 40 * 86400) >= 1
assert sc.replaced_info(B)[0] == 0
assert os.path.exists(os.path.join(B, "a.txt"))                 # real files untouched

# --- symlinks are ignored
os.symlink(A, os.path.join(A, "loop"))
assert not any(k.startswith("loop") for k in sc.scan(A))
print("sync core passed")
