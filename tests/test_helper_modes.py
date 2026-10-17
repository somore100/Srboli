# tests/test_helper_modes.py - no display needed.
# --cover / --cover-cmd / --daemon / --overlay must never reach Kivy's own
# argument parser ("option --cover-cmd not recognized" killed the Cover
# feature, the background service and the stats overlay for several versions).
import os, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
r = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"),
                    "--cover-cmd", "status"],
                   capture_output=True, text=True, timeout=60, cwd=ROOT)
out = r.stdout + r.stderr
assert "Kivy Usage" not in out and "not recognized" not in out, out[:400]
assert "cover process not running" in out or out.startswith("ok"), out[:300]
# the helper modes must be excluded from the boot log import
src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
for flag in ("--cover", "--cover-cmd", "--daemon", "--overlay"):
    assert f'"{flag}"' in src.split("_HELPER_MODE", 2)[1][:200], flag
print("helper modes OK")
