# tests/test_file_safety.py - no display needed (python3 tests/test_file_safety.py)
import os, sys, time, shutil, tempfile, threading, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import file_safety as F

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

root = tempfile.mkdtemp()
def make(name, data=b"x" * 100, age=3600):
    p = os.path.join(root, name)
    with open(p, "wb") as f:
        f.write(data)
    if age is not None:
        t = time.time() - age
        os.utime(p, (t, t))
    return p

# ── static signals ──
p = make("old.bin")
r = F.check(p)
check("old file is ready", (r.ready, r.reason), (True, "ok"))
check("fresh file waits", F.check(make("fresh.bin", age=0)).ready, False)
check("fresh reason says why", "changed" in F.check(make("fresh2.bin", age=1)).reason, True)
check("settle is adjustable", (F.check(make("a.bin", age=3), settle=2).ready, F.check(make("b.bin", age=3), settle=10).ready), (True, False))
check("empty + young: not ready", F.check(make("e.bin", b"", age=60)).reason, "it is still empty (0 bytes)")
check("empty + very old: ready", F.check(make("e2.bin", b"", age=7200)).ready, True)
check("unfinished download name, young", F.check(make("movie.mp4.part", age=10)).reason, "it looks like an unfinished download")
check("same name once old", F.check(make("movie2.mp4.part", age=120)).ready, True)
check("missing", (F.check(os.path.join(root, "nope")).ready, F.check(os.path.join(root, "nope")).sig), (False, None))
check("directory", F.check(root).ready, False)
t = time.time() + 10 * 86400
fut = make("future.bin", age=None); os.utime(fut, (t, t))
check("far-future mtime doesn't block forever", (F.check(fut, settle=0).ready, 0 <= F.check(fut).age < 60), (True, True))

# editor lock files
for name, lock in [("doc.odt", ".~lock.doc.odt#"), ("report.docx", "~$report.docx"),
                   ("Document1.docx", "~$cument1.docx"), ("note.txt", ".note.txt.swp"), ("n.md", ".#n.md")]:
    make(name)
    check(f"ready before lock {name}", F.check(os.path.join(root, name)).ready, True)
    open(os.path.join(root, lock), "w").close()
    r = F.check(os.path.join(root, name))
    check(f"blocked by {lock}", (r.ready, "lock file" in r.reason), (False, True))
    os.remove(os.path.join(root, lock))

# ── another process holding the file open ──
if os.path.isdir("/proc/self/fd"):
    def holder(path, mode):
        code = "import sys,time;f=open(sys.argv[1],sys.argv[2]);print('open',flush=True);time.sleep(60)"
        pr = subprocess.Popen([sys.executable, "-c", code, path, mode], stdout=subprocess.PIPE, text=True)
        pr.stdout.readline()
        return pr
    w = make("writer.bin")
    pr = holder(w, "ab")
    try:
        F._open_cache["at"] = -1e9
        check("open for writing elsewhere: not ready", (F.check(w).ready, "open for writing" in F.check(w).reason), (False, True))
        check("it is in the list", os.path.realpath(w) in F.open_for_write_paths(max_age=0), True)
    finally:
        pr.kill(); pr.wait()
    rd = make("reader.bin")
    pr = holder(rd, "rb")
    try:
        F._open_cache["at"] = -1e9
        check("open for READING only: still ready", F.check(rd).ready, True)
    finally:
        pr.kill(); pr.wait()
    mine = make("mine.bin"); fh = open(mine, "ab")
    F._open_cache["at"] = -1e9
    check("our own open file doesn't block us", F.check(mine).ready, True)
    fh.close()
    F._open_cache["at"] = -1e9
    check("closed again: ready", F.check(w).ready, True)
    # the scan is cached
    F._open_cache["at"] = -1e9
    F.open_for_write_paths(); t0 = time.perf_counter()
    for _ in range(2000): F.open_for_write_paths()
    check("cached scan is cheap (2000 calls < 0.2s)", time.perf_counter() - t0 < 0.2, True)
    # many threads asking at the same moment must share ONE scan (Fast Transfer starts
    # up to 64 workers together; each doing its own scan wasted seconds)
    calls = []
    real_scan = F._scan_open_files
    def counting():
        calls.append(1); time.sleep(0.05); return real_scan()
    F._scan_open_files = counting
    F._open_cache["at"] = -1e9
    threads = [threading.Thread(target=F.open_for_write_paths) for _ in range(64)]
    for t_ in threads: t_.start()
    for t_ in threads: t_.join()
    F._scan_open_files = real_scan
    check("64 simultaneous callers cause one scan", len(calls), 1)
else:
    print("skip /proc tests (not Linux)")

# ── waiting ──
grow = make("grow.bin", age=0)
stop_writing = time.time() + 1.5
def writer():
    with open(grow, "ab") as f:
        while time.time() < stop_writing:
            f.write(b"y" * 1000); f.flush(); time.sleep(0.05)
th = threading.Thread(target=writer); th.start()
t0 = time.time()
ok = F.wait_until_ready(grow, settle=0.6, poll_interval=0.1)
size_at_return = os.path.getsize(grow); th.join()
check("waits for the writer to finish", (ok, time.time() - t0 >= 1.4), (True, True))
check("returned only after the last write", size_at_return, os.path.getsize(grow))
check("old file returns at once (no sleeping)", (lambda t=time.time(): (F.wait_until_ready(make("o2.bin")), time.time() - t < 0.2))(), (True, True))
msgs = []
check("max_wait gives up", F.wait_until_ready(make("never.bin", age=0), settle=999, poll_interval=0.05, max_wait=0.2, log=msgs.append), False)
check("gave-up is logged with the reason", any("gave up" in m for m in msgs) and any("waiting:" in m for m in msgs), True)
check("stop_check", F.wait_until_ready(make("s.bin", age=0), settle=999, poll_interval=0.05, stop_check=lambda: True), False)
check("vanished file", F.wait_until_ready(os.path.join(root, "missing")), False)
prog = []
F.wait_until_ready(make("p.bin", age=0), settle=999, poll_interval=0.05, max_wait=0.12, progress=lambda w, s: prog.append((round(w, 2), s)))
check("progress reports size", prog[0][1], 100)

# ── safe copy / move ──
dst_dir = os.path.join(root, "dst"); os.makedirs(dst_dir)
src = make("c.bin", os.urandom(5000))
d = os.path.join(dst_dir, "c.bin")
F.safe_copy(src, d)
check("copy matches", open(src, "rb").read() == open(d, "rb").read(), True)
check("copy keeps mtime (copy2)", int(os.stat(src).st_mtime) == int(os.stat(d).st_mtime), True)
check("no temp left", os.listdir(dst_dir), ["c.bin"])
try:
    F.safe_copy(src, d); check("won't overwrite", False, True)
except FileExistsError:
    check("won't overwrite", True, True)
src2 = make("c2.bin", b"new")
F.safe_copy(src2, d, overwrite=True)
check("overwrite=True replaces", open(d, "rb").read(), b"new")

# source changes DURING the copy -> abort, nothing at the destination, source intact
real_copy2 = shutil.copy2
def copy_then_change(s, t):
    real_copy2(s, t)
    with open(s, "ab") as f: f.write(b"more")
shutil.copy2 = copy_then_change
src3 = make("c3.bin", b"abc")
try:
    F.safe_copy(src3, os.path.join(dst_dir, "c3.bin")); check("detects change", False, True)
except F.FileChangedError:
    check("detects change", True, True)
finally:
    shutil.copy2 = real_copy2
check("changed copy leaves no file or temp", sorted(os.listdir(dst_dir)), ["c.bin"])
check("source untouched", os.path.exists(src3), True)
# copy that fails halfway leaves no temp
def boom(s, t):
    open(t, "wb").write(b"half"); raise OSError("disk full")
shutil.copy2 = boom
try:
    F.safe_copy(src3, os.path.join(dst_dir, "c4.bin")); check("failure raised", False, True)
except OSError:
    check("failure raised", True, True)
finally:
    shutil.copy2 = real_copy2
check("failed copy cleaned up", sorted(os.listdir(dst_dir)), ["c.bin"])

# move: same disk = rename; other disk = verified copy then delete
a = make("m1.bin", b"1" * 50); ino = os.stat(a).st_ino
F.safe_move(a, os.path.join(dst_dir, "m1.bin"))
check("same-disk move is a rename (same inode)", (os.path.exists(a), os.stat(os.path.join(dst_dir, "m1.bin")).st_ino), (False, ino))
F._same_device = lambda s, d: False                       # force the cross-disk path
b = make("m2.bin", b"2" * 50)
F.safe_move(b, os.path.join(dst_dir, "m2.bin"))
check("cross-disk move done", (os.path.exists(b), open(os.path.join(dst_dir, "m2.bin"), "rb").read()), (False, b"2" * 50))
shutil.copy2 = copy_then_change
b3 = make("m3.bin", b"3" * 50)
try:
    F.safe_move(b3, os.path.join(dst_dir, "m3.bin")); check("changed source: move aborted", False, True)
except F.FileChangedError:
    check("changed source: move aborted", True, True)
finally:
    shutil.copy2 = real_copy2
check("original kept when the copy is bad", (os.path.exists(b3), os.path.exists(os.path.join(dst_dir, "m3.bin"))), (True, False))
try:
    F.safe_move(make("m4.bin"), os.path.join(dst_dir, "m2.bin")); check("move won't overwrite", False, True)
except FileExistsError:
    check("move won't overwrite", True, True)
check("no temp files anywhere", [n for n in os.listdir(dst_dir) if "srboli-part" in n], [])

shutil.rmtree(root, ignore_errors=True)
print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
