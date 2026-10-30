# tests/test_safe_math.py - pure test (python3 tests/test_safe_math.py)
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.safe_math import arith

assert arith("1+2*3") == 7 and arith("(1+2)*3") == 9 and arith("-4+10%4") == -2
assert arith("2**10") == 1024 and arith("1e3+1") == 1001
for bad in ("", "__import__('os')", "a+1", "1+", "9" * 300, "[1]", "1 if 1 else 2", "1<2"):
    try:
        arith(bad); raise SystemExit(f"accepted {bad!r}")
    except (ValueError, SyntaxError):
        pass
t = time.time()
for hang in ("9**9**9", "9.0**9999999", "10**400"):
    try:
        arith(hang); raise SystemExit("no error for " + hang)
    except OverflowError:
        pass
assert time.time() - t < 1
try:
    arith("1/0"); raise SystemExit("1/0")
except ZeroDivisionError:
    pass
print("safe_math OK")
