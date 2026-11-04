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
#     linear equations in one variable and simplifying expressions; steps for
#     other polynomials (quadratics...) are still checked, just not solved.
#
# Numbers are exact fractions. Expressions are polynomials with fractional
# coefficients; division only by a plain number, powers only by whole numbers.
import re
from fractions import Fraction

MAX_POWER = 12


class MathError(ValueError):
    """The text can't be read as maths."""


class NotSupported(MathError):
    """Valid maths this version doesn't handle (yet)."""


# ── parsing ───────────────────────────────────────────────────────────────
_TOKEN = re.compile(r"\s*(\d+\.\d+|\d+|\.\d+|[A-Za-z]|[-+*/^()=]|\S)")


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
            elif self.peek()[0] == "var" or self.op("("):      # 2x, 3(x+1), (x)(y)
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
        if node[1][0] == "num" and node[2][0] == "num":
            a, b = node[1][1], node[2][1]
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
        return "combined like terms" if b.tidy() else "simplified"
    if a.L == b.L and a.R == b.R:
        if a.text.replace(" ", "") == b.text.replace(" ", ""):
            return "no change"
        if b.brackets() < a.brackets():
            return "expanded the brackets"
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


def solved(line):
    """'' while unfinished, else a short outcome text."""
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


def next_move(line):
    """The solver's next step from `line`, or None when finished / not
    supported (check `solved(line)` and `can_solve(line)`)."""
    if solved(line) or not can_solve(line):
        return None
    if line.kind == "expression":
        return Move("simplify", "Tidy the expression.",
                    "Expand the brackets and combine like terms.",
                    fmt(line.P), "Expanded the brackets and combined like terms.")
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
    vs = line.variables()
    if len(vs) > 1:
        return False
    if line.kind == "expression":
        return True
    return line.P.degree() <= 1


def solution(text):
    """[(line text, explanation)] from the problem to the answer; [] if the
    solver doesn't cover it."""
    line = Line(text)
    steps = []
    for _ in range(30):
        mv = next_move(line)
        if mv is None:
            break
        steps.append((mv.new_text, mv.why))
        line = Line(mv.new_text)
    return steps if solved(line) else []


def complexity(text):
    """('Easy' | 'Medium' | 'Hard', number of solving steps or None)."""
    try:
        line = Line(text)
    except MathError:
        return ("Hard", None)
    if not can_solve(line):
        return ("Hard", None)
    n = len(solution(text))
    if line.kind == "equation" and line.P.degree() > 1:
        return ("Hard", None)
    level = "Easy" if n <= 2 else "Medium" if n <= 4 else "Hard"
    return (level, n)


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
        self.first = Line(problem)
        self.lines = [self.first]
        self.wrong = 0
        self.hints = 0
        self.revealed = 0
        self.level, self.n_steps = complexity(problem)

    @property
    def current(self):
        return self.lines[-1]

    def status(self):
        return solved(self.current)

    def submit(self, text):
        try:
            new = Line(text)
        except MathError as e:
            return StepResult("info", str(e))
        cur = self.current
        if new.kind != cur.kind:
            return StepResult("wrong", "That line is "
                              + ("an equation" if new.kind == "equation"
                                 else "an expression")
                              + ", but the one above is "
                              + ("an equation." if cur.kind == "equation"
                                 else "an expression."))
        if set(new.variables()) - set(cur.variables()):
            self.wrong += 1
            return StepResult("wrong", "A different variable appeared.")
        if cur.kind == "equation":
            same = proportional(cur.P, new.P) is not None
        else:
            same = new.P == cur.P
        if not same:
            self.wrong += 1
            return StepResult("wrong", diagnose(cur, new))
        rule = name_step(cur, new)
        if rule == "no change":
            return StepResult("info", "That's the same as the line above.")
        self.lines.append(new)
        out = solved(new)
        return StepResult("ok", "You " + rule + ".", rule, bool(out), new.text)

    def hint(self, level):
        """level 1: the idea, 2: the action, 3: the next line."""
        mv = next_move(self.current)
        if mv is None:
            out = solved(self.current)
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
        out, line = [], self.current
        for _ in range(30):
            mv = next_move(line)
            if mv is None:
                break
            out.append((mv.new_text, mv.why))
            line = Line(mv.new_text)
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
