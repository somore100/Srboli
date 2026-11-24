# core/calc_core.py - the pocket calculator behind Srboli's bubble calculator. No Kivy.
import ast
import math
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
MAX_ENTRY = 15


def safe_eval(text):
    """Value of a plain arithmetic text (numbers, + - * /, unary minus, brackets) as a float.
    Anything else raises ValueError; there is no eval()."""
    def walk(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _BIN[type(n.op)](walk(n.left), walk(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = walk(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ValueError("not plain arithmetic")
    try:
        return walk(ast.parse(str(text).strip(), mode="eval").body)
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as e:
        raise ValueError(str(e) or "bad expression") from e


def fmt(v):
    """3.0 -> '3', 0.1+0.2 -> '0.3', up to 10 significant digits; nan / inf -> 'Error'."""
    if not math.isfinite(v):
        return "Error"
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    s = f"{v:.10g}"
    return s


class Calc:
    def __init__(self):
        self.entry, self.expr, self.history, self.fresh = "0", "", [], False

    def _bad(self):
        return self.entry == "Error"

    def _log(self, text):
        self.history.append(text)
        del self.history[:-20]

    def digit(self, d):
        if d not in "0123456789." or len(d) != 1:
            return
        if self._bad() or self.fresh:
            self.entry, self.fresh = "0", False
        if d == "." and "." in self.entry:
            return
        if self.entry == "0" and d != ".":
            self.entry = d
        elif self.entry == "-0" and d != ".":
            self.entry = "-" + d
        elif len(self.entry) < MAX_ENTRY:
            self.entry += d

    def op(self, o):
        if o not in "+-*/" or self._bad():
            return
        if self.expr and self.expr[-1] in "+-*/" and self.entry == "0" and not self.fresh:
            self.expr = self.expr[:-1] + o              # changed my mind about the operator
        else:
            self.expr += f"({self.entry})" if self.entry.startswith("-") else self.entry
            self.expr += o
        self.entry, self.fresh = "0", False

    def equals(self):
        if self._bad():
            return
        e = self.expr + (f"({self.entry})" if self.entry.startswith("-") else self.entry)
        try:
            v = safe_eval(e)
            r = fmt(v)
            if r == "Error":
                raise ValueError("overflow")
        except ValueError:
            self.entry, self.expr, self.fresh = "Error", "", False
            return
        self._log(f"{e} = {r}")
        self.entry, self.expr, self.fresh = r, "", True

    def clear(self):
        self.entry, self.expr, self.fresh = "0", "", False

    def back(self):
        if self._bad() or self.fresh:
            return
        self.entry = self.entry[:-1] if len(self.entry) > 1 and self.entry != "-0" else "0"
        if self.entry == "-":
            self.entry = "0"

    def _unary(self, label, fn):
        if self._bad():
            return
        try:
            v = float(self.entry)
            r = fmt(fn(v))
        except (ValueError, ZeroDivisionError, OverflowError):
            self.entry, self.fresh = "Error", False
            return
        if r == "Error":
            self.entry, self.fresh = "Error", False
            return
        self._log(f"{label}({self.entry}) = {r}")
        self.entry, self.fresh = r, True

    def negate(self):
        if self._bad() or self.entry == "0":
            return
        self.entry = self.entry[1:] if self.entry.startswith("-") else "-" + self.entry

    def percent(self):
        self._unary("%", lambda v: v / 100)

    def sqrt(self):
        self._unary("sqrt", lambda v: math.sqrt(v))

    def square(self):
        self._unary("sq", lambda v: v * v)

    def inverse(self):
        self._unary("1/", lambda v: 1 / v)

    def const(self, v):
        self.entry, self.fresh = fmt(v), True
