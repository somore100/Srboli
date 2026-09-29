# tests/test_notify.py — OS notification command building. No Kivy, no
# real notifier needed (a fake runner records what would have been run).
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core.notify as N

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

class FakeResult:
    def __init__(self, returncode=0):
        self.returncode = returncode

class FakeRunner:
    def __init__(self, returncode=0, raise_exc=None):
        self.calls = []
        self.returncode = returncode
        self.raise_exc = raise_exc
    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.raise_exc:
            raise self.raise_exc
        return FakeResult(self.returncode)

# ---- Linux
fr = FakeRunner()
ok = N.send_notification("Take pills", "It's 9am", runner=fr, system="Linux")
check("linux: reports success", ok, True)
check("linux: uses notify-send", fr.calls[0][0][0], "notify-send")
check("linux: title/message passed through", fr.calls[0][0][-2:], ["Take pills", "It's 9am"])
check("linux: has a timeout", fr.calls[0][1].get("timeout"), N.DEFAULT_TIMEOUT)

# ---- macOS
fr = FakeRunner()
N.send_notification('He said "hi"', "back\\slash", runner=fr, system="Darwin")
check("macos: uses osascript", fr.calls[0][0][0], "osascript")
script = fr.calls[0][0][2]
check("macos: quotes escaped", '\\"hi\\"' in script, True)
check("macos: backslash escaped", "back\\\\slash" in script, True)

# ---- Windows
fr = FakeRunner()
N.send_notification('Quote " test', "dollar $ test", runner=fr, system="Windows")
check("windows: uses powershell", fr.calls[0][0][0], "powershell")
script = fr.calls[0][0][-1]
check("windows: double-quote doubled", '""' in script, True)
check("windows: dollar sign escaped (avoid var interpolation)", "`$" in script, True)
check("windows: builds a toast via WinRT", "ToastNotificationManager" in script, True)

# ---- unsupported platform
ok = N.send_notification("x", "y", runner=FakeRunner(), system="Plan9")
check("unsupported platform returns False, no crash", ok, False)

# ---- non-zero exit -> False, no crash
ok = N.send_notification("x", "y", runner=FakeRunner(returncode=1), system="Linux")
check("non-zero exit reported as failure", ok, False)

# ---- missing binary -> False, no crash
ok = N.send_notification("x", "y", runner=FakeRunner(raise_exc=FileNotFoundError()), system="Linux")
check("missing binary handled, no crash", ok, False)

# ---- unexpected exception -> False, no crash (never take the daemon down)
ok = N.send_notification("x", "y", runner=FakeRunner(raise_exc=RuntimeError("boom")), system="Linux")
check("unexpected runner error handled, no crash", ok, False)

# ---- real call against the real subprocess.run, real (missing) binary on this box
ok = N.send_notification("Real call test", "no notify-send here", system="Linux")
check("real subprocess.run + missing notify-send doesn't raise, returns False", ok, False)

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
