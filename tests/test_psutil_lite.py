# tests/test_psutil_lite.py - the Android stand-in for psutil (pure Python).
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import psutil_lite as pl

FAILS = []
def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + (f" - {info}" if info and not cond else ""))
    if not cond:
        FAILS.append(name)

# /proc/net/dev closed (Android 10+): fall back to the system byte counters
real_read, real_ts = pl._read, pl._traffic_stats
def closed(path):
    raise RuntimeError("not available on this device")
pl._read = closed
pl._traffic_stats = lambda: (1000, 2000)
n = pl.net_io_counters()
check("network via traffic stats", (n.bytes_sent, n.bytes_recv) == (1000, 2000), n)
def nope():
    raise RuntimeError("not available on this device")
pl._traffic_stats = nope
try:
    pl.net_io_counters(); check("network error when nothing works", False)
except RuntimeError:
    check("network error when nothing works", True)
pl._read, pl._traffic_stats = real_read, real_ts

# this process's own CPU use
check("first own-CPU reading is 0", pl.process_cpu_percent() == 0.0)
t = time.time()
while time.time() - t < 0.2:
    pass                                            # burn a little CPU
v = pl.process_cpu_percent()
check("own CPU is a sane percentage", 0.0 < v <= 100.0, v)

print("ALL OK" if not FAILS else f"FAILED: {FAILS}")
sys.exit(1 if FAILS else 0)
