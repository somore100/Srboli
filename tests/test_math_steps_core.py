# tests/test_math_steps_core.py - pure test (python3 tests/test_math_steps_core.py)
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fractions import Fraction as F
from core import math_steps_core as m

def P(t): return m.to_poly(m.parse_expr(t))
def eq(a, b): assert a == b, f"{a!r} != {b!r}"

# parsing: implicit multiplication, precedence, powers, unary minus, decimals
eq(P("2x+3"), P("2*x+3")); eq(P("3(x+2)"), P("3x+6")); eq(P("(x+1)(x-1)"), P("x^2-1"))
eq(P("-x^2"), P("0-x^2")); eq(P("2^3^2"), m.Poly.const(512)); eq(P("x/2"), P("0.5x"))
eq(P("1/2x"), P("x/2")); eq(P("x(x+1)"), P("x^2+x")); eq(P("5-3-1"), m.Poly.const(1))
eq(P("2×x − 1"), P("2x-1")); eq(P("x**2"), P("x^2")); eq(P("xy+yx"), P("2xy"))
for bad in ("", "2+", "(x+1", "x+)", "3 4", "x$2"):
    try: m.parse_expr(bad) if bad else m.parse_expr(bad); raise SystemExit(f"accepted {bad!r}")
    except m.MathError: pass
for ns in ("1/x", "x^-1", "x^0.5", "2^x"):
    try: P(ns); raise SystemExit(f"accepted {ns!r}")
    except m.NotSupported: pass
try: P("1/0"); raise SystemExit("1/0")
except m.MathError: pass
try: P("x^50"); raise SystemExit("x^50")
except m.NotSupported: pass

# writing back out (and it reads back to the same thing)
for t, want in (("3x+6-x", "2x + 6"), ("-x+1", "-x + 1"), ("x/2+1/3", "(1/2)x + 1/3"),
                ("x^2-4+3x", "x^2 + 3x - 4"), ("0", "0"), ("xy+y^2", "xy + y^2")):
    eq(m.fmt(P(t)), want); eq(P(m.fmt(P(t))), P(t))

# simplest form
for t, want in (("2x+3", True), ("3+2x", True), ("x/2", True), ("(1/2)x+1", True), ("x^2-4", True),
                ("2x+3x", False), ("3(x+1)", False), ("x+(y+z)", False), ("x-(1+2)", False),
                ("2*3", False), ("4/2", False), ("1x", False), ("0+x", False), ("x+0", False),
                ("2x/3", False), ("14", True), ("-x", True), ("x*x", False)):
    eq(m.is_simplified(m.parse_expr(t)), want), t

# equation steps: any equivalent route is accepted
s = m.Session("3(x+2)=15")
for t, rule in (("3x+6=15", "expanded the brackets"), ("3x=15-6", "subtracted 6 on both sides"),
                ("3x=9", "combined like terms"), ("x=3", "divided both sides by 3")):
    r = s.submit(t); assert r.ok, (t, r.message); assert rule in r.message, (t, r.message)
assert r.done and s.status() == "x = 3" and s.wrong == 0

s = m.Session("2x+3=7")                                  # a different route: divide first (via fractions)
assert s.submit("x+3/2=7/2").ok
assert "subtracted 3/2" in s.submit("x=2").message and s.status() == "x = 2"

# naming
def step(a, b): return m.name_step(m.Line(a), m.Line(b))
eq(step("2x+3=7", "2x=4"), "subtracted 3 on both sides")
eq(step("2x=4", "x=2"), "divided both sides by 2")
eq(step("x/2=3", "x=6"), "multiplied both sides by 2")
eq(step("2x+1=x+5", "x+1=5"), "subtracted x on both sides")
eq(step("x=3", "3=x"), "swapped the two sides")
eq(step("x=-2", "-x=2"), "multiplied both sides by -1")
eq(step("2x+3", "2x+1+2"), "simplified")
eq(step("2x+3x", "5x"), "combined like terms")

# wrong steps say why, and are not kept
s = m.Session("2x+3=7")
r = s.submit("2x=7+3"); assert r.kind == "wrong" and "across the '='" in r.message, r.message
r = s.submit("2x=5"); assert r.kind == "wrong" and "plain numbers" in r.message, r.message
r = s.submit("5x=7"); assert r.kind == "wrong"
r = s.submit("2x-3=7"); assert r.kind == "wrong" and "sign" in r.message, r.message
r = s.submit("x+x=y"); assert r.kind == "wrong"                  # new variable
r = s.submit("2x+3"); assert r.kind == "wrong" and "equation" in r.message
assert len(s.lines) == 1 and s.wrong == 5 and s.submit("2x=4").ok
s = m.Session("3x+2x")
r = s.submit("6x"); assert r.kind == "wrong" and "number in front of x" in r.message, r.message
r = s.submit("5x"); assert r.ok and r.done and s.status() == "fully simplified"
r = m.Session("2(x+3)").submit("2x+3"); assert "plain numbers" in r.message
r = m.Session("2(x+3)").submit("2x-6"); assert "sign" in r.message or "plain numbers" in r.message
r = m.Session("x+1").submit("x+1"); assert r.kind == "info"        # same line: no penalty
r = m.Session("x+1").submit("x+"); assert r.kind == "info" and m.Session("x+1").wrong == 0

# unusual results
assert m.Session("2x+1=2x+3").submit("1=3").ok            # contradiction is a legal route...
s = m.Session("2x+1=2x+3"); assert s.status() == "no solution"
assert m.solved(m.Line("0=0")) == "true" and m.solved(m.Line("2x=2x")) == "true for every value"
s = m.Session("x^2=4")                                      # quadratics: steps checked, not solved
assert s.submit("x^2-4=0").ok and s.submit("(x-2)(x+2)=0").ok and not s.submit("(x-2)(x-2)=0").ok
assert "can't suggest" in s.hint(1) and m.solution("x^2=4") == []

# the solver
eq([t for t, _ in m.solution("2x+3=5x-1")], ["-3x + 3 = -1", "-3x = -4", "x = 4/3"])
eq([t for t, _ in m.solution("5=2x")][-1], "x = 5/2")
eq([t for t, _ in m.solution("x/3=2")], ["x = 6"])
eq([t for t, _ in m.solution("2(x+1)+3x")], ["5x + 2"])
for prob in ("3x-7=2", "4(x-1)=2x+6", "0.5x+1=3", "x-1/2=3/4", "7-2x=x+1", "-x=5", "(x+1)/2=4"):
    steps = m.solution(prob)
    assert steps, prob
    line = m.Line(prob)
    for text, why in steps:                                  # every solver step is itself valid
        nxt = m.Line(text); assert m.proportional(line.P, nxt.P) is not None, (prob, text); line = nxt
    assert m.solved(line).startswith("x = "), (prob, steps)

# hints reveal gradually and the session tracks them
s = m.Session("2x+3=5x-1")
h1, h2, h3 = s.hint(1), s.hint(2), s.hint(3)
assert "x terms" in h1 and "Subtract 5x" in h2 and h3 == "-3x + 3 = -1" and s.hints == 3 and s.revealed == 1
assert s.submit(h3).ok
assert [t for t, _ in s.solution_from_here()] == ["-3x = -4", "x = 4/3"]
assert "hint" in s.summary()
s = m.Session("x=2"); assert s.status() == "x = 2" and "done" in s.hint(1)

# complexity
eq(m.complexity("x+1=3")[0], "Easy"); eq(m.complexity("2x+3=5x-1")[0], "Medium")
eq(m.complexity("2(x+3)-4(x-1)=3(x+2)-5")[0], "Medium"); eq(m.complexity("3(2x-1)-2(x+4)=5(x-2)+x-7")[0], "Medium"); eq(m.complexity("x^2=4"), ("Hard", None))
eq(m.complexity("x+"), ("Hard", None))

# a long wrong-step stream never raises
import random
rng = random.Random(1)
alpha = list("x12+-*/()^= ")
for _ in range(3000):
    t = "".join(rng.choice(alpha) for _ in range(rng.randint(0, 10)))
    try: m.Session("2x+3=7").submit(t)
    except Exception as e: raise SystemExit(f"crashed on {t!r}: {e!r}")
print("math steps core OK")
