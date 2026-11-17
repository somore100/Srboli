# tests/test_twoway_core.py - no display needed. Real folders, real copies.
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core.twoway_core as tw
import core.sync_core as sc

root = tempfile.mkdtemp()
A, B = os.path.join(root, "A"), os.path.join(root, "B")
os.makedirs(A); os.makedirs(B)
ST = os.path.join(root, "state.json")
clock = [time.time()]

def w(base, rel, data, newer=None):
    p = os.path.join(base, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(data)
    clock[0] += 10                      # every write gets a clearly later time
    t = clock[0] if newer is None else time.time() + newer
    os.utime(p, (t, t))
    return p
def rm(base, rel): os.remove(os.path.join(base, *rel.split("/")))
def tree(base):
    out = {}
    for r, ds, fs in os.walk(base):
        ds[:] = [d for d in ds if d != sc.REPLACED]
        for f in fs:
            out[os.path.relpath(os.path.join(r, f), base).replace(os.sep, "/")] = open(os.path.join(r, f)).read()
    return out
def kept(base):
    return sorted(open(os.path.join(r, f)).read()
                  for r, _, fs in os.walk(os.path.join(base, sc.REPLACED)) for f in fs)
def sync(**kw):
    r = tw.run_sync(A, B, ST, **kw)
    return r
def settled():
    assert tree(A) == tree(B), (tree(A), tree(B))
    assert tw.make_plan(A, B, ST).work == 0

assert tw.check_folders(A, A) and tw.check_folders(A, os.path.join(A, "x")) and tw.check_folders("", B)
assert tw.check_folders(A, B) is None

# --- first sync: combine, nothing deleted, differing files are conflicts
w(A, "only_a.txt", "A"); w(B, "only_b.txt", "B"); w(A, "same.txt", "S"); w(B, "same.txt", "S")
w(A, "both.txt", "from A"); w(B, "both.txt", "from B newer")        # B written later
p = tw.make_plan(A, B, ST)
assert p.first and "First sync" in p.note
assert p.a2b == ["only_a.txt"] and p.b2a == ["only_b.txt"] and p.conflicts == ["both.txt"] and p.adopt == ["same.txt"]
r = sync()
assert r.ok and r.to_b == 1 and r.to_a == 1 and r.conflicts == 1 and not r.failed, vars(r)
t = tree(A)
assert t["both.txt"] == "from B newer"                              # newer wins
losers = [k for k, v in t.items() if "conflict from A" in k]
assert len(losers) == 1 and t[losers[0]] == "from A"                # loser kept, named by its side
settled()

# --- normal changes in both directions
w(A, "new_a.txt", "na"); w(B, "new_b.txt", "nb"); w(A, "only_a.txt", "A edited"); w(B, "only_b.txt", "B edited")
p = tw.make_plan(A, B, ST)
assert sorted(p.a2b) == ["new_a.txt", "only_a.txt"] and sorted(p.b2a) == ["new_b.txt", "only_b.txt"] and not p.conflicts
r = sync(); assert r.ok and r.to_b == 2 and r.to_a == 2
assert tree(B)["only_a.txt"] == "A edited" and tree(A)["only_b.txt"] == "B edited"
assert "A" in kept(B) and "B" in kept(A)                            # old versions kept aside
settled()

# --- deletions travel both ways
rm(A, "new_a.txt"); rm(B, "new_b.txt")
p = tw.make_plan(A, B, ST)
assert p.del_b == ["new_a.txt"] and p.del_a == ["new_b.txt"], vars(p)
r = sync(); assert r.ok and r.deleted_a == 1 and r.deleted_b == 1
assert "new_a.txt" not in tree(B) and "new_b.txt" not in tree(A)
assert "na" in kept(B) and "nb" in kept(A)                          # not really deleted
settled()

# --- a delete never beats an edit
w(A, "keep.txt", "v1"); sync()
rm(B, "keep.txt"); w(A, "keep.txt", "v2 edited")
p = tw.make_plan(A, B, ST); assert p.a2b == ["keep.txt"] and not p.del_a
assert sync().ok and tree(B)["keep.txt"] == "v2 edited"
rm(A, "keep.txt"); w(B, "keep.txt", "v3 edited on B")
assert tw.make_plan(A, B, ST).b2a == ["keep.txt"]
assert sync().ok and tree(A)["keep.txt"] == "v3 edited on B"
settled()

# --- both edited to the same content: no conflict
w(A, "twin.txt", "x"); sync()
w(A, "twin.txt", "same new"); w(B, "twin.txt", "same new")
p = tw.make_plan(A, B, ST); assert not p.conflicts and p.adopt == ["twin.txt"]
assert sync().ok; settled()

# --- both edited differently: conflict, both versions on both sides
w(A, "doc.txt", "base"); sync()
w(A, "doc.txt", "edit A"); w(B, "doc.txt", "edit B (later)")
r = sync(); assert r.ok and r.conflicts == 1
assert tree(A)["doc.txt"] == "edit B (later)"
cp = [k for k in tree(A) if k.startswith("doc (conflict from A")]
assert len(cp) == 1 and tree(A)[cp[0]] == "edit A" and tree(B)[cp[0]] == "edit A"
settled()
# the conflict copy is an ordinary file afterwards, and conflicts inside subfolders keep their folder
w(A, "d/x.txt", "1"); sync(); w(A, "d/x.txt", "2"); w(B, "d/x.txt", "3")
assert sync().ok and any(k.startswith("d/x (conflict") for k in tree(B)); settled()

# --- record lost: nothing is deleted, files are combined
os.remove(ST)
rm(A, "only_a.txt")
p = tw.make_plan(A, B, ST); assert p.first and not p.del_a and not p.del_b
assert "only_a.txt" in p.b2a
assert sync().ok and "only_a.txt" in tree(A); settled()

# --- folders given in the other order use the same record
rm(A, "only_a.txt")
q = tw.make_plan(B, A, ST)
assert q.del_a == ["only_a.txt"] and not q.first, vars(q)             # B is "A" now
r = tw.run_sync(B, A, ST); assert r.ok and "only_a.txt" not in tree(B); settled()

# --- warnings
for i in range(12): w(A, f"many{i}.txt", "m")
assert sync().ok
for i in range(12): rm(A, f"many{i}.txt")
p = tw.make_plan(A, B, ST); assert "would be deleted from B" in p.warning, p.warning
assert sync().ok; settled()
import shutil
for f in list(os.listdir(A)):                                      # A "unplugged": empty
    q = os.path.join(A, f); shutil.rmtree(q) if os.path.isdir(q) else os.remove(q)
p = tw.make_plan(A, B, ST); assert "Folder A looks EMPTY" in p.warning, p.warning
# restore from the empty side: files come back from B instead if we sync again with record intact?
# (user declines the warning here; a fresh record gets A's files back from B)
os.remove(ST)
assert sync().ok and tree(A) == tree(B) and len(tree(A)) > 5

# --- a failed copy leaves the record alone, and the next run finishes it
w(A, "late.txt", "L"); w(B, "late2.txt", "L2")
orig = sc.file_safety.safe_copy
def boom(s, d, overwrite=False):
    if s.endswith("late.txt"): raise PermissionError("denied")
    return orig(s, d, overwrite)
sc.file_safety.safe_copy = boom
r = sync(); sc.file_safety.safe_copy = orig
assert [f[0] for f in r.failed] == ["late.txt"] and "late2.txt" in tree(A) and "late.txt" not in tree(B)
assert sync().ok; settled()

# --- an edit that fails to copy puts the old version back
w(A, "late.txt", "L edited")
sc.file_safety.safe_copy = boom
r = sync(); sc.file_safety.safe_copy = orig
assert r.failed and tree(B)["late.txt"] == "L"
assert sync().ok and tree(B)["late.txt"] == "L edited"; settled()

# --- stop is safe and a re-run carries on
for i in range(6): w(A, f"s{i}.txt", str(i))
n = {"i": 0}
def stopper():
    n["i"] += 1; return n["i"] > 3
r = sync(stop=stopper); assert r.stopped and not r.ok
assert not any(".srboli-part" in f for f in os.listdir(B))
assert sync().ok; settled()

# --- the replaced folders are never synced and can be cleared
assert tw.replaced_total(A, B)[0] > 0
assert not any(sc.REPLACED in k for k in sc.scan(A))
assert tw.purge_both(A, B, 30) == 0
assert tw.purge_both(A, B, 0) > 0 and tw.replaced_total(A, B)[0] == 0
print("two-way core passed")
