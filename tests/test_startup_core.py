# tests/test_startup_core.py - python3 tests/test_startup_core.py
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import startup_core as s

T = "[Desktop Entry]\nName=Foo\nExec=foo --x\nType=Application\n"
k = s.parse_desktop(T)
assert k["Name"] == "Foo" and not s.desktop_disabled(k)
off = s.set_desktop_flags(T, True)
assert s.desktop_disabled(s.parse_desktop(off)) and "Exec=foo --x" in off
on = s.set_desktop_flags(off, False)
assert not s.desktop_disabled(s.parse_desktop(on)) and on == T
assert s.set_desktop_flags(off, True).count("Hidden") == 1
# flags land inside the [Desktop Entry] group even if another group follows
two = T + "[Desktop Action x]\nName=A\n"
assert s.parse_desktop(s.set_desktop_flags(two, True)).get("Hidden") == "true"

with tempfile.TemporaryDirectory() as root:
    sysd, usr = os.path.join(root, "sys"), os.path.join(root, "usr")
    os.makedirs(sysd); os.makedirs(usr)
    open(os.path.join(sysd, "a.desktop"), "w").write(T)
    open(os.path.join(usr, "b.desktop"), "w").write(T.replace("Foo", "Bee"))
    L = s._linux_list(usr, [sysd])
    assert [e["name"] for e in L] == ["Bee", "Foo"] and all(e["enabled"] for e in L)
    assert s._linux_set("a.desktop", False, usr, [sysd]) == (True, "")
    assert open(os.path.join(sysd, "a.desktop")).read() == T      # system file untouched
    assert not [e for e in s._linux_list(usr, [sysd]) if e["id"] == "a.desktop"][0]["enabled"]
    assert s._linux_set("a.desktop", True, usr, [sysd])[0]
    assert all(e["enabled"] for e in s._linux_list(usr, [sysd]))
    assert not s._linux_set("../x.desktop", False, usr, [sysd])[0]
    assert not s._linux_set("zz.desktop", False, usr, [sysd])[0]
assert s.approved_flag(bytes([2]) + bytes(11)) and not s.approved_flag(bytes([3]) + bytes(11))
print("startup core OK")
