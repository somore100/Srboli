import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.selftest import check_screens
bad = check_screens([("ok", "os.path", "join"), ("nomod", "no_such_mod_xyz", "X"), ("nocls", "os.path", "Nope")])
assert [r for r, _ in bad] == ["nomod", "nocls"], bad
print("selftest OK")
