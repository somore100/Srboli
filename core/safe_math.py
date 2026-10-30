# core/safe_math.py - arithmetic on typed-in text without eval().
"""Evaluate + - * / % ** and parentheses on plain numbers.

Every number is a float, so a runaway power such as 9**9**9 raises
OverflowError at once instead of building a huge integer and freezing the UI.
"""
import ast
import operator

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
MAX_LEN = 200


def arith(expr):
    expr = expr.strip()
    if not expr or len(expr) > MAX_LEN:
        raise ValueError("bad expression")

    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](walk(n.left), walk(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = walk(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        raise ValueError("unsupported expression")

    result = walk(ast.parse(expr, mode="eval"))
    if isinstance(result, complex) or result != result:
        raise ValueError("not a real number")
    return result
