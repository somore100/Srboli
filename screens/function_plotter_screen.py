# screens/function_plotter_screen.py
"""Function plotter / visualizer for Srboli.

Features
--------
* y=f(x) expression rows with safe AST evaluation (no eval()).
* Parametric x(t), y(t) and polar r(θ) rows.
* Pencil mode: freehand stroke → spline / polynomial / piecewise.
* Point mode: tap to place points, drag cancels, 2-finger pan + pinch-zoom.
* Warp: drag a curve to bend it locally with a Gaussian falloff, pinch or
  wheel to widen/narrow the falloff radius live.
* Fill between two curves with a numeric integral readout.
* Piecewise → expression conversion via nested where().
* Content undo/redo (Ctrl+Z/Y) with a labelled history panel.
* View undo/redo (Ctrl+Alt+Z/Y) for pan/zoom only.
* PNG export of the current view.
"""

import ast
import datetime
import math
import operator
import os

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Line, Mesh, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

import app_data


# ══════════════════════════════════════════════════════════════════════════
# Safe expression evaluation
# ══════════════════════════════════════════════════════════════════════════

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_UN_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "exp": math.exp, "log": math.log, "log10": math.log10,
    "log2": math.log2, "sqrt": math.sqrt,
    "cbrt": lambda v: math.copysign(abs(v) ** (1.0 / 3.0), v),
    "abs": abs, "floor": math.floor, "ceil": math.ceil, "round": round,
    "min": min, "max": max, "sign": lambda v: (v > 0) - (v < 0),
    "atan2": math.atan2, "hypot": math.hypot,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class ExprError(ValueError):
    pass


def _compare(op_node, a, b):
    if isinstance(op_node, ast.Lt):    return a < b
    if isinstance(op_node, ast.LtE):   return a <= b
    if isinstance(op_node, ast.Gt):    return a > b
    if isinstance(op_node, ast.GtE):   return a >= b
    if isinstance(op_node, ast.Eq):    return a == b
    if isinstance(op_node, ast.NotEq): return a != b
    raise ExprError(f"unsupported comparison: {type(op_node).__name__}")


def _eval_node(node, x, var="x"):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, x, var)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return node.value
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ExprError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id == var:
            return x
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ExprError(f"unknown name: {node.id}")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ExprError(f"unsupported operator: {type(node.op).__name__}")
        return op(_eval_node(node.left, x, var),
                  _eval_node(node.right, x, var))
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _eval_node(node.operand, x, var)
        op = _UN_OPS.get(type(node.op))
        if op is None:
            raise ExprError(f"unsupported unary: {type(node.op).__name__}")
        return op(_eval_node(node.operand, x, var))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not _eval_node(v, x, var):
                    return False
            return True
        for v in node.values:
            if _eval_node(v, x, var):
                return True
        return False
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, x, var)
        for op_node, comp in zip(node.ops, node.comparators):
            right = _eval_node(comp, x, var)
            if not _compare(op_node, left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExprError("only simple function calls allowed")
        # where() is lazy — dispatch before the generic function table
        if node.func.id == "where":
            if len(node.args) != 3:
                raise ExprError("where(cond, a, b) takes 3 arguments")
            cond = _eval_node(node.args[0], x, var)
            return _eval_node(node.args[1] if cond else node.args[2], x, var)
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise ExprError(f"unknown function: {node.func.id}")
        if node.keywords:
            raise ExprError("keyword arguments not allowed")
        return fn(*[_eval_node(a, x, var) for a in node.args])
    raise ExprError(f"unsupported syntax: {type(node).__name__}")


def compile_expr(text, var="x"):
    """Compile a user expression string into f(t) -> float.
    `var` names the free variable (`x` for y-mode, `t` for param/polar).
    Raises ExprError on anything invalid or unsafe."""
    text = text.strip().replace("^", "**")
    if not text:
        raise ExprError("empty expression")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"syntax error: {e.msg}") from None

    def fn(t):
        return _eval_node(tree, t, var)
    return fn


# ══════════════════════════════════════════════════════════════════════════
# Polynomial fitting (no numpy)
# ══════════════════════════════════════════════════════════════════════════

def _solve(A, b):
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-12:
            return None
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for c in range(col, n + 1):
            M[col][c] /= pv
        for r in range(n):
            if r == col:
                continue
            f = M[r][col]
            if f == 0:
                continue
            for c in range(col, n + 1):
                M[r][c] -= f * M[col][c]
    return [M[i][n] for i in range(n)]


def poly_fit(xs, ys, degree):
    n = degree + 1
    if len(xs) < n:
        return None
    ATA = [[0.0] * n for _ in range(n)]
    ATy = [0.0] * n
    for x, y in zip(xs, ys):
        powers = [x ** k for k in range(n)]
        for r in range(n):
            ATy[r] += powers[r] * y
            for c in range(n):
                ATA[r][c] += powers[r] * powers[c]
    return _solve(ATA, ATy)


def poly_to_str(coefs):
    parts = []
    for k in range(len(coefs) - 1, -1, -1):
        c = coefs[k]
        if abs(c) < 1e-9:
            continue
        sign = "-" if c < 0 else ("+" if parts else "")
        a = abs(c)
        if k == 0:
            body = f"{a:.4g}"
        elif k == 1:
            body = f"{a:.4g}x"
        else:
            body = f"{a:.4g}x^{k}"
        parts.append(f"{sign} {body}" if sign else body)
    return " ".join(parts).strip() or "0"


def poly_to_expr(coefs):
    parts = []
    for k in range(len(coefs) - 1, -1, -1):
        c = coefs[k]
        if abs(c) < 1e-9:
            continue
        if k == 0:
            parts.append(f"({c!r})")
        elif k == 1:
            parts.append(f"({c!r})*x")
        else:
            parts.append(f"({c!r})*x**{k}")
    return " + ".join(parts) or "0"


# ══════════════════════════════════════════════════════════════════════════
# Stroke / spline / range / integral helpers
# ══════════════════════════════════════════════════════════════════════════

def stroke_to_xy(world_stroke, n_bins=200):
    """Convert a freehand (wx, wy) stroke into a left-to-right function
    sequence by binning y per x-column."""
    if len(world_stroke) < 2:
        return []
    xs = [p[0] for p in world_stroke]
    lo, hi = min(xs), max(xs)
    span = hi - lo
    if span <= 1e-12:
        return []
    bin_w = span / n_bins
    buckets = {}
    for wx, wy in world_stroke:
        k = min(n_bins - 1, int((wx - lo) / bin_w))
        buckets.setdefault(k, []).append(wy)
    pts = []
    for k in sorted(buckets):
        cx = lo + (k + 0.5) * bin_w
        cy = sum(buckets[k]) / len(buckets[k])
        pts.append((cx, cy))
    pts[0] = (lo, sum(y for x, y in world_stroke if x == lo) /
              max(1, sum(1 for x, y in world_stroke if x == lo)))
    pts[-1] = (hi, sum(y for x, y in world_stroke if x == hi) /
               max(1, sum(1 for x, y in world_stroke if x == hi)))
    return pts


def make_spline(pts):
    """Cubic Hermite (Catmull-Rom tangents) through sorted (x,y) points."""
    pts = sorted(pts)
    P = []
    for x, y in pts:
        if not P or x > P[-1][0] + 1e-12:
            P.append((x, y))
    if len(P) < 2:
        return None

    def f(x):
        if x <= P[0][0]:
            return P[0][1]
        if x >= P[-1][0]:
            return P[-1][1]
        lo, hi = 0, len(P) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if P[mid][0] <= x:
                lo = mid
            else:
                hi = mid
        x0, y0 = P[lo]
        x1, y1 = P[lo + 1]
        h = x1 - x0
        if h < 1e-12:
            return y0
        xm1, ym1 = P[lo - 1] if lo > 0 else P[lo]
        x2, y2 = P[lo + 2] if lo + 2 < len(P) else P[lo + 1]
        m0 = (y1 - ym1) / (x1 - xm1) if x1 > xm1 else 0.0
        m1 = (y2 - y0) / (x2 - x0) if x2 > x0 else 0.0
        t = (x - x0) / h
        t2 = t * t
        t3 = t2 * t
        h00 = 2 * t3 - 3 * t2 + 1
        h10 = t3 - 2 * t2 + t
        h01 = -2 * t3 + 3 * t2
        h11 = t3 - t2
        return h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1

    return f


def stroke_to_piecewise(world_stroke, y_jump):
    """Split a stroke at big, mostly-vertical jumps. A jump must clear
    BOTH an absolute view-relative floor (y_jump) and ~5x the stroke's
    median step size, so smooth-but-steep curves don't false-split.

    Returns a list of point-lists (each at least 3 points long)."""
    if len(world_stroke) < 2:
        return []

    # adaptive floor: real discontinuities dwarf the typical |dy| step
    dys = sorted(abs(world_stroke[i][1] - world_stroke[i - 1][1])
                 for i in range(1, len(world_stroke)))
    median_dy = dys[len(dys) // 2] if dys else 0.0
    adaptive_min = max(y_jump, median_dy * 5.0)

    segments = [[world_stroke[0]]]
    for i in range(1, len(world_stroke)):
        px, py = world_stroke[i - 1]
        cx, cy = world_stroke[i]
        dx = abs(cx - px)
        dy = abs(cy - py)
        if dy > adaptive_min and dx < dy * 0.5:
            segments.append([world_stroke[i]])
        else:
            segments[-1].append(world_stroke[i])
    return [s for s in segments if len(s) >= 3]


def make_piecewise_spline(segment_lists, n_bins=200):
    """Return (fn, pieces). fn returns None outside every covered x-range."""
    compiled = []
    for seg in segment_lists:
        binned = stroke_to_xy(seg, n_bins=n_bins)
        if len(binned) < 2:
            continue
        sfn = make_spline(binned)
        if sfn is None:
            continue
        x_lo, x_hi = binned[0][0], binned[-1][0]
        if x_hi <= x_lo:
            continue
        compiled.append((x_lo, x_hi, sfn, binned))
    if not compiled:
        return None, []
    compiled.sort(key=lambda c: c[0])

    def f(x):
        for x_lo, x_hi, sfn, _binned in compiled:
            if x_lo - 1e-9 <= x <= x_hi + 1e-9:
                return sfn(x)
        return None

    pieces = [(lo, hi, binned) for lo, hi, _sfn, binned in compiled]
    return f, pieces


def parse_range(text, default_lo=0.0, default_hi=2 * math.pi):
    try:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 2:
            return default_lo, default_hi
        lo, hi = float(parts[0]), float(parts[1])
        if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
            return default_lo, default_hi
        return lo, hi
    except Exception:
        return default_lo, default_hi


def integrate_between(a_fn, b_fn, x_lo, x_hi, n=2000):
    """Trapezoidal ∫(a−b) dx over [x_lo, x_hi]. Returns (signed, abs)."""
    if x_hi <= x_lo:
        return 0.0, 0.0
    dx = (x_hi - x_lo) / n
    signed = 0.0
    absval = 0.0
    prev = None
    for i in range(n + 1):
        wx = x_lo + i * dx
        try:
            d = a_fn(wx) - b_fn(wx)
        except Exception:
            prev = None
            continue
        if not (isinstance(d, (int, float)) and math.isfinite(d)):
            prev = None
            continue
        if prev is not None:
            trap = (prev + d) * 0.5 * dx
            signed += trap
            absval += abs(trap)
        prev = d
    return signed, absval


# ══════════════════════════════════════════════════════════════════════════
# Graph canvas
# ══════════════════════════════════════════════════════════════════════════

PALETTE = [
    (0.30, 0.75, 1.00, 1),
    (1.00, 0.45, 0.55, 1),
    (0.55, 1.00, 0.55, 1),
    (1.00, 0.85, 0.35, 1),
    (0.85, 0.55, 1.00, 1),
    (0.40, 1.00, 0.90, 1),
    (1.00, 0.60, 0.30, 1),
]


class GraphCanvas(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.x_min, self.x_max = -10.0, 10.0
        self.y_min, self.y_max = -6.0, 6.0
        self.functions = []
        self.points = []
        self.fit = None
        self.fill = None
        self.mode = "pan"
        self._drag = None
        self._step_x = 1.0
        self._step_y = 1.0

        # pencil
        self._stroke_px = None
        self.on_stroke_done = None

        # warp
        self.warp_preview = None
        self.warp_visual = None
        self.on_warp_start = None
        self.on_warp_move = None
        self.on_warp_end = None
        self.on_warp_radius = None
        self._warp_active = False
        self._warp_hit_px = dp(14)
        self._warp_touches = {}
        self._warp_primary_uid = None
        self._pinch_last_dist = None

        # view notifications (separate stack from content undo)
        self.on_view_changed = None
        self._view_debounce = None

        # pencil multitouch
        self._pencil_touches = {}
        self._pencil_multi = False
        self._pencil_pan_anchor = None

        # point multitouch + pinch
        self._point_touches = {}
        self._point_multi = False
        self._point_pan_anchor = None
        self._point_candidate_px = None
        self._point_moved = False
        # dp, not raw px - the same physical tolerance on every device
        self._point_move_threshold = dp(8)
        self._point_prev_dist = None
        self.on_points_changed = None

        self.bind(pos=self._redraw, size=self._redraw)

    # ── public API ─────────────────────────────────────────────────────

    def set_functions(self, funcs):
        self.functions = funcs
        self._redraw()

    def reset_view(self):
        self.x_min, self.x_max = -10.0, 10.0
        self.y_min, self.y_max = -6.0, 6.0
        self._redraw()

    def clear_points(self):
        self.points = []
        self.fit = None
        self.fill = None
        self._redraw()

    # ── coordinate transforms ──────────────────────────────────────────

    def _w2s(self, wx, wy):
        px = self.x + (wx - self.x_min) / (self.x_max - self.x_min) * self.width
        py = self.y + (wy - self.y_min) / (self.y_max - self.y_min) * self.height
        return px, py

    def _s2w(self, px, py):
        wx = self.x_min + (px - self.x) / max(1.0, self.width) * (self.x_max - self.x_min)
        wy = self.y_min + (py - self.y) / max(1.0, self.height) * (self.y_max - self.y_min)
        return wx, wy

    # ── rendering ──────────────────────────────────────────────────────

    def _redraw(self, *a):
        self.canvas.clear()
        if self.width <= 1 or self.height <= 1:
            return
        with self.canvas:
            Color(0.07, 0.08, 0.11, 1)
            Rectangle(pos=self.pos, size=self.size)
            self._draw_grid()
            self._draw_axes()
            self._draw_fill()

            for f in self.functions:
                if not f.get("visible"):
                    continue
                mode = f.get("mode", "y")
                if mode == "y" and f.get("fn"):
                    self._draw_curve(f["fn"], f["color"], 1.5)
                elif mode == "param" and f.get("fn_x") and f.get("fn_y"):
                    self._draw_parametric(f["fn_x"], f["fn_y"],
                                          f["t_lo"], f["t_hi"],
                                          f["color"], 1.5)
                elif mode == "polar" and f.get("fn"):
                    self._draw_polar(f["fn"], f["t_lo"], f["t_hi"],
                                     f["color"], 1.5)

            if self.fit:
                self._draw_curve(self.fit["fn"], self.fit["color"], 1.6)

            self._draw_points()

            if self._stroke_px:
                Color(1, 0.9, 0.3, 0.9)
                flat = []
                for px, py in self._stroke_px:
                    flat.extend([px, py])
                if len(flat) >= 4:
                    Line(points=flat, width=2)

            if self.warp_preview and len(self.warp_preview) >= 2:
                Color(1.0, 0.62, 0.22, 0.95)
                flat = []
                for wx, wy in self.warp_preview:
                    flat.extend(self._w2s(wx, wy))
                Line(points=flat, width=2.2)

            if self.warp_visual:
                gx, gy = self.warp_visual["grab"]
                r = self.warp_visual["radius"]
                pts = []
                for i in range(72):
                    a = 2 * math.pi * i / 72
                    pts.extend(self._w2s(gx + r * math.cos(a),
                                         gy + r * math.sin(a)))
                pts.extend(pts[:2])
                Color(1.0, 0.62, 0.22, 0.28)
                Line(points=pts, width=1.2)
                pct = self.warp_visual.get("pct")
                if pct is not None:
                    _, py_above = self._w2s(gx, gy + r)
                    self._text(f"r = {pct}%",
                               self._w2s(gx, gy)[0] + 6,
                               py_above + 4,
                               (1.0, 0.75, 0.35, 1), 11)

            if (self.mode == "point"
                    and self._point_candidate_px is not None
                    and not self._point_moved
                    and not self._point_multi):
                px, py = self._point_candidate_px
                Color(1, 0.9, 0.3, 0.55)
                Line(circle=(px, py, 6), width=1.4)
                Color(1, 0.9, 0.3, 1)
                Line(circle=(px, py, 2), width=1.0)

    def _nice_step(self, span):
        if span <= 0:
            return 1.0
        raw = span / 10.0
        mag = 10 ** math.floor(math.log10(raw))
        for m in (1, 2, 5):
            if raw <= m * mag:
                return m * mag
        return 10 * mag

    def _iter_ticks(self, lo, hi, step):
        v = math.floor(lo / step) * step
        n = 0
        while v <= hi + 1e-9 and n < 500:
            yield v
            v += step
            n += 1

    def _draw_grid(self):
        self._step_x = self._nice_step(self.x_max - self.x_min)
        self._step_y = self._nice_step(self.y_max - self.y_min)
        Color(0.16, 0.18, 0.23, 1)
        for x in self._iter_ticks(self.x_min, self.x_max, self._step_x):
            px, _ = self._w2s(x, 0)
            Line(points=[px, self.y, px, self.top], width=1)
        for y in self._iter_ticks(self.y_min, self.y_max, self._step_y):
            _, py = self._w2s(0, y)
            Line(points=[self.x, py, self.right, py], width=1)

    def _draw_axes(self):
        Color(0.75, 0.78, 0.85, 1)
        has_x_axis = self.y_min <= 0 <= self.y_max
        has_y_axis = self.x_min <= 0 <= self.x_max
        axis_py = self._w2s(0, 0)[1] if has_x_axis else self.y
        axis_px = self._w2s(0, 0)[0] if has_y_axis else self.x
        if has_x_axis:
            Line(points=[self.x, axis_py, self.right, axis_py], width=1.6)
        if has_y_axis:
            Line(points=[axis_px, self.y, axis_px, self.top], width=1.6)

        for x in self._iter_ticks(self.x_min, self.x_max, self._step_x):
            if abs(x) < 1e-9:
                continue
            px, _ = self._w2s(x, 0)
            if self.x + 4 < px < self.right - 34:
                self._text(self._fmt(x), px + 3, axis_py + 3,
                           (0.62, 0.66, 0.74, 1), 10)
        for y in self._iter_ticks(self.y_min, self.y_max, self._step_y):
            if abs(y) < 1e-9:
                continue
            _, py = self._w2s(0, y)
            if self.y + 4 < py < self.top - 14:
                self._text(self._fmt(y), axis_px + 4, py + 2,
                           (0.62, 0.66, 0.74, 1), 10)

    def _fmt(self, v):
        if abs(v) < 1e-9:
            return "0"
        if abs(v) >= 1e5 or abs(v) < 1e-4:
            return f"{v:.1e}"
        return f"{v:g}"

    def _text(self, s, x, y, color=(1, 1, 1, 1), size=11):
        lbl = CoreLabel(text=s, font_size=sp(size))
        lbl.refresh()
        tex = lbl.texture
        if tex is None:
            return
        Color(*color)
        Rectangle(texture=tex, pos=(x, y), size=tex.size)

    def _draw_curve(self, fn, color, width=1.5):
        if self.width < 4:
            return
        px_start = int(self.x) + 1
        px_end = int(self.right) - 1
        max_jump = self.height * 1.5
        Color(*color)
        seg = []
        prev_py = None
        px = px_start
        while px < px_end:
            wx, _ = self._s2w(px, 0)
            try:
                wy = fn(wx)
            except Exception:
                wy = None
            ok = isinstance(wy, (int, float)) and math.isfinite(wy)
            if not ok:
                if len(seg) >= 4:
                    Line(points=seg, width=width)
                seg = []
                prev_py = None
                px += 2
                continue
            _, py = self._w2s(0, wy)
            if prev_py is not None and abs(py - prev_py) > max_jump:
                if len(seg) >= 4:
                    Line(points=seg, width=width)
                seg = []
            seg.extend([px, py])
            prev_py = py
            px += 2
        if len(seg) >= 4:
            Line(points=seg, width=width)

    def _draw_parametric(self, fn_x, fn_y, t_lo, t_hi, color, width=1.5):
        if self.width < 4:
            return
        n = 800
        Color(*color)
        seg = []
        prev = None
        jump_x = self.width * 1.5
        jump_y = self.height * 1.5
        for i in range(n + 1):
            t = t_lo + (t_hi - t_lo) * i / n
            try:
                wx = fn_x(t)
                wy = fn_y(t)
            except Exception:
                if len(seg) >= 4:
                    Line(points=seg, width=width)
                seg = []
                prev = None
                continue
            if not (isinstance(wx, (int, float))
                    and isinstance(wy, (int, float))
                    and math.isfinite(wx) and math.isfinite(wy)):
                if len(seg) >= 4:
                    Line(points=seg, width=width)
                seg = []
                prev = None
                continue
            px, py = self._w2s(wx, wy)
            if prev is not None:
                if (abs(px - prev[0]) > jump_x
                        or abs(py - prev[1]) > jump_y):
                    if len(seg) >= 4:
                        Line(points=seg, width=width)
                    seg = []
            seg.extend([px, py])
            prev = (px, py)
        if len(seg) >= 4:
            Line(points=seg, width=width)

    def _draw_polar(self, fn_r, t_lo, t_hi, color, width=1.5):
        if self.width < 4:
            return
        n = 800
        Color(*color)
        seg = []
        prev = None
        jump_x = self.width * 1.5
        jump_y = self.height * 1.5
        for i in range(n + 1):
            t = t_lo + (t_hi - t_lo) * i / n
            try:
                r = fn_r(t)
            except Exception:
                r = None
            if not (isinstance(r, (int, float)) and math.isfinite(r)):
                if len(seg) >= 4:
                    Line(points=seg, width=width)
                seg = []
                prev = None
                continue
            wx = r * math.cos(t)
            wy = r * math.sin(t)
            px, py = self._w2s(wx, wy)
            if prev is not None:
                if (abs(px - prev[0]) > jump_x
                        or abs(py - prev[1]) > jump_y):
                    if len(seg) >= 4:
                        Line(points=seg, width=width)
                    seg = []
            seg.extend([px, py])
            prev = (px, py)
        if len(seg) >= 4:
            Line(points=seg, width=width)

    def _draw_points(self):
        if not self.points:
            return
        Color(1, 0.9, 0.3, 1)
        for wx, wy in self.points:
            px, py = self._w2s(wx, wy)
            if not (self.x <= px <= self.right and self.y <= py <= self.top):
                continue
            Line(circle=(px, py, 5), width=1.6)

    def _draw_fill(self):
        if not self.fill:
            return
        fl = self.fill
        a_fn, b_fn = fl["a_fn"], fl["b_fn"]
        x_lo, x_hi = fl["x_lo"], fl["x_hi"]
        if x_hi <= x_lo:
            return
        n = 400
        verts = []
        for i in range(n + 1):
            wx = x_lo + (x_hi - x_lo) * i / n
            try:
                ya = a_fn(wx)
                yb = b_fn(wx)
            except Exception:
                continue
            if not (isinstance(ya, (int, float))
                    and isinstance(yb, (int, float))
                    and math.isfinite(ya) and math.isfinite(yb)):
                continue
            px, pya = self._w2s(wx, ya)
            _, pyb = self._w2s(wx, yb)
            verts.extend([px, pya, 0, 0])
            verts.extend([px, pyb, 0, 0])
        ncols = len(verts) // 8
        if ncols < 2:
            return
        idxs = []
        for i in range(ncols - 1):
            b = i * 2
            idxs.extend([b, b + 1, b + 2, b + 1, b + 3, b + 2])
        Color(*fl["color"])
        Mesh(vertices=verts, indices=idxs, mode="triangles")

    # ── hit test ───────────────────────────────────────────────────────

    def _hit_test_curve(self, pos):
        """Nearest visible curve within _warp_hit_px, or None. Samples a
        small window of world-x around the touch so near-vertical segments
        (tan(x), 1/x) are hittable even where the closest point isn't
        directly above or below the cursor."""
        if not self.functions:
            return None
        wx0, _ = self._s2w(*pos)
        span = self.x_max - self.x_min
        half_win = span * (25.0 / max(1.0, self.width)) / 2.0
        if half_win <= 0:
            half_win = span * 0.01
        n = 9
        xs = [wx0 - half_win + 2 * half_win * i / (n - 1) for i in range(n)]

        best_i = None
        best_d = float(self._warp_hit_px)
        for i, entry in enumerate(self.functions):
            fn = entry.get("fn")
            if not entry.get("visible") or fn is None:
                continue
            for wx in xs:
                try:
                    wy = fn(wx)
                except Exception:
                    continue
                if not isinstance(wy, (int, float)) or not math.isfinite(wy):
                    continue
                px, py = self._w2s(wx, wy)
                d = math.hypot(px - pos[0], py - pos[1])
                if d < best_d:
                    best_d = d
                    best_i = i
        return best_i

    # ── multitouch helpers ─────────────────────────────────────────────

    def _pinch_dist(self):
        if len(self._warp_touches) < 2:
            return None
        (x1, y1), (x2, y2) = list(self._warp_touches.values())[:2]
        return math.hypot(x2 - x1, y2 - y1)

    def _pencil_centroid(self):
        if not self._pencil_touches:
            return None
        xs = [p[0] for p in self._pencil_touches.values()]
        ys = [p[1] for p in self._pencil_touches.values()]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _point_centroid(self):
        if not self._point_touches:
            return None
        xs = [p[0] for p in self._point_touches.values()]
        ys = [p[1] for p in self._point_touches.values()]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _point_dist(self):
        if len(self._point_touches) < 2:
            return None
        (x1, y1), (x2, y2) = list(self._point_touches.values())[:2]
        return math.hypot(x2 - x1, y2 - y1)

    def _clamp_view_span(self, min_span=1e-6, max_span=1e9):
        sx = self.x_max - self.x_min
        sy = self.y_max - self.y_min
        if sx < min_span:
            cx = (self.x_min + self.x_max) / 2
            self.x_min, self.x_max = cx - min_span / 2, cx + min_span / 2
        elif sx > max_span:
            cx = (self.x_min + self.x_max) / 2
            self.x_min, self.x_max = cx - max_span / 2, cx + max_span / 2
        if sy < min_span:
            cy = (self.y_min + self.y_max) / 2
            self.y_min, self.y_max = cy - min_span / 2, cy + min_span / 2
        elif sy > max_span:
            cy = (self.y_min + self.y_max) / 2
            self.y_min, self.y_max = cy - max_span / 2, cy + max_span / 2

    def _pinch_zoom_pan_point(self, c_new, d_new):
        """One frame of two-finger pan+zoom in Point mode. Anchor on the
        previous centroid so pan and zoom compose without drift."""
        c_prev = self._point_pan_anchor
        d_prev = self._point_prev_dist
        if c_prev is None or d_prev is None or d_new is None or d_new <= 0:
            return
        wx_anchor, wy_anchor = self._s2w(*c_prev)
        k = d_prev / d_new
        k = max(0.2, min(5.0, k))
        self.x_min = wx_anchor + (self.x_min - wx_anchor) * k
        self.x_max = wx_anchor + (self.x_max - wx_anchor) * k
        self.y_min = wy_anchor + (self.y_min - wy_anchor) * k
        self.y_max = wy_anchor + (self.y_max - wy_anchor) * k
        dx_screen = c_new[0] - c_prev[0]
        dy_screen = c_new[1] - c_prev[1]
        dx_world = (dx_screen / max(1.0, self.width)
                    * (self.x_max - self.x_min))
        dy_world = (dy_screen / max(1.0, self.height)
                    * (self.y_max - self.y_min))
        self.x_min -= dx_world
        self.x_max -= dx_world
        self.y_min -= dy_world
        self.y_max -= dy_world
        self._clamp_view_span()
        self._point_pan_anchor = c_new
        self._point_prev_dist = d_new
        self._redraw()

    def _schedule_view_changed(self):
        if self._view_debounce:
            self._view_debounce.cancel()

        def _fire(dt):
            self._view_debounce = None
            if self.on_view_changed:
                self.on_view_changed()

        self._view_debounce = Clock.schedule_once(_fire, 0.35)

    def _zoom(self, factor, pivot_px):
        wx, wy = self._s2w(*pivot_px)
        self.x_min = wx + (self.x_min - wx) * factor
        self.x_max = wx + (self.x_max - wx) * factor
        self.y_min = wy + (self.y_min - wy) * factor
        self.y_max = wy + (self.y_max - wy) * factor
        self._clamp_view_span()
        self._redraw()
        self._schedule_view_changed()

    # ── touch ──────────────────────────────────────────────────────────

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        if getattr(touch, "is_mouse_scrolling", False):
            if self._warp_active:
                factor = 1.15 if touch.button == "scrollup" else 1 / 1.15
                if self.on_warp_radius:
                    self.on_warp_radius(factor)
            elif touch.button == "scrollup":
                self._zoom(1 / 1.2, touch.pos)
            elif touch.button == "scrolldown":
                self._zoom(1.2, touch.pos)
            return True

        if self._warp_active:
            if touch.uid != self._warp_primary_uid:
                self._warp_touches[touch.uid] = touch.pos
                self._pinch_last_dist = self._pinch_dist()
            return True

        if self.mode == "point":
            self._point_touches[touch.uid] = touch.pos
            if self._point_multi:
                self._point_pan_anchor = self._point_centroid()
                self._point_prev_dist = self._point_dist()
                return True
            if len(self._point_touches) >= 2:
                self._point_multi = True
                self._point_candidate_px = None
                self._point_moved = False
                self._point_pan_anchor = self._point_centroid()
                self._point_prev_dist = self._point_dist()
                self._redraw()
                return True
            self._point_candidate_px = touch.pos
            self._point_moved = False
            self._redraw()
            return True

        if self.mode == "pencil":
            self._pencil_touches[touch.uid] = touch.pos
            if self._pencil_multi:
                self._pencil_pan_anchor = self._pencil_centroid()
                return True
            if len(self._pencil_touches) >= 2:
                self._pencil_multi = True
                if self._stroke_px is not None:
                    self._stroke_px = None
                    self._redraw()
                self._pencil_pan_anchor = self._pencil_centroid()
                return True
            self._stroke_px = [touch.pos]
            self._redraw()
            return True

        # pan mode: try warp before falling through to pan
        hit_i = self._hit_test_curve(touch.pos)
        if hit_i is not None and self.on_warp_start:
            wx, wy = self._s2w(*touch.pos)
            if self.on_warp_start(hit_i, (wx, wy)):
                self._warp_active = True
                self._warp_primary_uid = touch.uid
                self._warp_touches = {touch.uid: touch.pos}
                self._pinch_last_dist = None
                return True

        self._drag = (touch.x, touch.y,
                      self.x_min, self.x_max, self.y_min, self.y_max)
        return True

    def on_touch_move(self, touch):
        # warp takes priority
        if self._warp_active and touch.uid in self._warp_touches:
            self._warp_touches[touch.uid] = touch.pos
            if len(self._warp_touches) >= 2:
                d = self._pinch_dist()
                if d and self._pinch_last_dist:
                    factor = d / self._pinch_last_dist
                    if self.on_warp_radius:
                        self.on_warp_radius(factor)
                self._pinch_last_dist = d
                return True
            if self.on_warp_move:
                self.on_warp_move(self._s2w(*touch.pos))
            return True

        # point mode
        if self.mode == "point" and touch.uid in self._point_touches:
            self._point_touches[touch.uid] = touch.pos
            if self._point_multi:
                new_center = self._point_centroid()
                new_dist = self._point_dist()
                if new_center is not None and new_dist is not None:
                    self._pinch_zoom_pan_point(new_center, new_dist)
                elif new_center is not None:
                    if self._point_pan_anchor is not None:
                        dx = ((new_center[0] - self._point_pan_anchor[0])
                              / max(1.0, self.width)
                              * (self.x_max - self.x_min))
                        dy = ((new_center[1] - self._point_pan_anchor[1])
                              / max(1.0, self.height)
                              * (self.y_max - self.y_min))
                        self.x_min -= dx
                        self.x_max -= dx
                        self.y_min -= dy
                        self.y_max -= dy
                        self._point_pan_anchor = new_center
                        self._redraw()
                return True
            if (not self._point_moved
                    and self._point_candidate_px is not None):
                cx, cy = self._point_candidate_px
                d = math.hypot(touch.x - cx, touch.y - cy)
                if d > self._point_move_threshold:
                    self._point_moved = True
                    self._redraw()
            return True

        # pencil mode
        if self.mode == "pencil" and touch.uid in self._pencil_touches:
            self._pencil_touches[touch.uid] = touch.pos
            if self._pencil_multi:
                new_center = self._pencil_centroid()
                if (self._pencil_pan_anchor is not None
                        and new_center is not None):
                    dx = ((new_center[0] - self._pencil_pan_anchor[0])
                          / max(1.0, self.width)
                          * (self.x_max - self.x_min))
                    dy = ((new_center[1] - self._pencil_pan_anchor[1])
                          / max(1.0, self.height)
                          * (self.y_max - self.y_min))
                    self.x_min -= dx
                    self.x_max -= dx
                    self.y_min -= dy
                    self.y_max -= dy
                    self._pencil_pan_anchor = new_center
                    self._redraw()
                return True
            if self._stroke_px is not None:
                self._stroke_px.append(touch.pos)
                self._redraw()
            return True

        # pan
        if self._drag is None:
            return super().on_touch_move(touch)
        sx, sy, xmin0, xmax0, ymin0, ymax0 = self._drag
        dx = (touch.x - sx) / max(1.0, self.width) * (xmax0 - xmin0)
        dy = (touch.y - sy) / max(1.0, self.height) * (ymax0 - ymin0)
        self.x_min = xmin0 - dx
        self.x_max = xmax0 - dx
        self.y_min = ymin0 - dy
        self.y_max = ymax0 - dy
        self._redraw()
        return True

    def on_touch_up(self, touch):
        if self._warp_active and touch.uid in self._warp_touches:
            del self._warp_touches[touch.uid]
            self._pinch_last_dist = self._pinch_dist()
            if touch.uid == self._warp_primary_uid:
                self._warp_active = False
                self._warp_primary_uid = None
                self._warp_touches = {}
                self._pinch_last_dist = None
                if self.on_warp_end:
                    self.on_warp_end()
            return True

        if self.mode == "point" and touch.uid in self._point_touches:
            self._point_touches[touch.uid] = touch.pos
            del self._point_touches[touch.uid]
            if self._point_multi:
                if self._point_touches:
                    self._point_pan_anchor = self._point_centroid()
                    self._point_prev_dist = self._point_dist()
                else:
                    self._point_multi = False
                    self._point_pan_anchor = None
                    self._point_prev_dist = None
                    self._point_candidate_px = None
                    self._point_moved = False
                    self._schedule_view_changed()
                return True
            if (self._point_candidate_px is not None
                    and not self._point_moved):
                wx, wy = self._s2w(*touch.pos)
                self.points.append((wx, wy))
                self.fit = None
                if self.on_points_changed:
                    self.on_points_changed()
            self._point_candidate_px = None
            self._point_moved = False
            self._redraw()
            return True

        if self.mode == "pencil" and touch.uid in self._pencil_touches:
            del self._pencil_touches[touch.uid]
            if self._pencil_multi:
                if self._pencil_touches:
                    self._pencil_pan_anchor = self._pencil_centroid()
                else:
                    self._pencil_multi = False
                    self._pencil_pan_anchor = None
                    self._stroke_px = None
                    self._schedule_view_changed()
                return True
            stroke_px = list(self._stroke_px or [])
            self._stroke_px = None
            self._redraw()
            if self.on_stroke_done and len(stroke_px) >= 4:
                world = [self._s2w(px, py) for px, py in stroke_px]
                self.on_stroke_done(world)
            return True

        self._drag = None
        self._schedule_view_changed()
        return super().on_touch_up(touch)


# ══════════════════════════════════════════════════════════════════════════
# UI helper widgets
# ══════════════════════════════════════════════════════════════════════════

class ColorDot(Widget):
    def __init__(self, color, **kw):
        super().__init__(size_hint_x=None, width=dp(22), **kw)
        with self.canvas:
            Color(*color)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size


class FunctionRow(BoxLayout):
    kind = "expr"

    def __init__(self, color, on_change, on_delete, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(42), spacing=dp(4), **kw)
        self.color = color
        self.on_change = on_change
        self.mode = "y"
        self.lhs = self.rhs = self.rhs2 = self.range_in = None

        self.mode_sp = Spinner(
            text="y =", values=("y =", "x,y(t)", "r(\u03b8)"),
            size_hint_x=None, width=dp(72), font_size=11)
        self.mode_sp.bind(text=self._on_mode_pick)
        self.add_widget(self.mode_sp)

        self.body = BoxLayout(orientation="horizontal", spacing=dp(4))
        self.add_widget(self.body)
        self._build_body()

        self.add_widget(ColorDot(color))
        del_btn = Button(text="\u2715", size_hint_x=None, width=dp(30),
                         font_size=13, background_color=(0.55, 0.12, 0.12, 1))
        del_btn.bind(on_release=lambda *a: on_delete(self))
        self.add_widget(del_btn)

    def _on_mode_pick(self, sp, text):
        self.mode = {"y =": "y", "x,y(t)": "param",
                     "r(\u03b8)": "polar"}.get(text, "y")
        self._build_body()
        self.on_change(self)

    def _bind(self, w):
        w.bind(text=lambda *a: self.on_change(self))
        return w

    def _build_body(self):
        self.body.clear_widgets()
        self.lhs = self.rhs = self.rhs2 = self.range_in = None

        if self.mode == "y":
            self.lhs = self._bind(TextInput(
                text="f(x)", multiline=False, font_size=13,
                size_hint_x=None, width=dp(52)))
            self.rhs = self._bind(TextInput(
                multiline=False, font_size=13, hint_text="sin(x)/x"))
            self.body.add_widget(self.lhs)
            self.body.add_widget(Label(text="=", size_hint_x=None, width=dp(10)))
            self.body.add_widget(self.rhs)

        elif self.mode == "param":
            self.lhs = self._bind(TextInput(
                text="x(t)", multiline=False, font_size=12,
                size_hint_x=None, width=dp(50)))
            self.rhs = self._bind(TextInput(
                multiline=False, font_size=12, hint_text="cos(t)"))
            self.rhs2 = self._bind(TextInput(
                multiline=False, font_size=12, hint_text="sin(t)"))
            self.range_in = self._bind(TextInput(
                text="0, 6.283", multiline=False, font_size=11,
                size_hint_x=None, width=dp(76)))
            self.body.add_widget(self.lhs)
            self.body.add_widget(Label(text="=", size_hint_x=None, width=dp(10)))
            self.body.add_widget(self.rhs)
            self.body.add_widget(Label(text=",", size_hint_x=None, width=dp(8)))
            self.body.add_widget(self.rhs2)
            self.body.add_widget(self.range_in)

        else:  # polar
            self.lhs = self._bind(TextInput(
                text="r(\u03b8)", multiline=False, font_size=12,
                size_hint_x=None, width=dp(50)))
            self.rhs = self._bind(TextInput(
                multiline=False, font_size=12,
                hint_text="1 + cos(\u03b8)"))
            self.range_in = self._bind(TextInput(
                text="0, 6.283", multiline=False, font_size=11,
                size_hint_x=None, width=dp(76)))
            self.body.add_widget(self.lhs)
            self.body.add_widget(Label(text="=", size_hint_x=None, width=dp(10)))
            self.body.add_widget(self.rhs)
            self.body.add_widget(self.range_in)

    def get_entry(self):
        if self.mode == "y":
            expr = self.rhs.text.strip()
            entry = {"kind": "expr", "mode": "y",
                     "name": self.lhs.text.strip() or "f(x)",
                     "expr": expr, "color": self.color,
                     "visible": bool(expr), "fn": None, "error": None}
            if expr:
                try:
                    entry["fn"] = compile_expr(expr, var="x")
                except ExprError as e:
                    entry["error"] = str(e)
                    entry["visible"] = False
            self.rhs.foreground_color = ((1, 0.4, 0.4, 1) if entry["error"]
                                         else (1, 1, 1, 1))
            return entry

        if self.mode == "param":
            ex = self.rhs.text.strip()
            ey = self.rhs2.text.strip()
            lo, hi = parse_range(self.range_in.text)
            entry = {"kind": "expr", "mode": "param",
                     "name": "x,y(t)", "expr": f"{ex} ; {ey}",
                     "t_lo": lo, "t_hi": hi, "color": self.color,
                     "visible": bool(ex and ey),
                     "fn_x": None, "fn_y": None, "error": None}
            if ex and ey:
                try:
                    entry["fn_x"] = compile_expr(ex, var="t")
                    entry["fn_y"] = compile_expr(ey, var="t")
                except ExprError as e:
                    entry["error"] = str(e)
                    entry["visible"] = False
            self.rhs.foreground_color = ((1, 0.4, 0.4, 1) if entry["error"]
                                         else (1, 1, 1, 1))
            return entry

        er = self.rhs.text.strip()
        lo, hi = parse_range(self.range_in.text)
        entry = {"kind": "expr", "mode": "polar",
                 "name": "r(\u03b8)", "expr": er,
                 "t_lo": lo, "t_hi": hi, "color": self.color,
                 "visible": bool(er), "fn": None, "error": None}
        if er:
            try:
                entry["fn"] = compile_expr(er, var="t")
            except ExprError as e:
                entry["error"] = str(e)
                entry["visible"] = False
        self.rhs.foreground_color = ((1, 0.4, 0.4, 1) if entry["error"]
                                     else (1, 1, 1, 1))
        return entry


class SplineRow(BoxLayout):
    """Non-editable row for a pencil-drawn spline."""
    kind = "spline"

    def __init__(self, color, points, on_delete, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(42), spacing=dp(4), **kw)
        self.color = color
        self.points = list(points)
        self._fn = make_spline(points)

        self.add_widget(Label(text="\u270e spline",
                              size_hint_x=None, width=dp(70),
                              font_size=13, color=(0.9, 0.9, 0.6, 1)))
        self.add_widget(Label(text=f"{len(points)} pts",
                              font_size=12,
                              color=(0.7, 0.75, 0.8, 1)))
        self.add_widget(ColorDot(color))

        del_btn = Button(text="\u2715", size_hint_x=None, width=dp(30),
                         font_size=13, background_color=(0.55, 0.12, 0.12, 1))
        del_btn.bind(on_release=lambda *a: on_delete(self))
        self.add_widget(del_btn)

    def get_entry(self):
        return {"kind": "spline", "name": "spline",
                "color": self.color, "visible": bool(self._fn),
                "fn": self._fn, "points": self.points, "error": None}


class PiecewiseRow(BoxLayout):
    """Non-editable row for a pencil stroke split at discontinuities."""
    kind = "piecewise"

    def __init__(self, color, pieces, on_delete, on_convert=None, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(42), spacing=dp(4), **kw)
        self.color = color
        norm = []
        for p in pieces:
            if isinstance(p, tuple) and len(p) == 3 and isinstance(p[2], list):
                norm.append(list(p[2]))
            else:
                norm.append(list(p))
        self.pieces = norm
        self.on_convert = on_convert
        self._rebuild()

        n = len(self.pieces)
        self.add_widget(Label(text=f"\u270e piecewise \u00b7 {n}",
                              size_hint_x=None, width=dp(120),
                              font_size=13, color=(0.9, 0.9, 0.6, 1)))
        self.add_widget(Label(text=f"{sum(len(p) for p in self.pieces)} pts",
                              font_size=12,
                              color=(0.7, 0.75, 0.8, 1)))
        self.add_widget(ColorDot(color))
        if on_convert is not None:
            conv = Button(text="\u2192expr", size_hint_x=None, width=dp(52),
                          font_size=11,
                          background_color=(0.3, 0.3, 0.5, 1))
            conv.bind(on_release=lambda *a: on_convert(self))
            self.add_widget(conv)
        del_btn = Button(text="\u2715", size_hint_x=None, width=dp(30),
                         font_size=13, background_color=(0.55, 0.12, 0.12, 1))
        del_btn.bind(on_release=lambda *a: on_delete(self))
        self.add_widget(del_btn)

    def _rebuild(self):
        compiled = []
        for binned in self.pieces:
            sfn = make_spline(binned)
            if sfn is None:
                continue
            compiled.append((binned[0][0], binned[-1][0], sfn))
        compiled.sort(key=lambda c: c[0])
        self._compiled = compiled

        def f(x, _c=compiled):
            for lo, hi, sfn in _c:
                if lo - 1e-9 <= x <= hi + 1e-9:
                    return sfn(x)
            return None

        self._fn = f if compiled else None

    def get_entry(self):
        return {"kind": "piecewise", "name": "piecewise",
                "color": self.color, "visible": bool(self._fn),
                "fn": self._fn, "pieces": self.pieces, "error": None}


# ══════════════════════════════════════════════════════════════════════════
# Screen
# ══════════════════════════════════════════════════════════════════════════

class FunctionPlotterScreen(Screen):
    title = "Function Plotter"
    MAX_UNDO = 50
    MAX_VIEW_UNDO = 50

    def __init__(self, **kw):
        super().__init__(**kw)
        self._rows = []
        self._color_i = 0
        self._sync_ev = None
        self._warp = None
        self._warp_bounds = (0.01, 1.0)
        self._undo = []
        self._redo = []
        self._last_snap = None
        self._restoring = False
        self._history_popup = None
        self._view_undo = []
        self._view_redo = []
        self._view_last = None
        self._build()

    # ── build ──────────────────────────────────────────────────────────

    def _next_color(self):
        c = PALETTE[self._color_i % len(PALETTE)]
        self._color_i += 1
        return c

    def _build(self):
        root = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))

        self.graph = GraphCanvas(size_hint=(1, 1))
        root.add_widget(self.graph)

        tb = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
        b_view = Button(text="View \u25be  (0/0)", font_size=11)
        b_view.bind(on_release=lambda *a: self._open_view_menu())
        self._b_view = b_view
        tb.add_widget(b_view)
        for label, cb in (
            ("Clear pts", lambda *a: self.graph.clear_points()),
            ("Fit poly", lambda *a: self._fit()),
            ("Fill", lambda *a: self._open_fill_popup()),
            ("PNG", lambda *a: self._export_png()),
        ):
            b = Button(text=label, font_size=11)
            b.bind(on_release=cb)
            tb.add_widget(b)
        root.add_widget(tb)

        mode_bar = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        b_undo = Button(text="\u21b6", font_size=14, size_hint_x=None,
                        width=dp(38))
        b_undo.bind(on_release=lambda *a: self._do_undo())
        b_redo = Button(text="\u21b7", font_size=14, size_hint_x=None,
                        width=dp(38))
        b_redo.bind(on_release=lambda *a: self._do_redo())
        b_hist = Button(text="\u2630", font_size=14, size_hint_x=None,
                        width=dp(38))
        b_hist.bind(on_release=lambda *a: self._open_history())
        mode_bar.add_widget(b_undo)
        mode_bar.add_widget(b_redo)
        mode_bar.add_widget(b_hist)
        for mode_name, label in (("pan", "Pan"), ("point", "Point"),
                                 ("pencil", "Pencil")):
            b = ToggleButton(text=label, font_size=11, group="mode")
            if mode_name == "pan":
                b.state = "down"
            b.bind(on_release=lambda btn, m=mode_name: self._set_mode(m))
            mode_bar.add_widget(b)
        root.add_widget(mode_bar)

        sv = ScrollView(size_hint_y=None, height=dp(140))
        self.rows_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                  spacing=dp(3), padding=dp(2))
        self.rows_box.bind(minimum_height=self.rows_box.setter("height"))
        sv.add_widget(self.rows_box)
        root.add_widget(sv)

        self.fit_lbl = Label(text="", font_size=11, size_hint_y=None,
                             height=dp(20), color=(0.6, 1, 0.7, 1))
        root.add_widget(self.fit_lbl)

        bb = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
        b_add = Button(text="+ Add function", font_size=12,
                       background_color=(0.2, 0.5, 0.25, 1))
        b_add.bind(on_release=lambda *a: self._add_row())
        b_help = Button(text="?", font_size=14, size_hint_x=None, width=dp(40))
        b_help.bind(on_release=lambda *a: self._show_help())
        b_back = Button(text="Back", font_size=12, size_hint_x=None, width=dp(70))
        b_back.bind(on_release=lambda *a: setattr(
            self.manager, "current", "dashboard"))
        bb.add_widget(b_add)
        bb.add_widget(b_help)
        bb.add_widget(b_back)
        root.add_widget(bb)

        self.add_widget(root)

        # callback wiring
        self.graph.on_stroke_done = self._on_stroke_done
        self.graph.on_warp_start = self._warp_start
        self.graph.on_warp_move = self._warp_move
        self.graph.on_warp_end = self._warp_end
        self.graph.on_warp_radius = self._warp_radius
        self.graph.on_points_changed = self._commit_undo
        self.graph.on_view_changed = self._on_view_changed

        Clock.schedule_once(lambda dt: self._seed_initial(), 0)

        self._add_row("sin(x)")
        self._add_row("x^2 / 4 - 3")

        Window.bind(on_key_down=self._on_key_down)

    def _seed_initial(self):
        self._last_snap = self._snapshot()
        self._view_last = self._graph_view()
        self._refresh_view_button()

    # ── rows ───────────────────────────────────────────────────────────

    def _add_row(self, default=""):
        row = FunctionRow(self._next_color(), self._on_row_change,
                          self._on_row_delete)
        row.rhs.text = default
        self._rows.append(row)
        self.rows_box.add_widget(row)
        self._on_row_change(row)
        return row

    def _add_spline_row(self, points):
        row = SplineRow(self._next_color(), points, self._on_row_delete)
        self._rows.append(row)
        self.rows_box.add_widget(row)
        self._sync()

    def _add_piecewise_row(self, pieces):
        row = PiecewiseRow(self._next_color(), pieces, self._on_row_delete,
                           on_convert=self._piecewise_to_expr)
        self._rows.append(row)
        self.rows_box.add_widget(row)
        self._sync()

    def _on_row_delete(self, row):
        if row in self._rows:
            self._rows.remove(row)
            self.rows_box.remove_widget(row)
            self._sync()

    def _on_row_change(self, row):
        if self._restoring:
            return
        if self._sync_ev:
            self._sync_ev.cancel()
        self._sync_ev = Clock.schedule_once(lambda dt: self._sync(), 0.15)

    def _sync(self):
        self._sync_ev = None
        funcs = []
        for row in self._rows:
            e = row.get_entry()
            row._entry = e
            funcs.append(e)
        self.graph.set_functions(funcs)
        self._commit_undo()

    # ── undo/redo (content) ────────────────────────────────────────────

    def _serialize_rows(self):
        out = []
        for row in self._rows:
            if row.kind == "spline":
                out.append({"kind": "spline",
                            "color": row.color,
                            "points": list(row.points)})
            elif row.kind == "piecewise":
                out.append({"kind": "piecewise",
                            "color": row.color,
                            "pieces": [list(p) for p in row.pieces]})
            else:
                d = {"kind": "expr", "mode": row.mode, "color": row.color}
                if row.mode == "y":
                    d["lhs"] = row.lhs.text
                    d["rhs"] = row.rhs.text
                elif row.mode == "param":
                    d["lhs"] = row.lhs.text
                    d["rhs"] = row.rhs.text
                    d["rhs2"] = row.rhs2.text
                    d["range"] = row.range_in.text
                else:
                    d["lhs"] = row.lhs.text
                    d["rhs"] = row.rhs.text
                    d["range"] = row.range_in.text
                out.append(d)
        return out

    def _snapshot(self):
        return {
            "rows": self._serialize_rows(),
            "points": list(self.graph.points),
        }

    def _describe_diff(self, prev, cur):
        pr, cr = prev["rows"], cur["rows"]
        pp, cp = prev["points"], cur["points"]
        if len(cr) > len(pr):
            return "Add row"
        if len(cr) < len(pr):
            return "Delete row"
        if len(cp) > len(pp):
            return f"Place point ({len(cp)})"
        if len(cp) < len(pp):
            return "Clear points"
        for a, b in zip(pr, cr):
            if a.get("kind") != b.get("kind"):
                return "Change row kind"
            if a.get("mode") != b.get("mode"):
                return "Change row mode"
            if a.get("kind") == "piecewise":
                if a.get("pieces") != b.get("pieces"):
                    return "Edit piecewise"
            elif a.get("kind") == "spline":
                if a.get("points") != b.get("points"):
                    return "Warp spline"
            else:
                if a.get("rhs") != b.get("rhs"):
                    return f"Edit {b.get('lhs') or 'expr'}"
                if a.get("rhs2") != b.get("rhs2"):
                    return "Edit param y(t)"
        return "Edit"

    def _commit_undo(self):
        if self._restoring:
            return
        cur = self._snapshot()
        if self._last_snap is None:
            self._last_snap = cur
            return
        if cur == self._last_snap:
            return
        label = self._describe_diff(self._last_snap, cur)
        self._undo.append((label, self._last_snap))
        if len(self._undo) > self.MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()
        self._last_snap = cur
        self._refresh_history()

    def _restore(self, snap):
        self._restoring = True
        try:
            for row in list(self._rows):
                self.rows_box.remove_widget(row)
            self._rows = []
            for r in snap["rows"]:
                if r["kind"] == "spline":
                    row = SplineRow(r["color"], r["points"],
                                    self._on_row_delete)
                elif r["kind"] == "piecewise":
                    row = PiecewiseRow(r["color"], r["pieces"],
                                       self._on_row_delete)
                else:
                    row = FunctionRow(r["color"], self._on_row_change,
                                      self._on_row_delete)
                    mode = r.get("mode", "y")
                    sp_text = {"y": "y =", "param": "x,y(t)",
                               "polar": "r(\u03b8)"}[mode]
                    if row.mode_sp.text != sp_text:
                        row.mode_sp.text = sp_text
                    if mode == "y":
                        row.lhs.text = r["lhs"]
                        row.rhs.text = r["rhs"]
                    elif mode == "param":
                        row.lhs.text = r["lhs"]
                        row.rhs.text = r["rhs"]
                        row.rhs2.text = r["rhs2"]
                        row.range_in.text = r["range"]
                    else:
                        row.lhs.text = r["lhs"]
                        row.rhs.text = r["rhs"]
                        row.range_in.text = r["range"]
                self._rows.append(row)
                self.rows_box.add_widget(row)
            self.graph.points = list(snap["points"])
            self.graph.fit = None
        finally:
            self._restoring = False
        self._sync()
        self._last_snap = self._snapshot()

    def _do_undo(self):
        if not self._undo:
            self.fit_lbl.text = "Nothing to undo."
            return
        label, snap = self._undo.pop()
        self._redo.append((label, self._snapshot()))
        self._restore(snap)
        self.fit_lbl.text = f"Undo: {label}"
        self._refresh_history()

    def _do_redo(self):
        if not self._redo:
            self.fit_lbl.text = "Nothing to redo."
            return
        label, snap = self._redo.pop()
        self._undo.append((label, self._snapshot()))
        self._restore(snap)
        self.fit_lbl.text = f"Redo: {label}"
        self._refresh_history()

    def _jump_to_undo_index(self, i):
        if not (0 <= i < len(self._undo)):
            return
        fwd = self._snapshot()
        while len(self._undo) > i:
            label, snap = self._undo.pop()
            self._redo.append((label, fwd))
            fwd = snap
        self._restore(fwd)
        self.fit_lbl.text = f"Jumped to undo #{i + 1}"
        self._refresh_history()

    def _jump_to_redo_index(self, i):
        if not (0 <= i < len(self._redo)):
            return
        skipped = []
        while len(self._redo) - 1 > i:
            skipped.append(self._redo.pop())
        label, snap = self._redo.pop()
        for slabel, ssnap in reversed(skipped):
            self._undo.append((slabel, ssnap))
        self._redo.append((label, self._snapshot()))
        self._restore(snap)
        self.fit_lbl.text = f"Jumped forward: {label}"
        self._refresh_history()

    # ── history panel ─────────────────────────────────────────────────

    def _refresh_history(self):
        if self._history_popup is not None:
            self._history_popup.dismiss()
            self._history_popup = None
            self._open_history()

    def _open_history(self):
        sv = ScrollView()
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        spacing=dp(2), padding=dp(4))
        box.bind(minimum_height=box.setter("height"))

        def make_row(text, enabled, on_click=None, bg=(0.2, 0.25, 0.32, 1)):
            b = Button(text=text, size_hint_y=None, height=dp(34),
                       font_size=11, halign="left", valign="middle",
                       background_color=bg)
            b.bind(size=lambda *a: setattr(
                b, "text_size", (b.width - dp(10), None)))
            if enabled and on_click:
                b.bind(on_release=on_click)
            else:
                b.disabled = True
            return b

        popup = Popup(title="History", content=sv,
                      size_hint=(0.8, 0.7))
        box.add_widget(make_row("\u25cf Current state", False,
                                bg=(0.15, 0.42, 0.25, 1)))

        for rev in range(len(self._undo)):
            i = len(self._undo) - 1 - rev
            label, _snap = self._undo[i]
            b = make_row(f"\u21b6  {label}", True,
                         on_click=lambda inst, idx=i: (
                             popup.dismiss(),
                             self._jump_to_undo_index(idx)))
            box.add_widget(b)

        for rev in range(len(self._redo)):
            i = len(self._redo) - 1 - rev
            label, _snap = self._redo[i]
            b = make_row(f"\u21b7  {label}", True,
                         on_click=lambda inst, idx=i: (
                             popup.dismiss(),
                             self._jump_to_redo_index(idx)),
                         bg=(0.18, 0.2, 0.26, 1))
            box.add_widget(b)

        self._history_popup = popup
        popup.bind(on_dismiss=lambda *a: setattr(
            self, "_history_popup", None))
        popup.open()

    # ── view undo (pan/zoom only) ──────────────────────────────────────

    def _graph_view(self):
        g = self.graph
        return (g.x_min, g.x_max, g.y_min, g.y_max)

    def _apply_view(self, v):
        g = self.graph
        g.x_min, g.x_max, g.y_min, g.y_max = v
        g._redraw()

    def _on_view_changed(self):
        cur = self._graph_view()
        if self._view_last is None:
            self._view_last = cur
            return
        if cur == self._view_last:
            return
        self._view_undo.append(self._view_last)
        if len(self._view_undo) > self.MAX_VIEW_UNDO:
            self._view_undo.pop(0)
        self._view_redo.clear()
        self._view_last = cur
        self._refresh_view_button()

    def _do_view_undo(self):
        if not self._view_undo:
            self.fit_lbl.text = "No view changes to undo."
            return
        cur = self._graph_view()
        snap = self._view_undo.pop()
        self._view_redo.append(cur)
        self._apply_view(snap)
        self._view_last = snap
        self.fit_lbl.text = f"View undo ({len(self._view_undo)} left)"
        self._refresh_view_button()

    def _do_view_redo(self):
        if not self._view_redo:
            self.fit_lbl.text = "No view changes to redo."
            return
        cur = self._graph_view()
        snap = self._view_redo.pop()
        self._view_undo.append(cur)
        self._apply_view(snap)
        self._view_last = snap
        self.fit_lbl.text = f"View redo ({len(self._view_redo)} left)"
        self._refresh_view_button()

    def _do_view_reset(self):
        self.graph.reset_view()
        self.graph._schedule_view_changed()

    def _refresh_view_button(self):
        b = getattr(self, "_b_view", None)
        if b is not None:
            u = len(self._view_undo)
            r = len(self._view_redo)
            b.text = f"View \u25be  ({u}/{r})"

    def _open_view_menu(self):
        layout = BoxLayout(orientation="vertical", spacing=dp(6),
                           padding=dp(8))
        u = len(self._view_undo)
        r = len(self._view_redo)
        for label, cb, bg in (
            (f"Undo view  ({u})", self._do_view_undo, (0.2, 0.3, 0.45, 1)),
            (f"Redo view  ({r})", self._do_view_redo, (0.2, 0.3, 0.45, 1)),
            ("Reset to default", self._do_view_reset, (0.28, 0.35, 0.2, 1)),
        ):
            b = Button(text=label, size_hint_y=None, height=dp(42),
                       font_size=13, background_color=bg)
            b.bind(on_release=lambda inst, fn=cb: (popup.dismiss(), fn()))
            layout.add_widget(b)
        popup = Popup(title="View history", content=layout,
                      size_hint=(0.6, None), height=dp(210))
        popup.open()

    # ── fit poly ───────────────────────────────────────────────────────

    def _fit_poly_to_points(self, points, deg_text):
        try:
            deg = int(deg_text)
        except ValueError:
            deg = 6
        deg = max(1, min(deg, len(points) - 1))
        while deg >= 1:
            coefs = poly_fit([p[0] for p in points],
                             [p[1] for p in points], deg)
            if coefs is not None:
                return coefs, deg
            deg -= 1
        return None, 0

    def _fit(self):
        pts = self.graph.points
        if len(pts) < 2:
            self.fit_lbl.text = "Place at least 2 points first."
            return
        coefs, deg = self._fit_poly_to_points(pts, "6")
        if coefs is None:
            self.fit_lbl.text = "Could not fit a polynomial."
            return
        self.fit_lbl.text = f"Fit (deg {deg}): y = {poly_to_str(coefs)}"

        def fit_fn(x, _c=coefs):
            r = 0.0
            for k, c in enumerate(_c):
                r += c * (x ** k)
            return r

        self.graph.fit = {"fn": fit_fn, "color": (1, 0.4, 0.8, 1)}
        self.graph._redraw()
        row = self._add_row(poly_to_expr(coefs))
        row.lhs.text = "fit(x)"

    # ── pencil stroke popup ────────────────────────────────────────────

    def _on_stroke_done(self, world_pts):
        Clock.schedule_once(lambda dt: self._stroke_popup(world_pts), 0)

    def _stroke_popup(self, world_pts):
        g = self.graph
        y_jump = (g.y_max - g.y_min) * 0.20
        segments = stroke_to_piecewise(world_pts, y_jump)
        if not segments:
            return
        n_seg = len(segments)
        is_piecewise = n_seg >= 2

        info = Label(
            text=(f"Captured {len(world_pts)} samples in {n_seg} "
                  f"segment{'s' if n_seg != 1 else ''}."),
            size_hint_y=None, height=dp(22), font_size=12)

        spline_label = ("Piecewise spline (recommended)" if is_piecewise
                        else "Smooth curve (spline)")
        spline_btn = Button(text=spline_label, font_size=13,
                            size_hint_y=None, height=dp(44),
                            background_color=(0.2, 0.45, 0.7, 1))

        deg_sp = Spinner(text="6",
                         values=("2", "3", "4", "5", "6", "7", "8", "10", "12"),
                         size_hint_x=None, width=dp(60), font_size=13)
        poly_btn = Button(text="Polynomial fit", font_size=13,
                          size_hint_y=None, height=dp(44),
                          background_color=(0.25, 0.55, 0.3, 1))
        poly_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        poly_row.add_widget(Label(text="deg", size_hint_x=None,
                                  width=dp(34), font_size=12))
        poly_row.add_widget(deg_sp)
        poly_row.add_widget(poly_btn)

        cancel = Button(text="Cancel", size_hint_y=None, height=dp(38),
                        font_size=12)

        layout = BoxLayout(orientation="vertical", spacing=dp(6),
                           padding=dp(8))
        for w in (info, spline_btn, poly_row, cancel):
            layout.add_widget(w)
        popup = Popup(title="Convert stroke to function",
                      content=layout, size_hint=(0.85, None),
                      height=dp(240))

        def do_spline(*a):
            popup.dismiss()
            if is_piecewise:
                _fn, pieces = make_piecewise_spline(segments)
                if not pieces:
                    self.fit_lbl.text = "Couldn't build piecewise curve."
                    return
                self._add_piecewise_row(pieces)
            else:
                binned = stroke_to_xy(segments[0])
                if len(binned) < 2:
                    self.fit_lbl.text = "Stroke too short."
                    return
                self._add_spline_row(binned)

        def do_poly(*a):
            popup.dismiss()
            binned_all = []
            for seg in segments:
                binned_all.extend(stroke_to_xy(seg))
            if len(binned_all) < 2:
                self.fit_lbl.text = "Stroke too short."
                return
            coefs, deg = self._fit_poly_to_points(binned_all, deg_sp.text)
            if coefs is None:
                self.fit_lbl.text = "Could not fit polynomial."
                return
            row = self._add_row(poly_to_expr(coefs))
            row.lhs.text = f"pencil_{len(self._rows)}"
            self.fit_lbl.text = (f"Pencil \u2192 poly deg {deg}: "
                                 f"y = {poly_to_str(coefs)}")

        spline_btn.bind(on_release=do_spline)
        poly_btn.bind(on_release=do_poly)
        cancel.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    # ── warp ───────────────────────────────────────────────────────────

    def _warp_start(self, entry_idx, world_xy):
        if entry_idx >= len(self._rows):
            return False
        row = self._rows[entry_idx]
        if row.kind == "piecewise":
            return False
        if getattr(row, "mode", "y") in ("param", "polar"):
            return False
        g = self.graph
        span = g.x_max - g.x_min
        radius_world = span * 0.12
        self._warp_bounds = (span * 0.03, span * 0.60)

        if row.kind == "spline":
            self._warp = {
                "row": row, "kind": "spline",
                "orig_points": list(row.points),
                "grab_world": world_xy,
                "radius_world": radius_world,
                "base_radius_world": radius_world,
            }
            return True

        entry = getattr(row, "_entry", None)
        if not entry or not entry.get("fn"):
            return False
        n = 80
        pts = []
        for i in range(n):
            wx = g.x_min + (g.x_max - g.x_min) * i / (n - 1)
            try:
                wy = entry["fn"](wx)
            except Exception:
                continue
            if not isinstance(wy, (int, float)) or not math.isfinite(wy):
                continue
            pts.append((wx, wy))
        if len(pts) < 6:
            return False
        self._warp = {
            "row": row, "kind": "expr",
            "orig_points": pts,
            "grab_world": world_xy,
            "radius_world": radius_world,
            "base_radius_world": radius_world,
        }
        return True

    def _warp_move(self, world_xy):
        w = getattr(self, "_warp", None)
        if not w:
            return
        w["last_world_xy"] = world_xy
        gx, gy = w["grab_world"]
        dx = world_xy[0] - gx
        dy = world_xy[1] - gy
        r2 = max(1e-9, w["radius_world"] ** 2)
        new_pts = []
        for px, py in w["orig_points"]:
            d2 = (px - gx) ** 2 + (py - gy) ** 2
            wgt = math.exp(-(d2 / r2))
            new_pts.append((px + dx * wgt, py + dy * wgt))
        w["current_points"] = new_pts
        self.graph.warp_preview = new_pts
        pct = int(100 * w["radius_world"] / w["base_radius_world"])
        self.graph.warp_visual = {"grab": (gx, gy),
                                  "radius": w["radius_world"],
                                  "pct": pct}
        self.fit_lbl.text = (f"Warp \u2014 falloff r = {pct}% "
                             f"(2-finger or wheel)")
        self.graph._redraw()

    def _warp_radius(self, factor):
        w = getattr(self, "_warp", None)
        if not w:
            return
        lo, hi = self._warp_bounds
        w["radius_world"] = max(lo, min(hi, w["radius_world"] * factor))
        if w.get("last_world_xy"):
            self._warp_move(w["last_world_xy"])

    def _warp_end(self):
        w = getattr(self, "_warp", None)
        self._warp = None
        self.graph.warp_visual = None
        self.graph.warp_preview = None
        if not w:
            return
        new_pts = w.get("current_points")
        if not new_pts:
            self.graph._redraw()
            return

        if w["kind"] == "spline":
            w["row"].points = list(new_pts)
            w["row"]._fn = make_spline(new_pts)
            self._sync()
            self._commit_undo()
            self.fit_lbl.text = "Warped \u2192 spline"
            return

        self._expr_warp_commit_popup(w, new_pts)

    def _expr_warp_commit_popup(self, warp, new_pts):
        info = Label(text="Keep warped curve as:", size_hint_y=None,
                     height=dp(22), font_size=12)
        spline_btn = Button(text="Spline (exact)", size_hint_y=None,
                            height=dp(44), font_size=13,
                            background_color=(0.2, 0.45, 0.7, 1))
        deg_sp = Spinner(text="6",
                         values=("2", "3", "4", "5", "6", "7", "8", "10", "12"),
                         size_hint_x=None, width=dp(60), font_size=13)
        poly_btn = Button(text="Polynomial", size_hint_y=None,
                          height=dp(44), font_size=13,
                          background_color=(0.25, 0.55, 0.3, 1))
        poly_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        poly_row.add_widget(Label(text="deg", size_hint_x=None,
                                  width=dp(34), font_size=12))
        poly_row.add_widget(deg_sp)
        poly_row.add_widget(poly_btn)

        cancel = Button(text="Cancel (revert)", size_hint_y=None,
                        height=dp(38), font_size=12)

        layout = BoxLayout(orientation="vertical", spacing=dp(6),
                           padding=dp(8))
        for wdg in (info, spline_btn, poly_row, cancel):
            layout.add_widget(wdg)
        popup = Popup(title="Warped curve", content=layout,
                      size_hint=(0.85, None), height=dp(250))

        def do_spline(*a):
            popup.dismiss()
            self._on_row_delete(warp["row"])
            self._add_spline_row(new_pts)

        def do_poly(*a):
            popup.dismiss()
            coefs, deg = self._fit_poly_to_points(new_pts, deg_sp.text)
            if coefs is None:
                self.fit_lbl.text = "Could not fit polynomial to warp."
                self._sync()
                return
            warp["row"].rhs.text = poly_to_expr(coefs)
            self.fit_lbl.text = f"Warped \u2192 poly deg {deg}"

        def do_cancel(*a):
            popup.dismiss()
            self.graph._redraw()

        spline_btn.bind(on_release=do_spline)
        poly_btn.bind(on_release=do_poly)
        cancel.bind(on_release=do_cancel)
        popup.open()

    # ── fill between curves ────────────────────────────────────────────

    def _open_fill_popup(self):
        candidates = [(i, r) for i, r in enumerate(self._rows)
                      if r.kind == "expr" and r.mode == "y"
                      and r.rhs.text.strip()]
        if len(candidates) < 2:
            self.fit_lbl.text = "Need 2 y=f(x) functions to fill."
            return
        labels = [f"#{i} {r.lhs.text.strip() or 'f(x)'}"
                  for i, r in candidates]
        sp_a = Spinner(text=labels[0], values=labels, font_size=11,
                       size_hint_y=None, height=dp(34))
        sp_b = Spinner(text=labels[1], values=labels, font_size=11,
                       size_hint_y=None, height=dp(34))
        lo_in = TextInput(text=f"{self.graph.x_min:g}", multiline=False,
                          font_size=12, size_hint_y=None, height=dp(32))
        hi_in = TextInput(text=f"{self.graph.x_max:g}", multiline=False,
                          font_size=12, size_hint_y=None, height=dp(32))
        apply_btn = Button(text="Shade + integrate", font_size=13,
                           size_hint_y=None, height=dp(42),
                           background_color=(0.25, 0.5, 0.3, 1))
        remove_btn = Button(text="Remove fill", font_size=12,
                            size_hint_y=None, height=dp(34),
                            background_color=(0.45, 0.25, 0.2, 1))
        cancel = Button(text="Cancel", font_size=12, size_hint_y=None,
                        height=dp(34))

        layout = BoxLayout(orientation="vertical", spacing=dp(6),
                           padding=dp(8))
        for w in (Label(text="Upper curve:", size_hint_y=None,
                        height=dp(20), font_size=11), sp_a,
                  Label(text="Lower curve:", size_hint_y=None,
                        height=dp(20), font_size=11), sp_b,
                  Label(text="Interval x_lo:", size_hint_y=None,
                        height=dp(20), font_size=11), lo_in,
                  Label(text="Interval x_hi:", size_hint_y=None,
                        height=dp(20), font_size=11), hi_in,
                  apply_btn, remove_btn, cancel):
            layout.add_widget(w)
        popup = Popup(title="Fill between curves", content=layout,
                      size_hint=(0.8, 0.85))

        def apply(*a):
            ia = labels.index(sp_a.text)
            ib = labels.index(sp_b.text)
            ea = candidates[ia][1].get_entry()
            eb = candidates[ib][1].get_entry()
            if not ea.get("fn") or not eb.get("fn"):
                self.fit_lbl.text = "Pick two valid functions."
                return
            try:
                x_lo = float(lo_in.text)
                x_hi = float(hi_in.text)
            except ValueError:
                self.fit_lbl.text = "Invalid interval."
                return
            if x_hi <= x_lo:
                self.fit_lbl.text = "x_hi must be > x_lo."
                return
            self.graph.fill = {"a_fn": ea["fn"], "b_fn": eb["fn"],
                               "x_lo": x_lo, "x_hi": x_hi,
                               "color": (0.4, 0.7, 1.0, 0.22)}
            self.graph._redraw()
            signed, absval = integrate_between(ea["fn"], eb["fn"],
                                               x_lo, x_hi)
            self.fit_lbl.text = (f"\u222b(a\u2212b)[{x_lo:g},{x_hi:g}] "
                                 f"\u2248 {signed:.6g}  "
                                 f"|  \u222b|a\u2212b| \u2248 {absval:.6g}")

        def remove(*a):
            self.graph.fill = None
            self.graph._redraw()
            self.fit_lbl.text = "Fill removed."
            popup.dismiss()

        apply_btn.bind(on_release=apply)
        remove_btn.bind(on_release=remove)
        cancel.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    # ── piecewise → expression ─────────────────────────────────────────

    def _piecewise_to_expr(self, row):
        if not row.pieces:
            return
        fitted = []
        for pts in row.pieces:
            if len(pts) < 2:
                continue
            coefs, deg = self._fit_poly_to_points(pts, "6")
            if coefs is None:
                self.fit_lbl.text = "Could not fit a segment."
                return
            xs = [p[0] for p in pts]
            fitted.append((min(xs), max(xs), coefs))
        if not fitted:
            return
        fitted.sort(key=lambda f: f[0])

        expr = poly_to_expr(fitted[-1][2])
        for i in range(len(fitted) - 2, -1, -1):
            boundary = (fitted[i][1] + fitted[i + 1][0]) / 2.0
            expr = (f"where(x < {boundary!r}, "
                    f"{poly_to_expr(fitted[i][2])}, {expr})")

        self._restoring = True
        try:
            if row in self._rows:
                self._rows.remove(row)
                self.rows_box.remove_widget(row)
            new_row = FunctionRow(self._next_color(), self._on_row_change,
                                  self._on_row_delete)
            new_row.lhs.text = "pw(x)"
            new_row.rhs.text = expr
            self._rows.append(new_row)
            self.rows_box.add_widget(new_row)
        finally:
            self._restoring = False
        self._sync()
        self.fit_lbl.text = (f"Piecewise \u2192 expression "
                             f"({len(fitted)} branches)")

    # ── PNG export ─────────────────────────────────────────────────────

    def _export_png(self):
        try:
            from kivy.utils import platform as _plat
            if _plat == "android":
                from core.android_storage import shared_storage_root
                out_dir = os.path.join(shared_storage_root(), "Pictures",
                                       "Srboli")
            else:
                out_dir = os.path.join(app_data.get_data_dir(), "exports")
        except Exception:
            out_dir = os.path.join(app_data.get_data_dir(), "exports")
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            self.fit_lbl.text = f"Export failed: {e}"
            return
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(out_dir, f"plot_{ts}.png")
        try:
            saved_visual = self.graph.warp_visual
            saved_preview = self.graph.warp_preview
            saved_stroke = self.graph._stroke_px
            self.graph.warp_visual = None
            self.graph.warp_preview = None
            self.graph._stroke_px = None
            self.graph._redraw()
            self.graph.export_to_png(path)
            self.graph.warp_visual = saved_visual
            self.graph.warp_preview = saved_preview
            self.graph._stroke_px = saved_stroke
            self.graph._redraw()
            self.fit_lbl.text = f"Saved: {path}"
        except Exception as e:
            self.fit_lbl.text = f"Export failed: {e}"

    # ── keyboard ───────────────────────────────────────────────────────

    def _on_key_down(self, window, key, scancode, codepoint, modifiers):
        if self.manager is None or self.manager.current != self.name:
            return False
        ctrl = "ctrl" in modifiers
        shift = "shift" in modifiers
        alt = "alt" in modifiers
        if ctrl and alt and codepoint == "z" and not shift:
            self._do_view_undo()
            return True
        if ctrl and alt and (codepoint == "y" or
                             (codepoint == "z" and shift)):
            self._do_view_redo()
            return True
        if ctrl and codepoint == "z" and not shift and not alt:
            self._do_undo()
            return True
        if ctrl and not alt and (codepoint == "y" or
                                 (codepoint == "z" and shift)):
            self._do_redo()
            return True
        return False

    # ── mode & lifecycle ───────────────────────────────────────────────

    def _set_mode(self, mode):
        self.graph.mode = mode
        if mode != "pencil":
            self.graph._stroke_px = None
            self.graph._pencil_touches = {}
            self.graph._pencil_multi = False
            self.graph._pencil_pan_anchor = None
        if mode != "point":
            self.graph._point_touches = {}
            self.graph._point_multi = False
            self.graph._point_pan_anchor = None
            self.graph._point_prev_dist = None
            self.graph._point_candidate_px = None
            self.graph._point_moved = False
        self.graph._redraw()

    def on_enter(self, *a):
        Clock.schedule_once(lambda dt: self.graph._redraw(), 0)
        Window.bind(on_key_down=self._on_key_down)

    def on_leave(self, *a):
        try:
            Window.unbind(on_key_down=self._on_key_down)
        except Exception:
            pass
        if self.graph._view_debounce:
            self.graph._view_debounce.cancel()
            self.graph._view_debounce = None
        self.graph._pencil_touches = {}
        self.graph._pencil_multi = False
        self.graph._pencil_pan_anchor = None
        self.graph._stroke_px = None
        self.graph._point_touches = {}
        self.graph._point_multi = False
        self.graph._point_pan_anchor = None
        self.graph._point_prev_dist = None
        self.graph._point_candidate_px = None
        self.graph._point_moved = False

    # ── help ───────────────────────────────────────────────────────────

    def _show_help(self):
        txt = (
            "[b]Function Plotter[/b]\n\n"
            "Type expressions in [i]x[/i] (or [i]t[/i] for param/polar). "
            "[b]^[/b] works for powers.\n"
            "  sin(x)/x\n"
            "  x^2 - 3*x + 1\n"
            "  exp(-x^2)\n"
            "  log(abs(x)) + sqrt(x)\n"
            "  where(x < 0, 1/x, x)\n\n"
            "[b]Functions[/b]: sin cos tan asin acos atan sinh cosh tanh "
            "exp log log10 log2 sqrt cbrt abs floor ceil round min max "
            "sign atan2 hypot where\n"
            "[b]Constants[/b]: pi, e, tau\n"
            "[b]Operators[/b]: + - * / ** // % ^ and or not < <= > >= == != "
            "where(cond, a, b)\n\n"
            "[b]Row modes[/b]\n"
            "• y = f(x)\n"
            "• x,y(t) — parametric, range lo, hi\n"
            "• r(θ) — polar, range lo, hi\n\n"
            "[b]Controls[/b]\n"
            "• Drag on the graph → pan\n"
            "• Mouse wheel → zoom at cursor\n"
            "• Pan mode: grab a curve to warp it; pinch or wheel "
            "to widen/narrow the falloff\n"
            "• Point mode: tap to place, drag cancels, 2-finger drag pans "
            "+ pinch to zoom\n"
            "• Pencil mode: draw a stroke; a 2-finger drag pans without "
            "drawing\n"
            "• Ctrl+Z / Ctrl+Y — undo/redo content\n"
            "• Ctrl+Alt+Z / Ctrl+Alt+Y — undo/redo view\n"
            "• View ▾ — view-history menu\n"
            "• Fill — shade ∫(a−b) dx between two y=f(x) curves\n"
            "• PNG — export the current view\n"
        )
        lbl = Label(text=txt, markup=True, font_size=12, halign="left",
                    valign="top", size_hint_y=None, padding=(dp(8), dp(8)))
        lbl.bind(width=lambda *a: lbl.setter("text_size")(
            lbl, (lbl.width, None)))
        lbl.bind(texture_size=lambda *a: setattr(
            lbl, "height", lbl.texture_size[1] + dp(16)))
        sv = ScrollView()
        sv.add_widget(lbl)
        Popup(title="Help", content=sv, size_hint=(0.9, 0.85)).open()