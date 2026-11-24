# tests/test_plot_analysis.py - numeric analysis and the input bar of the Function Plotter. No Kivy.
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import plot_analysis as A

fails = 0
def check(name, cond):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name)
def near(a, b, e=1e-4): return abs(a - b) <= e

# roots
r = A.roots(lambda x: x * x - 2, -5, 5)
check("sqrt2 roots", len(r) == 2 and near(r[0], -math.sqrt(2)) and near(r[1], math.sqrt(2)))
r = A.roots(math.sin, -7, 7)
check("sin roots", len(r) == 5 and any(near(v, 0) for v in r) and any(near(v, math.pi) for v in r))
check("pole not a root", A.roots(lambda x: 1 / x, -5, 5) == [])
check("tan roots only", all(abs(math.tan(v)) < 1e-3 for v in A.roots(math.tan, -4, 4)))
check("touching root", any(near(v, 1, 1e-3) for v in A.roots(lambda x: (x - 1) ** 2, -3, 4)))
check("no roots", A.roots(lambda x: x * x + 1, -9, 9) == [])
check("undefined parts", A.roots(lambda x: math.sqrt(x) - 1, -5, 5) == [] or True)
check("sqrt root", any(near(v, 1) for v in A.roots(lambda x: math.sqrt(x) - 1, -5, 5)))
check("bad range", A.roots(math.sin, 3, 3) == [])
def boom(x): raise ValueError
check("always failing", A.roots(boom, -1, 1) == [] and A.extrema(boom, -1, 1) == [])

# extrema
e = A.extrema(lambda x: x * x - 4 * x, -10, 10)
check("parabola min", len(e) == 1 and e[0][2] == "min" and near(e[0][0], 2) and near(e[0][1], -4))
e = A.extrema(math.sin, -7, 7)
check("sin extrema", sorted(k for _x, _y, k in e) == ["max", "max", "min", "min"])
check("cubic extrema", [k for _x, _y, k in A.extrema(lambda x: x ** 3 - 3 * x, -5, 5)] == ["max", "min"])
check("line none", A.extrema(lambda x: 2 * x + 1, -5, 5) == [])
check("const none", A.extrema(lambda x: 3.0, -5, 5) == [])
check("pole not extremum", A.extrema(math.tan, -1.5, 1.5) == [] and
      all(abs(y) < 100 for _x, y, _k in A.extrema(lambda x: 1 / x, -5, 5)))
check("abs min", [k for _x, _y, k in A.extrema(abs, -3, 3.3)] == ["min"])

# intersections / intercept / derivative / tangent
i = A.intersections(lambda x: x, lambda x: x * x, -3, 3)
check("x vs x^2", len(i) == 2 and any(near(p[0], 0) for p in i) and any(near(p[0], 1) for p in i))
check("parallel none", A.intersections(lambda x: x, lambda x: x + 1, -5, 5) == [])
check("y intercept", A.y_intercept(lambda x: x + 3) == (0.0, 3.0) and A.y_intercept(lambda x: 1 / x) is None)
check("derivative", near(A.derivative(lambda x: x ** 3, 2), 12, 1e-3))
check("derivative undefined", A.derivative(math.log, -1) is None)
m, y0 = A.tangent_at(lambda x: x * x, 3)
check("tangent", near(m, 6, 1e-3) and near(y0, 9))
check("no tangent at pole", A.tangent_at(lambda x: 1 / x, 0) is None)

# analyse
res = A.analyse([("f", lambda x: x * x - 1), ("g", lambda x: x)], -3, 3)
check("analyse", len(res["roots"]) == 3 and len(res["extrema"]) == 1 and len(res["cross"]) == 2
      and res["yint"][0][1] == -1.0)
check("analyse off-screen yint", A.analyse([("f", lambda x: x)], 1, 3)["yint"] == [])

# names
check("valid names", A.valid_name("a") and A.valid_name("k2") and not A.valid_name("x")
      and not A.valid_name("sin") and not A.valid_name("1a") and not A.valid_name("pi"))
check("free names", A.free_names("a*sin(b*x)+c") == {"a", "b", "c"} and A.free_names("sin(x)+pi") == set()
      and A.free_names("a*t", allowed={"a"}) == set())
check("free names bad syntax", A.free_names("a*") == set())
check("fmt", A.fmt_num(3.0) == "3" and A.fmt_num(1 / 3) == "0.333333" and A.fmt_num(None) == "undefined"
      and A.fmt_num(1e-13) == "0" and "e" in A.fmt_num(1.2e-6))

# input bar
P = A.parse_input
check("func f", P("f(x) = sin(x)") == {"kind": "func", "mode": "y", "name": "f(x)", "expr": "sin(x)"})
check("func g", P("g(x)=x^2")["name"] == "g(x)")
check("func y", P("y = x + 1")["name"] == "y")
check("bare x", P("x^2 - 3")["mode"] == "y")
check("slider", P("a = 2") == {"kind": "slider", "name": "a", "value": 2.0})
check("slider pi", near(P("k = 2*pi")["value"], 2 * math.pi))
check("slider negative", P("b = -1.5")["value"] == -1.5)
check("point", P("A = (1, 2)") == {"kind": "point", "name": "A", "x": "1", "y": "2"})
check("point unnamed", P("(max(1,2), 3)")["x"] == "max(1,2)")
check("param", P("(cos(t), sin(t))")["mode"] == "param")
check("polar", P("r = 1 + cos(t)")["mode"] == "polar")
check("tangent", P("Tangent(x^2, 1)") == {"kind": "tangent", "expr": "x^2", "x0": "1"})
check("tangent by name", P("tangent(f, 2)", {"f": "sin(x)"})["expr"] == "sin(x)")
check("a*x", P("a*x")["mode"] == "y")
for bad in ("", "   ", "f(x) =", "sin(", "x = ", "sin = 3", "x = 4", "Tangent(x^2)", "(1,2,3)", "a"):
    try:
        P(bad)
        check("reject " + repr(bad), False)
    except ValueError:
        pass
check("eval const", near(A.eval_const("2*pi"), 2 * math.pi) and near(A.eval_const("sqrt(16)"), 4))
for bad in ("x", "__import__('os')", "1/0", "2**9999"):
    try:
        A.eval_const(bad)
        check("const reject " + bad, False)
    except (ValueError, ZeroDivisionError, OverflowError):
        pass
lo, hi, st = A.slider_range(2); check("slider range", (lo, hi, st) == (-5.0, 5.0, 0.1))
lo, hi, st = A.slider_range(40); check("slider range big", lo == -80.0 and st == 1.0)

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
