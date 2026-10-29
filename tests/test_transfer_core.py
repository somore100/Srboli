# tests/test_transfer_core.py - no display needed (python3 tests/test_transfer_core.py)
import os, sys, time, shutil, tempfile, subprocess, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import transfer_core as T
from core import file_safety

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

root = tempfile.mkdtemp()
def tree(name, n=30, size=2000, age=3600, nested=True):
    base = os.path.join(root, name); os.makedirs(base)
    for i in range(n):
        folder = os.path.join(base, f"d{i % 4}") if nested else base
        os.makedirs(folder, exist_ok=True)
        p = os.path.join(folder, f"f{i}.bin")
        open(p, "wb").write(os.urandom(size))
        if age:
            t = time.time() - age; os.utime(p, (t, t))
    return base
def listing(base):
    return sorted(os.path.relpath(os.path.join(r, f), base) for r, _d, fs in os.walk(base) for f in fs)

# ── worker limits ──
check("clamp: junk and low", (T.clamp_workers("x")[0], T.clamp_workers(0)[0], T.clamp_workers(-3)[0]), (1, 1, 1))
check("clamp: fine", T.clamp_workers(8), (8, None))
n, w = T.clamp_workers(32); check("clamp: warns above 16", (n, w is not None), (32, True))
n, w = T.clamp_workers(200); check("clamp: capped at 64", (n, "64" in w), (64, True))

# ── collecting ──
src = tree("src")
open(os.path.join(src, "d0", "x.bin.srboli-part"), "wb").write(b"half")
pairs = T.collect_files_with_relpaths(src)
check("collect: all files, no temp leftovers", (len(pairs), any("srboli-part" in a for a, _ in pairs)), (30, False))
check("collect: non-recursive is flat", T.collect_files_with_relpaths(src, recursive=False), [])
check("rel paths rebuild the structure", sorted(r for _a, r in pairs)[0], os.path.join("d0", "f0.bin"))

# ── copy: identical, nested, no temp files, and FAST for old files ──
dst = os.path.join(root, "dst")
t0 = time.perf_counter()
res = T.run_transfer(pairs, dst, "copy", 4)
took = time.perf_counter() - t0
check("copy: all done", sorted(r[0] for r in res), ["done"] * 30)
check("copy: same folder structure", listing(dst), [f for f in listing(src) if "srboli-part" not in f])
check("copy: contents identical", all(open(a, "rb").read() == open(os.path.join(dst, r), "rb").read() for a, r in pairs), True)
check("copy: sources untouched", all(os.path.exists(a) for a, _ in pairs), True)
check("copy: no temp files in destination", [f for f in listing(dst) if "srboli-part" in f], [])
check("old files need no waiting (30 files < 1s; used to be ~3s at 4 workers)", took < 1.0, True)
big = tree("src_big", n=200, size=1000)
t0 = time.perf_counter()
T.run_transfer(T.collect_files_with_relpaths(big), os.path.join(root, "dst_big"), "copy", 1)
check("200 old files, ONE worker, under 2s (was ~90s)", time.perf_counter() - t0 < 2.0, True)

# ── names: unique unless overwrite ──
res = T.run_transfer(pairs[:3], dst, "copy", 2)
check("existing names get (1)", all(os.path.exists(r[2]) and " (1)" in r[2] for r in res), True)
a, rel = pairs[0]
open(a, "wb").write(b"CHANGED"); t = time.time() - 3600; os.utime(a, (t, t))
res = T.run_transfer([(a, rel)], dst, "copy", 1, overwrite=True)
check("overwrite=True replaces", (res[0][0], open(os.path.join(dst, rel), "rb").read()), ("done", b"CHANGED"))

# ── move ──
msrc = tree("msrc", n=12); mdst = os.path.join(root, "mdst")
mp = T.collect_files_with_relpaths(msrc)
res = T.run_transfer(mp, mdst, "move", 3)
check("move: done, sources gone, destination complete", (sorted(set(r[0] for r in res)), [a for a, _ in mp if os.path.exists(a)], len(listing(mdst))), (["done"], [], 12))

# ── files that are not ready ──
young = tree("young", n=2, age=0, nested=False)
yp = T.collect_files_with_relpaths(young)
t0 = time.time()
res = T.run_transfer(yp, os.path.join(root, "ydst"), "copy", 2, settle=1.0)
took = time.time() - t0
check("young files wait for the settle time, then copy", (sorted(r[0] for r in res), 0.9 <= took < 5), (["done", "done"], True))
if os.path.isdir("/proc/self/fd"):
    busy = tree("busy", n=2, nested=False); bp = T.collect_files_with_relpaths(busy)
    code = "import sys,time;f=open(sys.argv[1],'ab');print('open',flush=True);time.sleep(60)"
    pr = subprocess.Popen([sys.executable, "-c", code, bp[0][0]], stdout=subprocess.PIPE, text=True); pr.stdout.readline()
    try:
        file_safety._open_cache["at"] = -1e9
        res = T.run_transfer(bp, os.path.join(root, "bdst"), "move", 2, max_wait=0.6)
        by = {os.path.basename(r[1]): r for r in res}
        check("a file another program writes is skipped and left in place",
              (by[os.path.basename(bp[0][0])][0], os.path.exists(bp[0][0])), ("skipped", True))
        check("the other file moved normally", (by[os.path.basename(bp[1][0])][0], os.path.exists(bp[1][0])), ("done", False))
    finally:
        pr.kill(); pr.wait()
res = T.run_transfer(T.collect_files_with_relpaths(tree("stopme", n=5)), os.path.join(root, "sdst"), "copy", 1, stop_check=lambda: True)
check("stop_check: nothing copied", (sorted(set(r[0] for r in res)), os.path.exists(os.path.join(root, "sdst"))), (["stopped"], False))

# ── auto-tune ──
check("knee: fewest workers within 10% of the best", T.pick_knee([(1, 10.0), (2, 5.5), (4, 3.1), (8, 3.0), (16, 3.2)]), 4)
check("knee: more is never picked when it isn't faster", T.pick_knee([(1, 4.0), (2, 4.1), (4, 4.2)]), 1)
check("knee: real gain at the top", T.pick_knee([(1, 10), (2, 6), (4, 3), (8, 1.5)]), 8)
check("sample: nothing to measure", T.pick_sample([]), ([], 0))
big_files = tree("tunesrc", n=100, size=4000)
tp = T.collect_files_with_relpaths(big_files)
paths, total = T.pick_sample(tp)
check("sample: spread, capped at 48 files", (len(paths) <= T.TUNE_MAX_FILES, len(paths) >= 40, total == 4000 * len(paths)), (True, True, True))
paths, total = T.pick_sample(tp, max_files=10, max_bytes=4000 * 6)
check("sample: respects the byte budget", len(paths) <= 6, True)
check("sample: skips files bigger than a quarter of the budget", T.pick_sample(tp, max_bytes=8000), ([], 0))
tune_dst = os.path.join(root, "tune_dst")
seen = []
out = T.autotune(tp, tune_dst, progress=lambda w, i, n: seen.append(w))
check("autotune result shape", (out is not None, [r[0] for r in out["results"]], out["best"] in (1, 2, 4, 8, 16), out["sample_files"] >= 40), (True, [1, 2, 4, 8, 16], True, True))
check("autotune: every setting measured, speeds positive", all(sec > 0 and mbs > 0 for _w, sec, mbs in out["results"]), True)
check("autotune reported progress", seen, [1, 2, 4, 8, 16])
check("autotune leaves nothing behind", os.listdir(tune_dst), [])
check("autotune: too few files -> None", T.autotune(tp[:5], tune_dst), None)
check("autotune: stopped -> None, still cleaned up", (T.autotune(tp, tune_dst, stop_check=lambda: True), os.listdir(tune_dst)), (None, []))
out = T.autotune(tp[:10], tune_dst)
check("autotune: sample smaller than a worker count skips it", [r[0] for r in out["results"]], [1, 2, 4, 8])

shutil.rmtree(root, ignore_errors=True)
print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
