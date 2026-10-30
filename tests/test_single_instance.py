# tests/test_single_instance.py - pure test (python3 tests/test_single_instance.py)
import os, sys, subprocess, tempfile
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
from core import single_instance as si

lock = os.path.join(tempfile.mkdtemp(), "sub", ".srboli.lock")
assert si.acquire(lock)                       # folder is created on demand
probe = ("import sys; sys.path.insert(0, %r); from core import single_instance as s; "
         "sys.exit(0 if s.acquire(%r) else 7)" % (ROOT, lock))
assert subprocess.run([sys.executable, "-c", probe]).returncode == 7   # second one is refused
si.release()
assert subprocess.run([sys.executable, "-c", probe]).returncode == 0   # free again after release
env = dict(os.environ, SROBOLI_MULTI="1")
assert si.acquire(lock)
assert subprocess.run([sys.executable, "-c", probe], env=env).returncode == 0   # dev override
print("single_instance OK")
