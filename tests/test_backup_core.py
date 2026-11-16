# tests/test_backup_core.py - no display needed. Real folders, real copies.
import os, sys, tempfile, time, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core.backup_core as bc

root = tempfile.mkdtemp()
src, dst, out = (os.path.join(root, n) for n in ("src", "dst", "out"))
os.makedirs(os.path.join(src, "sub")); os.makedirs(dst)

def write(rel, data):
    p = os.path.join(src, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(data)
    return p
def bump(p, s=5):                       # a clearly newer modified time
    t = time.time() + s; os.utime(p, (t, t))
def tree(folder):
    d = {}
    for r, _, fs in os.walk(folder):
        for f in fs:
            d[os.path.relpath(os.path.join(r, f), folder).replace(os.sep, "/")] = open(os.path.join(r, f)).read()
    return d
def set_dir(): return bc.set_dir_for(dst, src)

a = write("a.txt", "A1"); write("b.txt", "B1"); write("sub/c.txt", "C1")

# --- folder rules
assert bc.check_folders(src, os.path.join(src, "inner"))          # inside the source
assert bc.check_folders(src, src)
assert bc.check_folders(src, dst) is None
assert bc.check_folders("", dst) and bc.check_folders(src, "")

# --- full
p = bc.make_plan(src, dst, "full")
assert p.kind == "full" and len(p.to_copy) == 3 and p.note == ""
r = bc.run_backup(src, dst, "full", verify=True)
assert r.ok and r.kind == "full" and r.copied == 3 and not r.failed, vars(r)
full = r.name
assert full.endswith("_full")
# incremental/differential with nothing earlier become full, and say so
assert bc.make_plan(src, dst, "incr").kind == "incr"              # a full exists now
shutil.rmtree(os.path.join(dst, os.listdir(dst)[0]))              # forget everything
assert bc.make_plan(src, dst, "incr").kind == "full" and bc.make_plan(src, dst, "incr").note
assert bc.make_plan(src, dst, "diff").kind == "full"
r = bc.run_backup(src, dst, "full"); full = r.name; assert r.ok

# nothing changed -> an incremental copies nothing
r = bc.run_backup(src, dst, "incr"); assert r.ok and r.copied == 0 and r.kind == "incr"
time.sleep(1.1)

# --- change a file, add a file, remove one
open(a, "w").write("A2"); bump(a)
write("d.txt", "D1")
os.remove(os.path.join(src, "b.txt"))
p = bc.make_plan(src, dst, "incr")
assert sorted(p.to_copy) == ["a.txt", "d.txt"] and p.removed == 1 and p.unchanged == 1, vars(p)
r = bc.run_backup(src, dst, "incr"); assert r.ok and r.copied == 2
incr1 = r.name
time.sleep(1.1)
# differential compares with the FULL: same changes again, plus nothing new
p = bc.make_plan(src, dst, "diff")
assert sorted(p.to_copy) == ["a.txt", "d.txt"] and p.base == full
r = bc.run_backup(src, dst, "diff"); assert r.ok and r.copied == 2; diff1 = r.name
time.sleep(1.1)
# more change: incremental now only has the new one, differential has all three
write("sub/e.txt", "E1")
assert bc.make_plan(src, dst, "incr").to_copy == ["sub/e.txt"]       # vs latest (diff1)
assert sorted(bc.make_plan(src, dst, "diff").to_copy) == ["a.txt", "d.txt", "sub/e.txt"]
r = bc.run_backup(src, dst, "incr"); assert r.ok and r.copied == 1; incr2 = r.name

bk = bc.list_backups(set_dir())
assert [b["kind"] for b in bk] == ["full", "incr", "incr", "diff", "incr"], [b["kind"] for b in bk]
assert bk[-1]["files"] == 4 and bk[0]["files"] == 3

# --- restore every point and compare with what the source looked like then
out1 = os.path.join(out, "full"); rr = bc.run_restore(set_dir(), full, out1)
assert rr.ok and tree(out1) == {"a.txt": "A1", "b.txt": "B1", "sub/c.txt": "C1"}, tree(out1)
out2 = os.path.join(out, "incr1"); assert bc.run_restore(set_dir(), incr1, out2).ok
assert tree(out2) == {"a.txt": "A2", "sub/c.txt": "C1", "d.txt": "D1"}, tree(out2)
out3 = os.path.join(out, "diff1"); assert bc.run_restore(set_dir(), diff1, out3).ok
assert tree(out3) == tree(out2)
out4 = os.path.join(out, "incr2"); assert bc.run_restore(set_dir(), incr2, out4).ok
assert tree(out4) == tree(src), (tree(out4), tree(src))
assert os.stat(os.path.join(out4, "a.txt")).st_mtime_ns == os.stat(a).st_mtime_ns   # times kept

# restore never overwrites
open(os.path.join(out4, "a.txt"), "w").write("MINE")
rr = bc.run_restore(set_dir(), incr2, out4)
assert rr.ok and "a.txt" in rr.skipped and rr.restored == 0 and open(os.path.join(out4, "a.txt")).read() == "MINE"
assert bc.run_restore(set_dir(), incr2, os.path.join(set_dir(), "x")).error     # into the backups
assert bc.run_restore(set_dir(), "nope", out4).error

# --- deleting: refused while later backups need it
assert bc.dependents(set_dir(), full)
ok, msg = bc.delete_backup(set_dir(), full); assert not ok and os.path.isdir(os.path.join(set_dir(), full))
assert bc.delete_backup(set_dir(), "../x")[0] is False
ok, _ = bc.delete_backup(set_dir(), incr2); assert ok
assert [b["name"] for b in bc.list_backups(set_dir())][-1] == diff1

# --- stop leaves nothing behind and no backup
before = bc.list_backups(set_dir())
write("sub/f.txt", "F"); write("sub/g.txt", "G")
n = {"i": 0}
def stop():
    n["i"] += 1; return n["i"] > 1
r = bc.run_backup(src, dst, "incr", stop=stop)
assert r.stopped and not r.ok
assert bc.list_backups(set_dir()) == before
assert sorted(os.listdir(set_dir())) == sorted([b["name"] for b in before] + ["set.json"])

# --- a file that can't be read is reported and retried next time
bad = write("sub/locked.txt", "L")
orig = bc.file_safety.safe_copy
def flaky(s, d, overwrite=False):
    if s.endswith("locked.txt"): raise PermissionError("denied")
    return orig(s, d, overwrite)
bc.file_safety.safe_copy = flaky
r = bc.run_backup(src, dst, "incr")
assert r.ok and [f[0] for f in r.failed] == ["sub/locked.txt"], r.failed
bc.file_safety.safe_copy = orig
assert "sub/locked.txt" in bc.make_plan(src, dst, "incr").to_copy
assert bc.run_backup(src, dst, "incr").ok

# --- crash leftovers are ignored and can be cleaned
os.makedirs(os.path.join(set_dir(), "2099-01-01_000000_full"))
assert all(b["name"] != "2099-01-01_000000_full" for b in bc.list_backups(set_dir()))
assert bc.cleanup_unfinished(set_dir()) == 1

# --- the backup folder is never scanned as part of the source when it is inside
inner = os.path.join(src, "mybackups")
assert bc.check_folders(src, inner)                  # refused outright

# --- two sources with the same name get separate sets
other = os.path.join(root, "x", "src"); os.makedirs(other); open(os.path.join(other, "z"), "w").write("z")
assert bc.set_dir_for(dst, other, create=True) != set_dir()
assert bc.run_backup(other, dst, "full").ok

# --- symlinks are not followed
os.symlink(src, os.path.join(src, "loop"))
assert not any(k.startswith("loop") for k in bc.scan(src))
print("backup core passed")
