# tests/test_when_done_core.py - python3 tests/test_when_done_core.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import when_done_core as w

# network: must be seen busy first, then quiet for the full time
m = w.Monitor("network", 50, 120)
assert "Waiting for the task to start" in m.update(0, 3) and not m.armed
m.update(10, 400); assert m.armed
m.update(20, 5); m.update(100, 5); assert not m.done
m.update(130, 900); assert m.quiet_since is None                 # busy again: restart the quiet time
m.update(140, 1); assert not m.update(250, 1).startswith("Quiet long") and not m.done
assert "done" in m.update(262, 1) and m.done
assert m.update(300, 9999) == "Done."                            # stays done
# need_active=False: idle from the start counts
m = w.Monitor("cpu", 10, 60, need_active=False); m.update(0, 2); m.update(61, 2); assert m.done
m = w.Monitor("cpu"); assert m.threshold == 10.0 and m.quiet_secs == 180.0
# process
m = w.Monitor("process"); assert "Waiting for the program to start" in m.update(0, False) and not m.done
m.update(1, True); m.update(2, True); assert not m.done
assert "finished" in m.update(3, False) and m.done
m = w.Monitor("process", need_active=False); m.update(0, False); assert m.done
try: w.Monitor("coffee"); assert 0
except ValueError: pass

# commands
assert w.power_command("Shut down", "linux") == ["systemctl", "poweroff"]
assert w.power_command("Shut down", "win32") == ["shutdown", "/s", "/t", "0"]
assert w.power_command("Sleep", "darwin") == ["pmset", "sleepnow"]
assert w.power_command("Only notify") is None
got = []
assert w.run_action("Sleep", "linux", got.append) and got == [["systemctl", "suspend"]]
assert not w.run_action("Only notify", "linux", got.append) and len(got) == 1

# sampler with a fake psutil
class N: bytes_sent = 0; bytes_recv = 0
class D: read_bytes = 0; write_bytes = 0
class P:
    def __init__(s, n): s.info = {"name": n}
class FakePs:
    net = N(); dsk = D()
    def cpu_percent(self, interval=None): return 7.0
    def net_io_counters(self): return self.net
    def disk_io_counters(self): return self.dsk
    def process_iter(self, attrs): return [P("rclone"), P("Xorg"), P("rclone")]
ps = FakePs(); s = w.Sampler(ps)
assert s.reading("network", 0) == 0.0
ps.net.bytes_recv = 10 * 1024 * 2
assert abs(s.reading("network", 2) - 10.0) < 1e-6
assert s.reading("cpu") == 7.0 and s.reading("process", name="rclone") and not s.reading("process", name="nope")
assert w.list_processes(ps) == ["rclone", "Xorg"] or w.list_processes(ps) == ["rclone", "Xorg"][::-1] or set(w.list_processes(ps)) == {"rclone", "Xorg"}
print("when done core OK")
