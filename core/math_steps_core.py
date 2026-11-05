# core/math_steps_core.py - Math Steps engine (Kivy-free, no dependencies).
#
# The student types an equation or an expression and then solves it one line
# at a time; this module checks every line.
#
#   * CHECKING is by equivalence, not by rule matching, so any valid route is
#     accepted: an expression step must have the same value as the line above,
#     an equation step must have the same solutions (the two sides' difference
#     may only change by a non-zero constant factor).
#   * EXPLAINING comes second: an accepted step is named ("subtracted 3 from
#     both sides"), a wrong one gets a likely cause ("a sign looks wrong").
#   * The rule-based SOLVER gives the hints and the full solution. It covers
#     linear and quadratic equations in one variable (factoring, square root,
#     quadratic formula) and simplifying expressions; steps for other
#     polynomials are still checked, just not solved.
#   * Solutions are written as 'x = 2 or x = -2', 'x = (3 ± sqrt(5))/2' or
#     'no real solutions'. Such lines are compared with the line above by
#     their set of real solutions.
#
# Numbers are exact fractions. Expressions are polynomials with fractional
# coefficients; division only by a plain number, powers only by whole numbers.
import math
import re
from fractions import Fraction

MAX_POWER = 12


class MathError(ValueError):
    """The text can't be read as maths."""


class NotSupported(MathError):
    """Valid maths this version doesn't handle (yet)."""


# ── parsing ───────────────────────────────────────────────────────────────
_TOKEN = re.compile(r"\s*(\d+\.\d+|\d+|\.\d+|sqrt|√|[A-Za-z]|[-+*/^()=]|\S)")


def _tokens(text):
    text = (text.replace("−", "-").replace("–", "-")
            .replace("×", "*").replace("·", "*").replace("÷", "/")
            .replace("**", "^"))
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            break
        tok = m.group(1)
        pos = m.end()
        if re.fullmatch(r"\d+\.\d+|\d+|\.\d+", tok):
            out.append(("num", Fraction(tok)))
        elif tok in ("sqrt", "\u221a"):
            out.append(("func", "sqrt"))
        elif tok.isalpha() and len(tok) == 1:
            out.append(("var", tok))
        elif tok in "+-*/^()=":
            out.append(("op", tok))
        else:
            raise MathError(f"I don't understand '{tok}'.")
    return out


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def op(self, ch):
        return self.peek() == ("op", ch)

    def expr(self):
        node = self.term()
        while self.op("+") or self.op("-"):
            o = self.take()[1]
            rhs = self.term()
            node = ("add" if o == "+" else "sub", node, rhs)
        return node

    def term(self):
        node = self.unary()
        while True:
            if self.op("*") or self.op("/"):
                o = self.take()[1]
                node = ("mul" if o == "*" else "div", node, self.unary())
            elif self.peek()[0] in ("var", "func") or self.op("("):   # 2x, 3(x+1), 2sqrt(5)
                node = ("mul", node, self.unary())
            else:
                return node

    def unary(self):
        if self.op("-"):
            self.take()
            return ("neg", self.unary())
        if self.op("+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        base = self.atom()
        if self.op("^"):
            self.take()
            neg = self.op("-")
            if neg:
                self.take()
            exp = self.power()
            base = ("pow", base, ("neg", exp) if neg else exp)
        return base

    def atom(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", val)
        if kind == "var":
            return ("var", val)
        if kind == "func":                          # sqrt(5), sqrt 5
            if self.op("("):
                self.take()
                arg = self.expr()
                if self.take() != ("op", ")"):
                    raise MathError("A bracket is not closed.")
            else:
                arg = self.atom()
            return ("sqrt", arg)
        if (kind, val) == ("op", "("):
            node = self.expr()
            if self.take() != ("op", ")"):
                raise MathError("A bracket is not closed.")
            return node
        if kind is None:
            raise MathError("The expression ends too early.")
        raise MathError(f"Unexpected '{val}'.")


def parse_expr(text):
    toks = _tokens(text)
    if not toks:
        raise MathError("Nothing to check - type an expression.")
    p = _Parser(toks)
    node = p.expr()
    if p.i < len(toks):
        kind, val = toks[p.i]
        raise MathError(f"Unexpected '{val}'.")
    return node


# ── polynomials with exact fractions ──────────────────────────────────────
class Poly:
    """Sum of monomials. A monomial is a sorted tuple of (variable, power)."""

    def __init__(self, terms=None):
        self.t = {m: c for m, c in (terms or {}).items() if c != 0}

    @staticmethod
    def const(c):
        return Poly({(): Fraction(c)})

    @staticmethod
    def var(name):
        return Poly({((name, 1),): Fraction(1)})

    def __add__(self, o):
        t = dict(self.t)
        for m, c in o.t.items():
            t[m] = t.get(m, 0) + c
        return Poly(t)

    def __neg__(self):
        return Poly({m: -c for m, c in self.t.items()})

    def __sub__(self, o):
        return self + (-o)

    def scale(self, k):
        return Poly({m: c * k for m, c in self.t.items()})

    def __mul__(self, o):
        t = {}
        for m1, c1 in self.t.items():
            for m2, c2 in o.t.items():
                e = dict(m1)
                for v, p in m2:
                    e[v] = e.get(v, 0) + p
                m = tuple(sorted(e.items()))
                t[m] = t.get(m, 0) + c1 * c2
        return Poly(t)

    def power(self, n):
        out = Poly.const(1)
        for _ in range(n):
            out = out * self
        return out

    def __eq__(self, o):
        return isinstance(o, Poly) and self.t == o.t

    def __hash__(self):
        return hash(frozenset(self.t.items()))

    def is_zero(self):
        return not self.t

    def is_const(self):
        return all(m == () for m in self.t)

    def value(self):
        return self.t.get((), Fraction(0))

    def variables(self):
        return sorted({v for m in self.t for v, _ in m})

    def degree(self):
        return max((sum(p for _, p in m) for m in self.t), default=0)

    def coef(self, mono):
        return self.t.get(mono, Fraction(0))

    def without(self, mono):
        return Poly({m: c for m, c in self.t.items() if m != mono})


def to_poly(node):
    kind = node[0]
    if kind == "num":
        return Poly.const(node[1])
    if kind == "var":
        return Poly.var(node[1])
    if kind == "neg":
        return -to_poly(node[1])
    if kind == "add":
        return to_poly(node[1]) + to_poly(node[2])
    if kind == "sub":
        return to_poly(node[1]) - to_poly(node[2])
    if kind == "mul":
        return to_poly(node[1]) * to_poly(node[2])
    if kind == "div":
        den = to_poly(node[2])
        if not den.is_const():
            raise NotSupported("Dividing by an expression with a variable "
                               "isn't supported yet.")
        if den.value() == 0:
            raise MathError("Division by zero.")
        return to_poly(node[1]).scale(1 / den.value())
    if kind == "pow":
        base, exp = to_poly(node[1]), to_poly(node[2])
        if not exp.is_const() or exp.value().denominator != 1 or exp.value() < 0:
            raise NotSupported("Only whole-number powers (0, 1, 2, ...) are "
                               "supported yet.")
        n = int(exp.value())
        if n > MAX_POWER:
            raise NotSupported(f"Powers above {MAX_POWER} are not supported.")
        return base.power(n)
    if kind == "sqrt":
        arg = to_poly(node[1])
        if not arg.is_const():
            raise NotSupported("Square roots of expressions with a variable "
                               "aren't supported.")
        v = arg.value()
        if v < 0:
            raise MathError("The square root of a negative number isn't real.")
        n, d = math.isqrt(v.numerator), math.isqrt(v.denominator)
        if n * n == v.numerator and d * d == v.denominator:
            return Poly.const(Fraction(n, d))
        raise NotSupported("SURD")
    raise MathError("Can't read that.")


def ast_vars(node):
    if node[0] == "var":
        return {node[1]}
    return set().union(*(ast_vars(c) for c in node[1:] if isinstance(c, tuple))) \
        if len(node) > 1 else set()


def eval_num(node):
    """Value of variable-free maths as a float (square roots allowed)."""
    k = node[0]
    if k == "num":
        return float(node[1])
    if k == "var":
        raise MathError("A variable can't be here.")
    if k == "neg":
        return -eval_num(node[1])
    a = eval_num(node[1])
    if k == "sqrt":
        if a < 0:
            raise MathError("The square root of a negative number isn't real.")
        return math.sqrt(a)
    b = eval_num(node[2])
    if k == "add":
        return a + b
    if k == "sub":
        return a - b
    if k == "mul":
        return a * b
    if k == "div":
        if b == 0:
            raise MathError("Division by zero.")
        return a / b
    if k == "pow":
        if abs(b) > 50:
            raise NotSupported("That power is too large.")
        try:
            return a ** b
        except (ZeroDivisionError, OverflowError):
            raise MathError("Can't work that out.")
    raise MathError("Can't read that.")


# ── writing maths back out ────────────────────────────────────────────────
def _num(c):
    c = abs(c)
    return str(c.numerator) if c.denominator == 1 else f"{c.numerator}/{c.denominator}"


def _mono(m):
    return "".join(v if p == 1 else f"{v}^{p}" for v, p in m)


def mono_name(m):
    return _mono(m) if m else "number"


def fmt(p):
    """Canonical text: highest powers first, 'x', '-x', '3x', '(1/2)x', '7/2'."""
    if p.is_zero():
        return "0"
    terms = sorted(p.t.items(),
                   key=lambda mc: (-sum(e for _, e in mc[0]), _mono(mc[0])))
    out = ""
    for i, (m, c) in enumerate(terms):
        if m == ():
            body = _num(c)
        else:
            body = _mono(m)
            if abs(c) != 1:
                body = (_num(c) if c.denominator == 1 else f"({_num(c)})") + body
        if i == 0:
            out = ("-" if c < 0 else "") + body
        else:
            out += (" - " if c < 0 else " + ") + body
    return out


def fmt_num(c):
    return ("-" if c < 0 else "") + _num(c)


# ── is this expression already in simplest form? ──────────────────────────
def _flatten_terms(node, out):
    """Terms of a left-to-right sum. A bracketed sum on the right (a + (b + c),
    a - (b + c)) stays one node so it counts as 'brackets still to expand'."""
    if node[0] in ("add", "sub"):
        _flatten_terms(node[1], out)
        out.append(node[2])
    else:
        out.append(node)


def _monomial(node):
    """(monomial key, numeric factors) if node is one tidy term, else None."""
    k = node[0]
    if k == "num":
        return (), 1
    if k == "var":
        return ((node[1], 1),), 0
    if k == "neg":
        return _monomial(node[1])
    if k == "pow":
        if node[1][0] == "var" and node[2][0] == "num" \
                and node[2][1].denominator == 1 and node[2][1] >= 2:
            return ((node[1][1], int(node[2][1])),), 0
        return None
    if k == "div":
        top = node[1]
        while top[0] == "neg":                   # -3/2 parses as (-3)/2
            top = top[1]
        if top[0] == "num" and node[2][0] == "num":
            a, b = top[1], node[2][1]
            if b in (0, 1) or a.denominator != 1 or b.denominator != 1:
                return None
            f = Fraction(a, b)
            return ((), 1) if f.denominator == b and f.numerator == a else None
        if node[2][0] == "num" and node[2][1] not in (0, 1):
            inner = _monomial(node[1])
            if inner and inner[0] != () and inner[1] == 0:
                return inner[0], 1
        return None
    if k == "mul":
        a, b = _monomial(node[1]), _monomial(node[2])
        if not a or not b:
            return None
        if {v for v, _ in a[0]} & {v for v, _ in b[0]}:
            return None                           # x*x is x^2: not tidy yet
        key = tuple(sorted(dict(a[0] + b[0]).items()))
        return key, a[1] + b[1]
    return None


def is_simplified(node):
    """Sum of distinct tidy terms: no brackets to expand, no like terms to
    combine, at most one number in front of each term."""
    terms = []
    _flatten_terms(node, terms)
    seen = set()
    for t in terms:
        mono = _monomial(t)
        if mono is None:
            return False
        key, nums = mono
        if nums > 1 or key in seen:
            return False
        if t[0] in ("mul",):                      # 1x, 0x: explicit 1 or 0
            for part in (t[1], t[2]):
                if part[0] == "num" and part[1] in (0, 1):
                    return False
        if key == () and t[0] == "num" and len(terms) > 1 and t[1] == 0:
            return False
        seen.add(key)
    return True


# ── one line of work ──────────────────────────────────────────────────────
class Line:
    """A parsed line: an expression or an equation."""

    def __init__(self, text):
        self.text = " ".join(text.split())
        if self.text.count("=") > 1:
            raise MathError("Only one '=' is allowed.")
        if "=" in self.text:
            left, right = self.text.split("=")
            if not left.strip() or not right.strip():
                raise MathError("An equation needs something on both sides "
                                "of '='.")
            self.kind = "equation"
            self.ast_l, self.ast_r = parse_expr(left), parse_expr(right)
            self.L, self.R = to_poly(self.ast_l), to_poly(self.ast_r)
            self.P = self.L - self.R
        else:
            self.kind = "expression"
            self.ast = parse_expr(self.text)
            self.P = to_poly(self.ast)
            self.L, self.R = self.P, None

    def variables(self):
        return sorted(set(self.L.variables())
                      | set(self.R.variables() if self.R else []))

    def tidy(self):
        if self.kind == "equation":
            return is_simplified(self.ast_l) and is_simplified(self.ast_r)
        return is_simplified(self.ast)

    def brackets(self):
        return self.text.count("(")


def proportional(p1, p2):
    """k != 0 with p2 == k * p1 (both zero counts as k = 1), else None."""
    if p1.is_zero() or p2.is_zero():
        return Fraction(1) if p1.is_zero() and p2.is_zero() else None
    if set(p1.t) != set(p2.t):
        return None
    m = next(iter(p1.t))
    k = p2.t[m] / p1.t[m]
    return k if p2 == p1.scale(k) else None


# ── real solutions of equations ───────────────────────────────────────────
ALL = "all"                      # a clause that is true for every value


def _isqrt_exact(n):
    r = math.isqrt(n)
    return r if r * r == n else None


def _squarefree(n):
    """(s, m) with n == s*s*m and m square-free."""
    if n > 10 ** 14:
        raise NotSupported("Those numbers are too large for the square-root "
                           "helper.")
    s, m, f = 1, n, 2
    while f * f <= m:
        while m % (f * f) == 0:
            m //= f * f
            s *= f
        f += 1 if f == 2 else 2
    return s, m


def quad_roots_exact(a, b, c):
    """Exact real roots of ax^2+bx+c (a != 0):
    ('none',) | ('rational', r1, r2) | ('surd', P, S, m, Dn) meaning
    x = (P +/- S*sqrt(m)) / Dn with whole numbers and Dn > 0."""
    lcm = 1
    for f in (a, b, c):
        lcm = lcm * f.denominator // math.gcd(lcm, f.denominator)
    A, B, C = int(a * lcm), int(b * lcm), int(c * lcm)
    if A < 0:
        A, B, C = -A, -B, -C
    D = B * B - 4 * A * C
    if D < 0:
        return ("none",)
    r = _isqrt_exact(D)
    if r is not None:
        return ("rational", Fraction(-B - r, 2 * A), Fraction(-B + r, 2 * A))
    sq, m = _squarefree(D)
    P, S, Dn = -B, sq, 2 * A
    g = math.gcd(math.gcd(abs(P), S), Dn)
    return ("surd", P // g, S // g, m, Dn // g)


def surd_texts(P, S, m, Dn):
    """('combined', 'plus', 'minus') spellings of (P +/- S sqrt(m)) / Dn."""
    t = f"sqrt({m})" if S == 1 else f"{S}sqrt({m})"
    den = "" if Dn == 1 else f"/{Dn}"
    if P == 0:
        return f"\u00b1{t}{den}", f"{t}{den}", f"-{t}{den}"
    wrap = (lambda x: x) if Dn == 1 else (lambda x: f"({x})")
    return (wrap(f"{P} \u00b1 {t}") + den, wrap(f"{P} + {t}") + den,
            wrap(f"{P} - {t}") + den)


def poly_roots(p):
    """Sorted real roots (floats) of a one-variable polynomial of degree <= 2,
    or ALL when p is 0."""
    if p.is_zero():
        return ALL
    vs = p.variables()
    if len(vs) > 1:
        raise NotSupported("Solving for several variables isn't supported.")
    deg = p.degree()
    if deg == 0:
        return []
    if deg > 2:
        raise NotSupported("Solving is supported up to degree 2 (quadratics).")
    v = vs[0]
    c, b, a = (p.coef(()), p.coef(((v, 1),)), p.coef(((v, 2),)))
    if deg == 1:
        return [float(-c / b)]
    D = b * b - 4 * a * c
    if D < 0:
        return []
    r = math.sqrt(D)
    out = sorted({(-float(b) - r) / (2 * float(a)), (-float(b) + r) / (2 * float(a))})
    return [out[0]] if len(out) == 2 and abs(out[0] - out[1]) < 1e-12 else out


def same_roots(r1, r2):
    if r1 == ALL or r2 == ALL:
        return r1 == r2
    return len(r1) == len(r2) and all(
        abs(x - y) <= 1e-9 * max(1.0, abs(x)) for x, y in zip(r1, r2))


_NOSOL = re.compile(r"^\s*(no\s+(real\s+)?(solutions?|roots?)|none)\s*\.?\s*$", re.I)
_LISTY = re.compile(r"\u00b1|\+/-|\+-|\bor\b|;|,\s|sqrt|\u221a", re.I)


def _expand_pm(part):
    n = part.count("\u00b1")
    if n == 0:
        return [part]
    if n > 2:
        raise MathError("Use at most two \u00b1 signs in one solution.")
    out = [part]
    for _ in range(n):
        out = [v.replace("\u00b1", sign, 1) for v in out for sign in ("+", "-")]
    return out


class Sol:
    """A line that lists solutions: 'x = 2 or x = -2', 'x = \u00b13',
    'x = (3 \u00b1 sqrt(5))/2' or 'no real solutions'."""
    kind = "solset"

    def __init__(self, text):
        self.text = " ".join(text.split())
        self.nosol = bool(_NOSOL.match(self.text))
        self.clauses, self.vars, self.roots = [], set(), []
        self.P = None
        if self.nosol:
            return
        t = self.text.replace("+/-", "\u00b1").replace("+-", "\u00b1")
        parts = [x.strip() for x in re.split(r"\s+or\s+|;|,\s", t, flags=re.I)
                 if x.strip()]
        if not parts:
            raise MathError("Write the solutions like  x = 2 or x = -3.")
        roots = []
        for part in parts:
            for variant in _expand_pm(part):
                info = self._clause(variant)
                self.clauses.append(info)
                self.vars |= info["vars"]
                if info["roots"] == ALL:
                    raise NotSupported("A clause that is always true can't be "
                                       "compared yet.")
                roots += info["roots"]
        if len(self.vars) != 1:
            raise MathError("A solution line should use exactly one variable.")
        self.roots = sorted(roots)
        self.roots = [r for i, r in enumerate(self.roots)
                      if i == 0 or abs(r - self.roots[i - 1]) > 1e-9]

    @staticmethod
    def _clause(variant):
        if variant.count("=") != 1:
            raise MathError("Each solution needs exactly one '=', like x = 2.")
        left, right = variant.split("=")
        if not left.strip() or not right.strip():
            raise MathError("Each solution needs something on both sides of '='.")
        al, ar = parse_expr(left), parse_expr(right)
        vs = ast_vars(al) | ast_vars(ar)
        if not vs:
            raise MathError("A solution needs the variable, like x = 2.")
        info = {"text": variant, "vars": vs, "iso": False, "simple": False,
                "rhs": "", "roots": []}
        try:
            P = to_poly(al) - to_poly(ar)
            info["roots"] = poly_roots(P)
            other = None
            if al[0] == "var" and not ast_vars(ar):
                other = ar
            elif ar[0] == "var" and not ast_vars(al):
                other = al
            if other is not None:
                info["iso"] = True
                info["simple"] = is_simplified(other)
                info["rhs"] = (right if other is ar else left).replace(" ", "").lstrip("+")
        except NotSupported as e:
            if str(e) != "SURD":
                raise
            if al[0] == "var" and not ast_vars(ar):
                info.update(roots=[eval_num(ar)], iso=True,
                            rhs=right.replace(" ", "").lstrip("+"))
            elif ar[0] == "var" and not ast_vars(al):
                info.update(roots=[eval_num(al)], iso=True,
                            rhs=left.replace(" ", "").lstrip("+"))
            else:
                raise NotSupported("With square roots, write the answer as "
                                   "x = ...")
        return info

    def variables(self):
        return sorted(self.vars)

    def solved_text(self, canon=()):
        """The outcome if every solution is written out in simplest form."""
        if self.nosol:
            return "no real solutions"
        want = {c.replace(" ", "") for c in canon}
        if len(self.clauses) != len(self.roots):
            return ""
        for c in self.clauses:
            if not c["iso"] or not (c["simple"] or c["rhs"] in want):
                return ""
        return self.text


def parse_line(text):
    """A Line (expression / equation) or a Sol (list of solutions)."""
    if _NOSOL.match(text) or ("=" in text and _LISTY.search(text)):
        return Sol(text)
    return Line(text)


def line_roots(line):
    if line.kind == "solset":
        return line.roots
    vs = line.variables()
    if len(vs) != 1:
        raise NotSupported("I can only compare solutions of one-variable "
                           "equations.")
    return poly_roots(line.P)


def canon_for(line):
    """How the final answer must be spelled when it has a square root
    ((combined, plus, minus) texts), else ()."""
    if line.kind != "equation" or len(line.variables()) != 1 or line.P.degree() != 2:
        return ()
    v = line.variables()[0]
    P = line.P
    info = quad_roots_exact(P.coef(((v, 2),)), P.coef(((v, 1),)), P.coef(()))
    return surd_texts(*info[1:]) if info[0] == "surd" else ()


# ── naming an accepted step ───────────────────────────────────────────────
def _op_phrase(d):
    """'added 3' / 'subtracted 2x' for a poly d added to both sides."""
    first = sorted(d.t.items(), key=lambda mc: (-sum(e for _, e in mc[0]),
                                                _mono(mc[0])))[0][1]
    return ("added " + fmt(d)) if first > 0 else ("subtracted " + fmt(-d))


def name_step(a, b):
    """What the student did from line a to line b (both already known to be
    equivalent). Returns a short phrase."""
    if a.kind == "expression":
        if a.text.replace(" ", "") == b.text.replace(" ", ""):
            return "no change"
        if b.brackets() < a.brackets():
            return "expanded the brackets"
        if b.brackets() > a.brackets():
            return "factorised"
        return "combined like terms" if b.tidy() else "simplified"
    if a.L == b.L and a.R == b.R:
        if a.text.replace(" ", "") == b.text.replace(" ", ""):
            return "no change"
        if b.brackets() < a.brackets():
            return "expanded the brackets"
        if b.brackets() > a.brackets():
            return "factorised"
        return "combined like terms" if b.tidy() else "simplified"
    if a.L == b.R and a.R == b.L:
        return "swapped the two sides"
    dl, dr = b.L - a.L, b.R - a.R
    if dl == dr and not dl.is_zero():
        return _op_phrase(dl) + " on both sides"
    base, scaled = (a.L, b.L) if not a.L.is_zero() else (a.R, b.R)
    c = proportional(base, scaled)
    if c is not None and c != 1 and b.L == a.L.scale(c) and b.R == a.R.scale(c):
        if abs(c.numerator) == 1 and c.denominator > 1:
            return f"divided both sides by {fmt_num(1 / c)}"
        return f"multiplied both sides by {fmt_num(c)}"
    return "made several moves at once"


# ── why a step is wrong ───────────────────────────────────────────────────
def diagnose(a, b):
    """A friendly reason line b does not follow from line a."""
    if a.kind == "equation":
        dl, dr = b.L - a.L, b.R - a.R
        if dl == -dr and not dl.is_zero():           # 2x+3=7  ->  2x=7+3
            return (f"You moved {fmt(-dl)} across the '=' - its sign should "
                    "flip when it crosses.")
        for side, name in (("L", "left"), ("R", "right")):   # one term's sign flipped
            old, new = getattr(a, side), getattr(b, side)
            other = "R" if side == "L" else "L"
            if getattr(a, other) == getattr(b, other):
                for mo, c in old.t.items():
                    if new == old - Poly({mo: 2 * c}):
                        return (f"A sign looks wrong on the {mono_name(mo)} "
                                f"term on the {name} side.")
        cands = {Fraction(1), Fraction(-1)}
        for m, c in a.P.t.items():
            if m in b.P.t:
                cands.add(b.P.t[m] / c)
        best = None
        for k in cands:
            if k == 0:
                continue
            diff = b.P - a.P.scale(k)
            if best is None or len(diff.t) < len(best[1].t):
                best = (k, diff)
        k, diff = best
        want = a.P.scale(k)
    else:
        diff, want = b.P - a.P, a.P
    if len(diff.t) == 1:
        (m, d), = diff.t.items()
        q = want.coef(m)
        if m == ():
            if q != 0 and d == -2 * q:
                return "A sign looks wrong on the plain numbers."
            return "Check the arithmetic on the plain numbers."
        name = mono_name(m)
        if q == 0:
            return f"A {name} term appeared that shouldn't be there."
        if d == -2 * q:
            return f"A sign looks wrong on the {name} term."
        return f"Check the number in front of {name}."
    if a.kind == "equation":
        return ("That doesn't follow from the line above: the two lines "
                "have different solutions.")
    return "That expression isn't equal to the one above."


# ── the rule-based solver (hints and solutions) ───────────────────────────
class Move:
    def __init__(self, rule, hint1, hint2, new_text, why):
        self.rule, self.hint1, self.hint2 = rule, hint1, hint2
        self.new_text, self.why = new_text, why


def solved(line, canon=()):
    """'' while unfinished, else a short outcome text."""
    if line.kind == "solset":
        return line.solved_text(canon)
    if line.kind == "expression":
        return "fully simplified" if line.tidy() else ""
    vs = line.variables()
    if not vs:
        return "true" if line.P.is_zero() else "false"
    if line.P.is_const():
        return ("true for every value" if line.P.is_zero()
                else "no solution")
    v = vs[0]
    x = ((v, 1),)
    one = Poly({x: Fraction(1)})
    if len(vs) == 1 and line.tidy():
        if line.L == one and line.R.is_const():
            return f"{v} = {fmt_num(line.R.value())}"
        if line.R == one and line.L.is_const():
            return f"{v} = {fmt_num(line.L.value())}"
    return ""


def _subtract_text(d, past=False):
    """'Subtract 3 from both sides.' for d taken from both sides."""
    lead = sorted(d.t.items(), key=lambda mc: (-sum(e for _, e in mc[0]),
                                               _mono(mc[0])))[0][1]
    if lead > 0:
        return (f"Subtracted {fmt(d)} on both sides." if past
                else f"Subtract {fmt(d)} from both sides.")
    return (f"Added {fmt(-d)} on both sides." if past
            else f"Add {fmt(-d)} to both sides.")


def _factors(node, power, out):
    k = node[0]
    if k == "mul":
        _factors(node[1], power, out)
        _factors(node[2], power, out)
    elif k == "neg":
        _factors(node[1], power, out)
    elif (k == "pow" and node[2][0] == "num" and node[2][1].denominator == 1
          and node[2][1] >= 1):
        _factors(node[1], power * int(node[2][1]), out)
    else:
        out.append((node, power))


def _zero_product(line):
    """The zero-product step for a factorised  (x - 2)(x + 3) = 0  line."""
    if line.kind != "equation" or not line.R.is_zero():
        return None
    facs = []
    _factors(line.ast_l, 1, facs)
    total, distinct = 0, []
    for node, power in facs:
        p = to_poly(node)
        if p.is_const():
            if p.is_zero():
                return None
            continue
        if p.degree() != 1 or len(p.variables()) != 1:
            return None
        total += power
        if not any(proportional(p, q) is not None for q in distinct):
            distinct.append(p)
    if total < 2:
        return None
    text = " or ".join(f"{fmt(p)} = 0" for p in distinct)
    return Move("zero product",
                "A product is zero only when one of its factors is zero.",
                "Set each factor equal to 0 and join the cases with 'or'.",
                text, "Used the zero-product rule: a product is 0 when one "
                      "of its factors is 0.")


def _square_root_move(v, k):
    if k < 0:
        return Move("no real", "Can a square ever be negative?",
                    "No - so there is no real solution.", "no real solutions",
                    "A square is never negative, so there are no real "
                    "solutions.")
    if k == 0:
        return Move("root", f"Only 0 squared is 0.", f"So {v} = 0.",
                    f"{v} = 0", f"{v}^2 = 0 only when {v} = 0.")
    info = quad_roots_exact(Fraction(1), Fraction(0), -k)
    text = (f"{v} = ±{fmt_num(info[2])}" if info[0] == "rational"
            else f"{v} = {surd_texts(*info[1:])[0]}")
    return Move("square root",
                "Take the square root of both sides - a square root has two signs.",
                f"{v} = ± the square root of the number.", text,
                "Took the square root of both sides (±: both signs).")


def _lead(a):
    if a == 1:
        return ""
    if a == -1:
        return "-"
    return fmt_num(a) if a.denominator == 1 else f"({fmt_num(a)})"


def _par(n):
    return str(int(n)) if n.denominator == 1 and n >= 0 else f"({fmt_num(n)})"


def _quad_move(line, canon):
    v = line.variables()[0]
    x1, x2 = ((v, 1),), ((v, 2),)
    zp = _zero_product(line)
    if zp:
        return zp
    L, R = line.L, line.R
    if not line.tidy():
        return Move("simplify", "Tidy each side first.",
                    "Expand the brackets and combine like terms on each side.",
                    f"{fmt(L)} = {fmt(R)}",
                    "Expanded the brackets and combined like terms.")
    if L == Poly({x2: Fraction(1)}) and R.is_const():
        return _square_root_move(v, R.value())
    if not R.is_zero():
        return Move("standard form",
                    "Bring everything to one side so the other side is 0.",
                    _subtract_text(R), f"{fmt(L - R)} = 0",
                    _subtract_text(R, past=True))
    a, b, c = L.coef(x2), L.coef(x1), L.coef(())
    if b == 0 and c == 0:
        return Move("root", f"{v}^2 times a number is 0 only when {v} is 0.",
                    f"So {v} = 0.", f"{v} = 0", f"The only solution is {v} = 0.")
    if c == 0:
        inner = fmt(Poly({x1: a, (): b}))
        return Move("factorise", f"Take {v} out as a common factor.",
                    f"Write the left side as {v}(...).",
                    f"{v}({inner}) = 0", f"Factorised: {v} is a common factor.")
    if b == 0:
        k = -c / a
        by = f" and divide by {fmt_num(a)}" if a != 1 else ""
        return Move("isolate square", f"Get {v}^2 on its own.",
                    f"Move the number to the other side{by}.",
                    f"{v}^2 = {fmt_num(k)}", f"Got {v}^2 on its own.")
    info = quad_roots_exact(a, b, c)
    if info[0] == "none":
        d = fmt_num(b * b - 4 * a * c)
        return Move("discriminant", "Check the discriminant b^2 - 4ac.",
                    f"Here b^2 - 4ac = {d}, which is negative.",
                    "no real solutions",
                    f"The discriminant b^2 - 4ac = {d} is negative, so there "
                    "are no real solutions.")
    if info[0] == "rational":
        r1, r2 = info[1], info[2]

        def fx(r):
            return fmt(Poly.var(v) - Poly.const(r))
        text = (f"{_lead(a)}({fx(r1)})^2 = 0" if r1 == r2
                else f"{_lead(a)}({fx(r1)})({fx(r2)}) = 0")
        idea = (f"Find two numbers that multiply to {fmt_num(c)} and add to "
                f"{fmt_num(b)}." if a == 1 else
                "Factorise the quadratic (the roots are rational).")
        return Move("factorise", "Factorise the quadratic.", idea, text,
                    "Factorised the quadratic.")
    text = (f"{v} = (-{_par(b)} ± sqrt({_par(b)}^2 - 4*{_par(a)}*{_par(c)}))"
            f" / (2*{_par(a)})")
    return Move("quadratic formula",
                f"Use the quadratic formula {v} = (-b ± sqrt(b^2 - 4ac)) / 2a.",
                f"Here a = {fmt_num(a)}, b = {fmt_num(b)}, c = {fmt_num(c)}.",
                text, "Substituted a, b and c into the quadratic formula.")


def _solset_move(line, canon):
    if line.nosol or line.solved_text(canon):
        return None
    v = line.variables()[0]
    if canon:
        return Move("simplify", "Simplify the square root and tidy the fraction.",
                    "Work out what is under the square root, simplify it, "
                    "then reduce the fraction.", f"{v} = {canon[0]}",
                    "Simplified the square root and the fraction.")
    texts = []
    for c in line.clauses:
        try:
            cl = Line(c["text"])
        except MathError:
            return None
        if cl.P.degree() != 1:
            return None
        r = -cl.P.coef(()) / cl.P.coef(((v, 1),))
        t = f"{v} = {fmt_num(r)}"
        if t not in texts:
            texts.append(t)
    return Move("solve each", "Solve each equation separately.",
                f"Solve each one for {v}.", " or ".join(texts),
                "Solved each equation.")


def next_move(line, canon=()):
    """The solver's next step from `line`, or None when finished / not
    supported (check `solved(line)` and `can_solve(line)`)."""
    if line.kind == "solset":
        return _solset_move(line, canon)
    if solved(line, canon) or not can_solve(line):
        return None
    if line.kind == "expression":
        return Move("simplify", "Tidy the expression.",
                    "Expand the brackets and combine like terms.",
                    fmt(line.P), "Expanded the brackets and combined like terms.")
    if line.P.degree() >= 2:
        return _quad_move(line, canon)
    L, R = line.L, line.R
    v = line.variables()[0]
    x = ((v, 1),)
    if not line.tidy():
        return Move("simplify", "Tidy each side first.",
                    "Expand the brackets and combine like terms on each side.",
                    f"{fmt(L)} = {fmt(R)}",
                    "Expanded the brackets and combined like terms.")
    rv = Poly({x: R.coef(x)})
    if not rv.is_zero():
        what = _op_phrase(-rv)
        verb = "Subtract" if R.coef(x) > 0 else "Add"
        amount = fmt(rv) if R.coef(x) > 0 else fmt(-rv)
        return Move("move variable", f"Get all the {v} terms onto one side.",
                    f"{verb} {amount} from both sides." if verb == "Subtract"
                    else f"Add {amount} to both sides.",
                    f"{fmt(L - rv)} = {fmt(R - rv)}",
                    f"{what.capitalize()} on both sides.")
    c = L.value()
    if c != 0:
        amount = fmt_num(abs(c))
        text = f"{fmt(L - Poly.const(c))} = {fmt(R - Poly.const(c))}"
        if c > 0:
            return Move("move number", "Now get the plain numbers onto the other side.",
                        f"Subtract {amount} from both sides.", text,
                        f"Subtracted {amount} on both sides.")
        return Move("move number", "Now get the plain numbers onto the other side.",
                    f"Add {amount} to both sides.", text,
                    f"Added {amount} on both sides.")
    k = L.coef(x)
    if k != 1:
        if k.numerator == 1:
            do = f"Multiply both sides by {k.denominator}."
            done = f"Multiplied both sides by {k.denominator}."
        else:
            do = f"Divide both sides by {fmt_num(k)}."
            done = f"Divided both sides by {fmt_num(k)}."
        return Move("divide", f"Isolate {v}.", do,
                    f"{v} = {fmt_num(R.value() / k)}" if R.is_const()
                    else f"{v} = {fmt(R.scale(1 / k))}", done)
    return None


def can_solve(line):
    if line.kind == "solset":
        return True
    vs = line.variables()
    if len(vs) > 1:
        return False
    if line.kind == "expression":
        return True
    return line.P.degree() <= 2


def _walk(line, canon):
    steps = []
    for _ in range(30):
        mv = next_move(line, canon)
        if mv is None:
            break
        steps.append((mv.new_text, mv.why))
        line = parse_line(mv.new_text)
    return steps, line


def solution(text):
    """[(line text, explanation)] from the problem to the answer; [] if the
    solver doesn't cover it."""
    line = parse_line(text)
    if line.kind == "solset":
        return []
    canon = canon_for(line)
    steps, end = _walk(line, canon)
    return steps if solved(end, canon) else []


def complexity(text):
    """('Easy' | 'Medium' | 'Hard', number of solving steps or None)."""
    try:
        line = parse_line(text)
    except MathError:
        return ("Hard", None)
    if line.kind == "solset" or not can_solve(line):
        return ("Hard", None)
    n = len(solution(text))
    if not n:
        return ("Hard", None)
    level = "Easy" if n <= 2 else "Medium" if n <= 4 else "Hard"
    return (level, n)


# ── naming and judging lines that list solutions ──────────────────────────
def _is_square_eq(a):
    if a.kind != "equation" or len(a.variables()) != 1:
        return False
    v = a.variables()[0]
    return a.L == Poly({((v, 2),): Fraction(1)}) and a.R.is_const()


def name_any(a, b):
    if a.kind != "solset" and b.kind != "solset":
        if (a.kind == "equation" and _is_square_eq(a)
                and proportional(a.P, b.P) is None):
            return "took the square root of both sides"
        return name_step(a, b)
    if b.nosol:
        return "concluded there are no real solutions"
    if a.kind == "equation":
        if "±" in b.text or "sqrt" in b.text.lower():
            return ("took the square root of both sides" if _is_square_eq(a)
                    else "used the quadratic formula")
        if _zero_product(a):
            return "used the zero-product rule"
        return "found the solutions"
    if b.kind == "equation":
        return "found the solution"
    return "solved each equation"


def diagnose_roots(cur, new):
    if not new and cur:
        return "That says there is no solution, but the line above has some."
    if new and not cur:
        return "The line above has no real solutions, so this can't be right."
    miss = [r for r in cur if not any(abs(r - s) < 1e-9 for s in new)]
    extra = [s for s in new if not any(abs(s - r) < 1e-9 for r in cur)]
    if miss and not extra:
        n = len(cur)
        return ("A solution is missing - the line above has "
                + (f"{n} solutions." if n != 1 else "a solution."))
    if extra and not miss:
        return "An extra solution appeared that the line above doesn't have."
    return "Check the arithmetic - these solutions don't match the line above."


def _describe(kind):
    return {"equation": "an equation", "expression": "an expression",
            "solset": "a list of solutions"}[kind]


# ── a working session ─────────────────────────────────────────────────────
class StepResult:
    def __init__(self, kind, message, rule="", done=False, text=""):
        self.kind, self.message, self.rule = kind, message, rule
        self.done, self.text = done, text

    @property
    def ok(self):
        return self.kind == "ok"


class Session:
    """One problem and the student's lines. Wrong lines are not kept: the
    student retries from the last good line."""

    def __init__(self, problem):
        self.first = parse_line(problem)
        if self.first.kind == "solset":
            raise MathError("Start with an equation or an expression.")
        self.lines = [self.first]
        self.wrong = 0
        self.hints = 0
        self.revealed = 0
        self.canon = canon_for(self.first)
        self.level, self.n_steps = complexity(problem)

    @property
    def current(self):
        return self.lines[-1]

    def status(self):
        return solved(self.current, self.canon)

    def submit(self, text):
        try:
            new = parse_line(text)
        except MathError as e:
            return StepResult("info", str(e))
        cur = self.current
        eqish = ("equation", "solset")
        if (new.kind == "expression") != (cur.kind == "expression"):
            return StepResult("wrong", f"That line is {_describe(new.kind)}, "
                              f"but the one above is {_describe(cur.kind)}.")
        if not getattr(new, "nosol", False) and \
                set(new.variables()) - set(cur.variables()):
            self.wrong += 1
            return StepResult("wrong", "A different variable appeared.")
        if cur.kind == "expression":
            same = new.P == cur.P
        elif cur.kind == "equation" and new.kind == "equation":
            same = proportional(cur.P, new.P) is not None
            if not same and max(cur.P.degree(), new.P.degree()) >= 2:
                try:                     # x^2 = 0  ->  x = 0 keeps the solutions
                    cr, nr = line_roots(cur), line_roots(new)
                    if cr != ALL and nr != ALL and cr and same_roots(cr, nr):
                        same = True
                    else:
                        msg = diagnose_roots([] if cr == ALL else cr,
                                             [] if nr == ALL else nr)
                        if not msg.startswith("Check the arithmetic"):
                            self.wrong += 1
                            return StepResult("wrong", msg)
                except MathError:
                    pass
        else:
            try:
                cr, nr = line_roots(cur), line_roots(new)
            except MathError as e:
                return StepResult("info", str(e))
            same = same_roots(cr, nr)
            if not same:
                self.wrong += 1
                return StepResult("wrong", diagnose_roots(
                    [] if cr == ALL else cr, [] if nr == ALL else nr))
        if not same:
            self.wrong += 1
            return StepResult("wrong", diagnose(cur, new))
        rule = name_any(cur, new)
        if rule == "no change" or (new.text.replace(" ", "")
                                   == cur.text.replace(" ", "")):
            return StepResult("info", "That's the same as the line above.")
        self.lines.append(new)
        out = solved(new, self.canon)
        return StepResult("ok", "You " + rule + ".", rule, bool(out), new.text)

    def hint(self, level):
        """level 1: the idea, 2: the action, 3: the next line."""
        mv = next_move(self.current, self.canon)
        if mv is None:
            out = solved(self.current, self.canon)
            if out:
                return "You're done: " + out + "."
            return ("I can't suggest a step for this one yet, but I'll still "
                    "check every line you write.")
        self.hints += 1
        if level <= 1:
            return mv.hint1
        if level == 2:
            return mv.hint2
        self.revealed += 1
        return mv.new_text

    def solution_from_here(self):
        out, _end = _walk(self.current, self.canon)
        self.revealed += 1 if out else 0
        return out

    def summary(self):
        good = len(self.lines) - 1
        if self.wrong == 0 and not self.revealed:
            how = "No wrong steps."
        elif self.revealed:
            how = "You used the solution."
        else:
            how = f"{self.wrong} wrong " + ("step" if self.wrong == 1 else "steps") + " along the way."
        hints = f" {self.hints} hint" + ("" if self.hints == 1 else "s") + " used." if self.hints else ""
        return f"{good} step" + ("" if good == 1 else "s") + f" written. {how}{hints}"
