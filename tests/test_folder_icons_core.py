# tests/test_folder_icons_core.py - python3 tests/test_folder_icons_core.py
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
from PIL import Image
from core import folder_icons_core as fi, clean_env as ce

class R:  # fake subprocess.run result
    returncode = 0
calls = []
def runner(cmd, **kw):
    calls.append(cmd); return R()

# colour icon: transparent corner, coloured middle
p = fi.color_icon("#3e63dd"); im = Image.open(p)
assert im.size == (256, 256) and im.getpixel((2, 2))[3] == 0 and im.getpixel((128, 170))[:3] == (0x3e, 0x63, 0xdd)
assert fi.color_icon("#3e63dd") == p                       # cached
try: fi.make_color_icon("nope", os.path.join(tempfile.mkdtemp(), "x.png")); assert 0
except fi.IconError: pass

# picture icon
src = os.path.join(tempfile.mkdtemp(), "a.png"); Image.new("RGB", (400, 200), (200, 10, 10)).save(src)
q = fi.image_icon(src); iq = Image.open(q)
assert iq.getpixel((128, 170))[:3] == (200, 10, 10) and iq.getpixel((2, 2))[3] == 0
try: fi.image_icon("/no/such.png"); assert 0
except fi.IconError: pass
bad = os.path.join(tempfile.mkdtemp(), "b.png"); open(bad, "w").write("not a picture")
try: fi.image_icon(bad); assert 0
except fi.IconError: pass

# linux apply / reset
f = tempfile.mkdtemp()
done = fi.apply(f, p, platform="linux", runner=runner)
txt = open(os.path.join(f, ".directory")).read()
assert f"Icon={p}" in txt and fi.MARK in txt and fi.current(f)
assert any(c[:3] == ["gio", "set", "-t"] and c[-1] == "file://" + p for c in calls), calls
assert fi.reset(f, platform="linux", runner=runner) is True
assert not os.path.exists(os.path.join(f, ".directory")) and not fi.current(f)
assert calls[-1][3:] == [os.path.abspath(f), "metadata::custom-icon"] or "unset" in calls[-1]
# never overwrite the user's own .directory
g = tempfile.mkdtemp(); open(os.path.join(g, ".directory"), "w").write("[Desktop Entry]\nIcon=mine\n")
done = fi.apply(g, p, platform="linux", runner=runner)
assert "mine" in open(os.path.join(g, ".directory")).read() and "kept" in done[0]
assert fi.reset(g, platform="linux", runner=runner) is False and os.path.exists(os.path.join(g, ".directory"))

# windows
w = tempfile.mkdtemp(); calls.clear()
assert fi.apply(w, p, platform="win32", runner=runner) == ["Explorer (desktop.ini)"]
ini = open(os.path.join(w, "desktop.ini")).read()
assert ".ShellClassInfo" in ini and ".ico,0" in ini and os.path.exists(p.replace(".png", ".ico"))
assert ["attrib", "+r", os.path.abspath(w)] in calls
assert fi.reset(w, platform="win32", runner=runner) and not os.path.exists(os.path.join(w, "desktop.ini"))

# mac / errors / targets
try: fi.apply(f, p, platform="darwin", runner=runner); assert 0
except fi.IconError: pass
assert not fi.supported("darwin") and fi.supported("linux")
try: fi.apply("/no/such/dir", p, platform="linux", runner=runner); assert 0
except fi.IconError: pass
t = tempfile.mkdtemp(); [os.mkdir(os.path.join(t, n)) for n in ("a", "b", ".hid")]; open(os.path.join(t, "f"), "w").close()
assert fi.targets(t) == [t] and fi.targets(t, True) == [t, os.path.join(t, "a"), os.path.join(t, "b")]

# clean_env: bundled libs removed, user's own value restored
e = ce.clean_env({"LD_LIBRARY_PATH": "/bundle", "LD_LIBRARY_PATH_ORIG": "/usr/lib/x", "PATH": "/bin"})
assert e["LD_LIBRARY_PATH"] == "/usr/lib/x" and "LD_LIBRARY_PATH_ORIG" not in e and e["PATH"] == "/bin"
e = ce.clean_env({"LD_LIBRARY_PATH": "/bundle", "LD_LIBRARY_PATH_ORIG": ""}); assert e["LD_LIBRARY_PATH"] == ""
assert ce.clean_env({"LD_LIBRARY_PATH": "/mine", "PATH": "x"})["LD_LIBRARY_PATH"] == "/mine"   # not bundled: untouched
import subprocess
ce.install(); ce.install()
assert subprocess.run(["echo", "hi"], capture_output=True).stdout == b"hi\n"
print("folder icons OK")
