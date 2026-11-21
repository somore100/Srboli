# core/when_done_core.py - "do X when the task is done" (shut down, sleep, notify).
# A computer can't know what "done" means, so Srboli watches something that
# goes quiet when a task ends:
#   process  a program you pick (e.g. rclone, ffmpeg, a game installer) has exited
#   network  upload + download traffic stays under N KB/s for M minutes
#            (a Google Drive / cloud upload finished)
#   cpu      CPU stays under N % for M minutes (rendering, encoding, compiling)
#   disk     disk reads+writes stay under N KB/s for M minutes (copying files)
# The quiet kinds only count once the task has been seen working ("armed"), so
# starting the watch before the upload begins never powers off an idle PC.
# Pure Python: Monitor is a small state machine fed by Sampler, so it is tested
# without waiting. Nothing is run until the Srboli screen does it after a
# visible countdown that can be cancelled.
import os
import subprocess
import sys
import time

KINDS = ("process", "network", "cpu", "disk")
ACTIONS = ("Shut down", "Sleep", "Only notify")

DEFAULTS = {"network": 50.0, "cpu": 10.0, "disk": 200.0}     # KB/s, %, KB/s
UNITS = {"process": "", "network": "KB/s", "cpu": "%", "disk": "KB/s"}


class Monitor:
    """Feed it one reading at a time with update(); .done turns True when the
    watched task has ended. `threshold` is KB/s (network, disk) or % (cpu);
    `quiet_secs` is how long it must stay below that."""

    def __init__(self, kind, threshold=None, quiet_secs=180.0, need_active=True):
        if kind not in KINDS:
            raise ValueError(kind)
        self.kind = kind
        self.threshold = DEFAULTS.get(kind, 0.0) if threshold is None else float(threshold)
        self.quiet_secs = max(0.0, float(quiet_secs))
        self.need_active = need_active
        self.armed = not need_active or kind == "process"
        self.quiet_since = None
        self.done = False
        self.value = 0.0
        self.seen_alive = False

    def update(self, now, reading):
        """`reading`: the current KB/s or %, or for 'process' True/False (still
        running?). Returns a one-line status for the screen."""
        if self.done:
            return "Done."
        if self.kind == "process":
            alive = bool(reading)
            if alive:
                self.seen_alive = True
                return "Waiting: the program is still running."
            if not self.seen_alive and self.need_active:
                return "Waiting for the program to start..."
            self.done = True
            return "The program has finished."
        self.value = float(reading)
        unit = UNITS[self.kind]
        busy = self.value > self.threshold
        if busy:
            self.armed = True
            self.quiet_since = None
            return f"Busy: {self.value:.0f} {unit} (quiet limit {self.threshold:.0f} {unit})"
        if not self.armed:
            return (f"Waiting for the task to start ({self.value:.0f} {unit}, "
                    f"needs more than {self.threshold:.0f})")
        if self.quiet_since is None:
            self.quiet_since = now
        quiet = now - self.quiet_since
        if quiet >= self.quiet_secs:
            self.done = True
            return "Quiet long enough: done."
        return (f"Quiet for {int(quiet)} of {int(self.quiet_secs)} s "
                f"({self.value:.0f} {unit})")


class Sampler:
    """Reads the numbers Monitor needs (psutil). KB/s are averaged since the
    previous call."""

    def __init__(self, psutil_mod=None):
        if psutil_mod is None:
            import psutil as psutil_mod
        self.ps = psutil_mod
        self._last = {}
        self.ps.cpu_percent(interval=None)

    def _rate(self, key, total, now):
        prev = self._last.get(key)
        self._last[key] = (now, total)
        if not prev or now <= prev[0]:
            return 0.0
        return max(0.0, (total - prev[1]) / (now - prev[0]) / 1024.0)

    def reading(self, kind, now=None, name=None):
        now = time.monotonic() if now is None else now
        if kind == "cpu":
            return self.ps.cpu_percent(interval=None)
        if kind == "network":
            n = self.ps.net_io_counters()
            return self._rate("net", n.bytes_sent + n.bytes_recv, now)
        if kind == "disk":
            d = self.ps.disk_io_counters()
            return self._rate("disk", d.read_bytes + d.write_bytes, now) if d else 0.0
        if kind == "process":
            return name in self.process_names()
        raise ValueError(kind)

    def process_names(self):
        out = set()
        for p in self.ps.process_iter(["name"]):
            try:
                n = p.info.get("name")
                if n:
                    out.add(n)
            except Exception:
                pass
        return out


def list_processes(psutil_mod=None):
    """Sorted names of running programs (own user's first is not needed)."""
    return sorted(Sampler(psutil_mod).process_names(), key=str.lower)


def power_command(action, platform=None):
    """argv for an action, or None when it only notifies / is unsupported."""
    p = platform or sys.platform
    if action == "Shut down":
        if p.startswith("win"):
            return ["shutdown", "/s", "/t", "0"]
        if p == "darwin":
            return ["osascript", "-e", 'tell app "System Events" to shut down']
        return ["systemctl", "poweroff"]
    if action == "Sleep":
        if p.startswith("win"):
            return ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        if p == "darwin":
            return ["pmset", "sleepnow"]
        return ["systemctl", "suspend"]
    return None


def run_action(action, platform=None, runner=None):
    """Do it. Returns True if a command was started."""
    cmd = power_command(action, platform)
    if not cmd:
        return False
    (runner or subprocess.Popen)(cmd)
    return True
