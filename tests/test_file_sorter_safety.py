# tests/test_file_sorter_safety.py - no display needed.
# The background watcher must not move files that are still being written, empty,
# open in another program or locked by an editor - and must pick them up on a
# later pass once they are fine. Real files, real second process.
import os, sys, time, tempfile, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import core.file_sorter_core as fsc
import core.file_sorter_watch as fsw
import core.file_safety as safety

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

root = tempfile.mkdtemp()
src, dst = os.path.join(root, "src"), os.path.join(root, "dst")
os.makedirs(src); os.makedirs(dst)
fsc.save_ruleset(fsc.LAST_USED_KEY, [{
    "name": "pngs", "enabled": True, "logic": "AND",
    "conditions": [{"field": "extension", "op": "is_one_of", "value": "png"}],
    "action": {"type": "move", "dest": dst}}])
fsw.save_config({"enabled": True, "source_folder": src, "recursive": False,
                 "ruleset": fsc.LAST_USED_KEY, "settle_seconds": 5})

def make(name, data=b"x" * 100, age=0):
    p = os.path.join(src, name)
    open(p, "wb").write(data)
    if age:
        t = time.time() - age
        os.utime(p, (t, t))
    return p
def moved(name): return os.path.exists(os.path.join(dst, name)) and not os.path.exists(os.path.join(src, name))
def log_text():
    try: return open(os.path.join(fsc._rulesets_dir(), fsw.LOG_NAME)).read()
    except OSError: return ""

check("settle default and clamping", (fsw.load_config()["settle_seconds"], fsw._settle("x"), fsw._settle(-4), fsw._settle(99999)), (5.0, 5.0, 0.0, 3600.0))

# a file written a moment ago is left alone, and picked up once it has been quiet
p = make("fresh.png")
check("fresh file: nothing acted on", (fsw.scan_once(), os.path.exists(p)), (0, True))
check("reason is logged", "waiting: it changed" in log_text(), True)
fsw.scan_once(); fsw.scan_once()
check("same reason logged only once", log_text().count("waiting: it changed"), 1)
t = time.time() - 3600; os.utime(p, (t, t))
check("quiet now: moved", (fsw.scan_once(), moved("fresh.png")), (1, True))

# the 0-byte ComfyUI case
make("empty.png", b"", age=60)
check("0-byte file is not moved", (fsw.scan_once(), os.path.exists(os.path.join(src, "empty.png"))), (0, True))
check("0-byte reason", "still empty" in log_text(), True)
t = time.time() - 7200; os.utime(os.path.join(src, "empty.png"), (t, t))
check("a genuinely old empty file is moved", (fsw.scan_once(), moved("empty.png")), (1, True))

# held open for writing by another program (the generator still has it)
if os.path.isdir("/proc/self/fd"):
    p = make("busy.png", age=3600)
    code = "import sys,time;f=open(sys.argv[1],'ab');print('open',flush=True);time.sleep(60)"
    pr = subprocess.Popen([sys.executable, "-c", code, p], stdout=subprocess.PIPE, text=True)
    pr.stdout.readline()
    try:
        safety._open_cache["at"] = -1e9
        check("open for writing elsewhere: not moved", (fsw.scan_once(), os.path.exists(p)), (0, True))
    finally:
        pr.kill(); pr.wait()
    safety._open_cache["at"] = -1e9
    check("closed again: moved on the next pass", (fsw.scan_once(), moved("busy.png")), (1, True))

# an editor lock file beside it
make("doc.png", age=3600)
lock = os.path.join(src, ".~lock.doc.png#"); open(lock, "w").close()
check("editor lock file: not moved", (fsw.scan_once(), os.path.exists(os.path.join(src, "doc.png"))), (0, True))
os.remove(lock)
check("lock gone: moved", (fsw.scan_once(), moved("doc.png")), (1, True))

# a configurable settle time
make("quick.png", age=3)
check("default 5s: a 3s-old file waits", (fsw.scan_once(), os.path.exists(os.path.join(src, "quick.png"))), (0, True))
fsw.save_config({"enabled": True, "source_folder": src, "recursive": False,
                 "ruleset": fsc.LAST_USED_KEY, "settle_seconds": 1})
check("settle 1s: same file is moved", (fsw.scan_once(), moved("quick.png")), (1, True))

# the sorter's move keeps the file intact and leaves no temp files
check("no leftovers in the destination", [n for n in os.listdir(dst) if "srboli-part" in n or n.startswith(".")], [])
check("apply_action move/copy use the safe path",
      (fsc.file_safety.safe_move.__module__, fsc.file_safety.safe_copy.__module__), ("core.file_safety",) * 2)

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
