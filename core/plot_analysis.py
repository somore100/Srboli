# core/plot_analysis.py - the maths behind the Function Plotter's GeoGebra-style tools.
# No Kivy. Everything takes plain callables f(x) -> float, so it is easy to test.
#
#   roots / extrema / intersections / derivative / tangent   numeric analysis
#   parse_input                                              the single input bar
import ast
import math
import re

RESERVED = {"x", "t", "pi", "e", "tau", "y", "r", "where"}
FUNC_NAMES = {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "exp",
              "log", "log10", "log2", "sqrt", "cbrt", "abs", "floor", "ceil", "round", "min",
              "max", "sign", "atan2", "hypot", "where", "tangent"}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,15}$")


def valid_name(name):
    """A name a slider or point may use (not x/t/pi/e/function names)."""
    return bool(NAME_RE.match(name or "")) and name not in RESERVED and name not in FUNC_NAMES


def free_names(text, allowed=()):
    """Names used in an expression that are not constants, functions or `allowed`."""
    try:
        tree = ast.parse((text or "").strip().replace("^", "**"), mode="eval")
    except SyntaxError:
        return set()
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called
    return {n for n in names if n not in RESERVED and n not in FUNC_NAMES and n not in allowed}


# ---------------------------------------------------------------- numbers
def fmt_num(v, digits=6):
    """A short, readable number: 3, -0.5, 1.41421, 1.2e-07."""
    if v is None or not math.isfinite(v):
        return "undefined"
    if abs(v) < 1e-12:
        return "0"
    if abs(v) >= 1e7 or abs(v) < 1e-4:
        return f"{v:.{max(digits - 3, 2)}e}"
    s = f"{v:.{digits}g}"
    return s


def safe(fn, x):
    try:
        v = fn(x)
    except Exception:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def derivative(fn, x):
    """Numeric derivative (five-point stencil), or None where f is undefined."""
    h = 1e-4 * max(1.0, abs(x))
    a, b, c, d = (safe(fn, x + k * h) for k in (-2, -1, 1, 2))
    if None in (a, b, c, d):
        return None
    return (a - 8 * b + 8 * c - d) / (12 * h)


def tangent_at(fn, x0):
    """(slope, y0) of the tangent at x0, or None if f is not differentiable there."""
    y0 = safe(fn, x0)
    m = derivative(fn, x0)
    if y0 is None or m is None or abs(m) > 1e9:
        return None
    return m, y0


def _dedupe(pts, eps):
    out = []
    for p in sorted(pts, key=lambda q: q[0]):
        if not out or abs(p[0] - out[-1][0]) > eps:
            out.append(p)
    return out


def _bisect(g, a, b, ga, gb, iters=80):
    for _ in range(iters):
        m = (a + b) / 2
        gm = safe(g, m)
        if gm is None:
            return None
        if gm == 0:
            return m
        if (ga < 0) == (gm < 0):
            a, ga = m, gm
        else:
            b, gb = m, gm
        if b - a < 1e-14 * max(1.0, abs(a)):
            break
    return (a + b) / 2


def roots(fn, lo, hi, n=600, tol=1e-5):
    """x values in [lo, hi] where f crosses zero (poles such as 1/x are ignored)."""
    if not (hi > lo):
        return []
    step = (hi - lo) / n
    xs = [lo + i * step for i in range(n + 1)]
    ys = [safe(fn, x) for x in xs]
    out = []
    for i in range(n):
        a, b = ys[i], ys[i + 1]
        if a is None or b is None:
            continue
        if a == 0:
            out.append(xs[i])
        elif a * b < 0:
            r = _bisect(fn, xs[i], xs[i + 1], a, b)
            if r is not None:
                fr = safe(fn, r)
                if fr is not None and abs(fr) <= tol:
                    out.append(r)
    if ys[-1] == 0:
        out.append(xs[-1])
    # touching roots (x^2): a very flat minimum of |f| that reaches zero
    for i in range(1, n):
        a, b, c = ys[i - 1], ys[i], ys[i + 1]
        if None in (a, b, c) or b == 0:
            continue
        if abs(b) < abs(a) and abs(b) <= abs(c) and a * b > 0 and b * c > 0:
            lo_, hi_ = xs[i - 1], xs[i + 1]
            for _ in range(60):
                m1, m2 = lo_ + (hi_ - lo_) / 3, hi_ - (hi_ - lo_) / 3
                f1, f2 = safe(fn, m1), safe(fn, m2)
                if f1 is None or f2 is None:
                    break
                if abs(f1) < abs(f2):
                    hi_ = m2
                else:
                    lo_ = m1
            xm = (lo_ + hi_) / 2
            fm = safe(fn, xm)
            if fm is not None and abs(fm) <= 1e-9:
                out.append(xm)
    pts = _dedupe([(x, 0.0) for x in out], step * 0.5)
    return [p[0] for p in pts]


def extrema(fn, lo, hi, n=600):
    """Local minima and maxima in (lo, hi) as [(x, y, "min"|"max")]."""
    if not (hi > lo):
        return []
    step = (hi - lo) / n
    xs = [lo + i * step for i in range(n + 1)]
    ys = [safe(fn, x) for x in xs]
    out = []
    for i in range(1, n):
        a, b, c = ys[i - 1], ys[i], ys[i + 1]
        if None in (a, b, c):
            continue
        is_max = b > a and b >= c and (b > c or (i + 1 < n and (ys[i + 2] is not None and ys[i + 2] < c)))
        is_min = b < a and b <= c and (b < c or (i + 1 < n and (ys[i + 2] is not None and ys[i + 2] > c)))
        if not (is_max or is_min):
            continue
        sign = -1.0 if is_max else 1.0       # minimise sign * f
        l, r = xs[i - 1], xs[i + 1]
        for _ in range(70):
            m1, m2 = l + (r - l) / 3, r - (r - l) / 3
            f1, f2 = safe(fn, m1), safe(fn, m2)
            if f1 is None or f2 is None:
                break
            if sign * f1 < sign * f2:
                r = m2
            else:
                l = m1
        x = (l + r) / 2
        y = safe(fn, x)
        if y is None:
            continue
        d = max(abs(hi - lo) * 1e-7, 1e-9)
        ya, yb = safe(fn, x - d), safe(fn, x + d)
        if ya is None or yb is None or abs(ya - y) > 1e-3 * (1 + abs(y)) or abs(yb - y) > 1e-3 * (1 + abs(y)):
            continue                     # a jump or a pole, not a real extremum
        if abs(y - ya) < 1e-13 and abs(y - yb) < 1e-13:
            continue                     # a flat stretch
        out.append((x, y, "max" if is_max else "min"))
    pts = _dedupe(out, step * 1.5)
    return pts


def intersections(f, g, lo, hi, n=400):
    """[(x, y)] where the two graphs cross."""
    def h(x):
        a, b = safe(f, x), safe(g, x)
        return None if a is None or b is None else a - b
    out = []
    for x in roots(h, lo, hi, n):
        y = safe(f, x)
        if y is not None:
            out.append((x, y))
    return out


def y_intercept(fn):
    y = safe(fn, 0.0)
    return None if y is None else (0.0, y)


def analyse(funcs, lo, hi, intersect=True, max_pairs=15):
    """funcs: [(label, fn)]. Returns {"roots": [(x, 0, label)], "extrema": [(x, y, kind, label)],
    "yint": [(0, y, label)], "cross": [(x, y, labelA, labelB)]}."""
    res = {"roots": [], "extrema": [], "yint": [], "cross": []}
    for label, fn in funcs:
        res["roots"] += [(x, 0.0, label) for x in roots(fn, lo, hi)]
        res["extrema"] += [(x, y, k, label) for x, y, k in extrema(fn, lo, hi)]
        if lo <= 0 <= hi:
            p = y_intercept(fn)
            if p:
                res["yint"].append((0.0, p[1], label))
    if intersect:
        pairs = 0
        for i in range(len(funcs)):
            for j in range(i + 1, len(funcs)):
                if pairs >= max_pairs:
                    return res
                pairs += 1
                res["cross"] += [(x, y, funcs[i][0], funcs[j][0])
                                 for x, y in intersections(funcs[i][1], funcs[j][1], lo, hi)]
    return res


# ---------------------------------------------------------------- the input bar
def _split_top(text, sep=","):
    """Split on `sep` outside any brackets."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _check_expr(text, var):
    """Syntax check only; raises ValueError."""
    t = text.strip().replace("^", "**")
    if not t:
        raise ValueError("Empty expression.")
    try:
        ast.parse(t, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Syntax error: {e.msg}")
    return text.strip()


def _is_number_expr(text):
    t = text.strip().replace("^", "**")
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError:
        return False
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - {"pi", "e", "tau"}
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return not (names - calls)


def parse_input(text, functions=None):
    """Turn what was typed in the input bar into an object description.
    `functions` maps a function name (f, g) to its expression, so Tangent(f, 1) works.
    Returns one of
      {"kind": "func", "mode": "y",     "name", "expr"}
      {"kind": "func", "mode": "polar", "name", "expr"}
      {"kind": "func", "mode": "param", "name", "expr", "expr2"}
      {"kind": "slider", "name", "value"}
      {"kind": "point", "name", "x", "y"}
      {"kind": "tangent", "expr", "x0"}
    Raises ValueError with a readable message."""
    functions = functions or {}
    s = (text or "").strip()
    if not s:
        raise ValueError("Type something, e.g. f(x) = sin(x), a = 2, A = (1, 2).")
    m = re.match(r"^tangent\s*\((.*)\)$", s, re.I)
    if m:
        parts = _split_top(m.group(1))
        if len(parts) != 2:
            raise ValueError("Use Tangent(function, x). Example: Tangent(x^2, 1).")
        fx, x0 = parts[0].strip(), parts[1].strip()
        fx = functions.get(fx, fx)
        _check_expr(fx, "x")
        _check_expr(x0, "x")
        return {"kind": "tangent", "expr": fx, "x0": x0}

    name = None
    m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*(\(\s*[xt]\s*\))?\s*=(?!=)\s*(.+)$", s)
    if m:
        name, arg, rhs = m.group(1), m.group(2), m.group(3).strip()
    else:
        rhs = s

    # a point (x, y) or a parametric curve (cos(t), sin(t))
    if rhs.startswith("(") and rhs.endswith(")"):
        inner = _split_top(rhs[1:-1])
        if len(inner) == 2:
            a, b = inner[0].strip(), inner[1].strip()
            _check_expr(a, "x")
            _check_expr(b, "x")
            if "t" in free_names_raw(a) | free_names_raw(b):
                return {"kind": "func", "mode": "param", "name": name or "x,y(t)", "expr": a, "expr2": b}
            if name is not None and not valid_name(name):
                raise ValueError(f"'{name}' can't be used as a point name.")
            return {"kind": "point", "name": name or "", "x": a, "y": b}
        if len(inner) > 2:
            raise ValueError("A point has two coordinates: (x, y).")

    _check_expr(rhs, "x")
    raw = free_names_raw(rhs)
    has_eq = m is not None
    if has_eq and name.lower() not in ("y", "r") and arg is None and _is_number_expr(rhs):
        if not valid_name(name):
            raise ValueError(f"'{name}' can't be used as a slider name.")
        try:
            v = eval_const(rhs, {"pi": math.pi, "e": math.e, "tau": math.tau})
        except ValueError:
            raise ValueError("That is not a number.")
        return {"kind": "slider", "name": name, "value": v}
    if has_eq and (name.lower() == "r" or (arg and "t" in arg)):
        return {"kind": "func", "mode": "polar", "name": "r(\u03b8)", "expr": rhs}
    if has_eq:
        return {"kind": "func", "mode": "y", "name": "y" if name.lower() == "y" else f"{name}(x)",
                "expr": rhs}
    if "t" in raw and "x" not in raw:
        return {"kind": "func", "mode": "polar", "name": "r(\u03b8)", "expr": rhs}
    if raw and "x" not in raw:
        raise ValueError(f"I don't know '{sorted(raw)[0]}'. Write {sorted(raw)[0]} = 2 to make a slider.")
    return {"kind": "func", "mode": "y", "name": "f(x)", "expr": rhs}


def free_names_raw(text):
    """Every variable-like name in an expression (including x and t), minus constants."""
    try:
        tree = ast.parse((text or "").strip().replace("^", "**"), mode="eval")
    except SyntaxError:
        return set()
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called - {"pi", "e", "tau"}


def eval_const(text, consts=None):
    """Evaluate a constant arithmetic expression safely (numbers, + - * / ** and pi/e/tau/functions)."""
    consts = consts or {"pi": math.pi, "e": math.e, "tau": math.tau}
    import operator
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}
    funcs = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
             "log": math.log, "abs": abs}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name) and n.id in consts:
            return consts[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("exponent too large")
            return ops[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return -ev(n.operand) if isinstance(n.op, ast.USub) else ev(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs and len(n.args) == 1:
            return funcs[n.func.id](ev(n.args[0]))
        raise ValueError("not a constant")

    try:
        v = ev(ast.parse(text.strip().replace("^", "**"), mode="eval"))
    except (SyntaxError, TypeError):
        raise ValueError("not a constant")
    if isinstance(v, complex) or not math.isfinite(v):
        raise ValueError("not a finite number")
    return v


def slider_range(value):
    """A sensible (min, max, step) for a new slider holding `value`."""
    span = max(5.0, float(math.ceil(abs(value) * 2)))
    return -span, span, (0.1 if span <= 20 else 1.0)
