# tests/test_cleanup_core.py - python3 tests/test_cleanup_core.py
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import cleanup_core as c

assert c.human(500) == "500 B" and c.human(1536) == "1.5 KB"
now = time.time()

def touch(path, size, age_h):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(b"x" * size)
    t = now - age_h * 3600
    os.utime(path, (t, t))

with tempfile.TemporaryDirectory() as d:
    root = os.path.join(d, "cache")
    touch(os.path.join(root, "a/old.bin"), 1000, 48)
    touch(os.path.join(root, "a/b/old2.bin"), 500, 30)
    touch(os.path.join(root, "new.bin"), 700, 1)                      # too recent
    touch(os.path.join(root, "keep/ex.bin"), 300, 99)                 # excluded folder
    touch(os.path.join(d, "outside/secret.txt"), 50, 99)
    os.symlink(os.path.join(d, "outside"), os.path.join(root, "link"))   # symlinked dir
    os.symlink(os.path.join(d, "outside/secret.txt"), os.path.join(root, "flink"))
    cat = c.Category("cache", "Cache", root, "n", 24, exclude=[os.path.join(root, "keep")])
    r = c.scan_category(cat, now)
    names = sorted(os.path.basename(p) for p, _ in r["files"])
    assert names == ["old.bin", "old2.bin"] and r["total"] == 1500, names

    pat = c.Category("p", "P", root, "", 0, pattern="new*")
    assert [os.path.basename(p) for p, _ in c.scan_category(pat, now)["files"]] == ["new.bin"]
    assert c.scan_category(c.Category("x", "X", os.path.join(d, "missing"), "", 0), now)["files"] == []
    assert c.scan_category(c.Category("l", "L", os.path.join(root, "link"), "", 0), now)["files"] == []

    # a file touched after the scan is skipped; a path moved outside the root is skipped
    touch(os.path.join(root, "a/old.bin"), 1000, 0)
    tampered = dict(r); tampered["files"] = r["files"] + [(os.path.join(d, "outside/secret.txt"), 50)]
    out = c.clean([tampered], now)
    assert out["deleted"] == 1 and out["freed"] == 500 and out["skipped"] == 2, out
    assert os.path.exists(os.path.join(d, "outside/secret.txt"))              # never touched
    assert os.path.exists(os.path.join(root, "a/old.bin")) and os.path.exists(os.path.join(root, "new.bin"))
    assert os.path.exists(os.path.join(root, "keep/ex.bin"))
    assert not os.path.exists(os.path.join(root, "a/b"))                      # emptied folder removed
    assert os.path.isdir(root) and os.path.islink(os.path.join(root, "link")) # root and links stay
    # progress and cancel
    seen = []
    c.scan([cat, pat], now, progress=lambda i, n, l: seen.append(l))
    assert seen == ["Cache", "P"] and c.scan([cat], now, cancel=lambda: True) == []

cats = c.categories("Linux", "/home/u", {}, ["/data/cache"])
assert [x.key for x in cats][:4] == ["thumbs", "cache", "tmp", "trash"] and cats[-1].key == "srboli0"
assert not [x for x in cats if x.key == "trash"][0].default_on
assert all(x.root != "/home/u" and "Documents" not in x.root and "Downloads" not in x.root for x in cats)
w = c.categories("Windows", "C:/Users/u", {"LOCALAPPDATA": "C:/L", "TEMP": "C:/T"})
assert [x.key for x in w] == ["temp", "thumbs", "crash"] and w[0].root == "C:/T" and w[1].pattern == "thumbcache_*.db"
assert [x.key for x in c.categories("Darwin", "/Users/u", {})] == ["cache", "logs", "trash"]
assert c.categories("Android", "/x", {}) == []

# memory: fake psutil
class P:
    def __init__(self, pid, name, rss, user="me"): self.pid=pid; self._n=name; self.info={"pid":pid,"name":name,"memory_info":type("M",(),{"rss":rss})(),"username":user}; self.terminated=False
    def name(self): return self._n
    def username(self): return self.info["username"]
    def terminate(self): self.terminated = True
class Fake:
    procs = [P(1, "firefox", 900), P(2, "gnome-shell", 800), P(3, "other", 700, "root"), P(os.getpid(), "srboli", 600), P(5, "code", 500)]
    def Process(self, pid=None):
        if pid is None: return P(0, "me-proc", 0)
        return next(p for p in self.procs if p.pid == pid)
    def process_iter(self, attrs): return iter(self.procs)
ps = Fake()
top = c.top_processes(ps, 10)
assert [t["name"] for t in top] == ["firefox", "gnome-shell", "srboli", "code"]          # root's hidden
assert [t["protected"] for t in top] == [False, True, True, False]
assert c.close_process(ps, 1)[0] and Fake.procs[0].terminated
assert not c.close_process(ps, 2)[0] and not Fake.procs[1].terminated
assert not c.close_process(ps, os.getpid())[0] and not c.close_process(ps, 3)[0]
assert not c.close_process(ps, 999)[0]
assert c.free_own_memory() >= 0
print("cleanup core OK")
