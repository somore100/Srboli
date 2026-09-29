# tests/test_autostart.py — login-time autostart toggle (Linux path
# tested for real on this box; Windows path exercised via a stub winreg
# module injected into sys.modules, since the real module only exists
# on Windows). No Kivy.
import os, sys, tempfile, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

home = tempfile.mkdtemp()
os.environ["HOME"] = home
import core.autostart as A

CMD = ["/usr/bin/python3", "/opt/srboli/main.py", "--daemon"]

# ---- Linux path, for real
check("supported on Linux", A.is_supported(), True)
check("starts disabled", A.is_enabled(), False)

ok, err = A.enable(CMD)
check("enable reports ok", (ok, err), (True, None))
check("now reports enabled", A.is_enabled(), True)

path = os.path.join(home, ".config", "autostart", "srboli-daemon.desktop")
check("desktop file created", os.path.isfile(path), True)
content = open(path, encoding="utf-8").read()
check("Exec line present and quoted", 'Exec=/usr/bin/python3 /opt/srboli/main.py --daemon' in content, True)
check("marked as a real autostart entry", "X-GNOME-Autostart-enabled=true" in content, True)
check("no leftover .tmp file", os.path.isfile(path + ".tmp"), False)

# a command with a space in it must be shell-quoted or the desktop file lies
ok, err = A.enable(["/usr/bin/python3", "/opt/My Apps/Srboli/main.py", "--daemon"])
content = open(path, encoding="utf-8").read()
check("path with a space is quoted", "'/opt/My Apps/Srboli/main.py'" in content, True)

ok, err = A.disable()
check("disable reports ok", (ok, err), (True, None))
check("file removed after disable", os.path.isfile(path), False)
check("now reports disabled", A.is_enabled(), False)

ok, err = A.disable()
check("disabling twice is harmless", (ok, err), (True, None))

# ---- Windows path, via a stub winreg (the real one doesn't exist here)
class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 1
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __init__(self, outer):
            self.outer = outer
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def CreateKey(self, root, path):
        return self._Key(self)

    def OpenKey(self, root, path, *a, **kw):
        if "SrboliDaemon" not in self.values and not a:
            pass
        return self._Key(self)

    def SetValueEx(self, key, name, reserved, type_, value):
        self.values[name] = value

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise OSError("not found")
        return (self.values[name], 1)

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError()
        del self.values[name]

fake_reg = FakeWinreg()
sys.modules["winreg"] = fake_reg
import importlib
A2 = importlib.reload(A)
A2._platform = lambda: "Windows"

check("windows: starts disabled", A2.is_enabled(), False)
ok, err = A2.enable(CMD)
check("windows: enable reports ok", (ok, err), (True, None))
check("windows: registry value set", fake_reg.values.get("SrboliDaemon"),
      "/usr/bin/python3 /opt/srboli/main.py --daemon")
check("windows: now reports enabled", A2.is_enabled(), True)
ok, err = A2.disable()
check("windows: disable reports ok", (ok, err), (True, None))
check("windows: now reports disabled", A2.is_enabled(), False)
ok, err = A2.disable()
check("windows: disabling twice is harmless", (ok, err), (True, None))
del sys.modules["winreg"]
importlib.reload(A)

print("\nFAILURES:", fails)
sys.exit(1 if fails else 0)
