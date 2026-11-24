# core/precision_canvas_core.py - the model behind Precision Canvas. No Kivy.
#
# A document is a list of editable geometric objects (never pixels). Coordinates are
# document units with Y pointing UP (maths convention); the screen uses the same
# orientation (see View), so there is no hidden flip. Angles are degrees, counter-clockwise.
#
#   point, line, arrow, polyline, freehand : points
#   rect (x, y = lower-left corner, w, h, rot about its centre), square (x, y, side, rot)
#   circle (cx, cy, r), ellipse (cx, cy, rx, ry, rot), polygon (cx, cy, r, n, rot)
#   text (x, y = lower-left of the first line, text, size, rot)
import copy
import json
import math
import re

VERSION = 1
TYPES = ("point", "line", "arrow", "polyline", "freehand", "rect", "square", "circle",
         "ellipse", "polygon", "text")
DASHES = ("solid", "dashed", "dotted")
UNITS = ("u", "px", "mm", "cm", "m", "in")
GRIDS = ("square", "dots")
MAX_UNDO = 200
MAX_OBJECTS = 5000

DEFAULT_STYLE = {"stroke": "#202020", "fill": "", "width": 2.0, "dash": "solid", "opacity": 1.0}
DEFAULT_SETTINGS = {"width": 800.0, "height": 600.0, "units": "u", "background": "#FFFFFF",
                    "grid": True, "grid_type": "square", "grid_spacing": 20.0, "grid_major": 5,
                    "snap_grid": True, "snap_points": True, "snap_align": False,
                    "angle_step": 15, "mode": "strict"}


# ---------------------------------------------------------------- numbers
def fmt(v, nd=2):
    """12 -> '12', 1234.5 -> '1,234.5', 0.333333 -> '0.33'."""
    if v is None or isinstance(v, str):
        return str(v or "")
    if not math.isfinite(v):
        return "n/a"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    s = f"{v:,.{nd}f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def calc(text):
    """Evaluate a typed number or expression safely (no eval): + - * / ^ ( ), pi, e, tau,
    sqrt, abs, sin, cos, tan (degrees) and deg. Raises ValueError with a readable message."""
    s = (text or "").strip().lower().replace(",", ".").replace("×", "*").replace("÷", "/")
    s = s.replace("√", "sqrt").replace("π", "pi")
    if not s or len(s) > 200:
        raise ValueError("Type a number.")
    toks = re.findall(r"\d+\.?\d*(?:e[+-]?\d+)?|\.\d+|[a-z]+|[-+*/^()]", s)
    if "".join(toks) != re.sub(r"\s+", "", s):
        raise ValueError("Can't read that.")
    pos = [0]
    consts = {"pi": math.pi, "e": math.e, "tau": math.tau}
    funcs = {"sqrt": math.sqrt, "abs": abs, "deg": math.radians,
             "sin": lambda v: math.sin(math.radians(v)), "cos": lambda v: math.cos(math.radians(v)),
             "tan": lambda v: math.tan(math.radians(v))}

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        t = peek()
        pos[0] += 1
        return t

    def expr():
        v = term()
        while peek() in ("+", "-"):
            v = v + term() if take() == "+" else v - term()
        return v

    def term():
        v = power()
        while peek() in ("*", "/"):
            if take() == "*":
                v *= power()
            else:
                d = power()
                if d == 0:
                    raise ValueError("Division by zero.")
                v /= d
        return v

    def power():
        b = unary()
        if peek() == "^":
            take()
            e = power()
            if abs(e) > 100:
                raise ValueError("Exponent too large.")
            try:
                b = b ** e
            except (OverflowError, ZeroDivisionError):
                raise ValueError("Result too large.")
            if isinstance(b, complex):
                raise ValueError("Not a real number.")
        return b

    def unary():
        if peek() == "-":
            take()
            return -unary()
        if peek() == "+":
            take()
            return unary()
        return atom()

    def atom():
        t = take()
        if t is None:
            raise ValueError("Incomplete expression.")
        if t == "(":
            v = expr()
            if take() != ")":
                raise ValueError("Missing ).")
            return v
        if t in funcs:
            if take() != "(":
                raise ValueError(f"{t} needs ( ).")
            v = expr()
            if take() != ")":
                raise ValueError("Missing ).")
            try:
                return funcs[t](v)
            except ValueError:
                raise ValueError(f"{t} of that is not defined.")
        if t in consts:
            return consts[t]
        if re.fullmatch(r"\d+\.?\d*(?:e[+-]?\d+)?|\.\d+", t):
            return float(t)
        raise ValueError(f"Unknown '{t}'.")

    v = expr()
    if peek() is not None:
        raise ValueError("Can't read that.")
    if not math.isfinite(v):
        raise ValueError("Not a finite number.")
    return v


# ---------------------------------------------------------------- vectors
def rotate_point(px, py, cx, cy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    dx, dy = px - cx, py - cy
    return cx + dx * c - dy * s, cy + dx * s + dy * c


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle_deg(p0, p1):
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))


def snap_angle(p0, p1, step):
    """p1 moved so the line p0->p1 has an angle that is a multiple of `step` degrees."""
    if not step or step <= 0:
        return p1
    d = dist(p0, p1)
    if d == 0:
        return p1
    a = round(angle_deg(p0, p1) / step) * step
    return p0[0] + d * math.cos(math.radians(a)), p0[1] + d * math.sin(math.radians(a))


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else clamp(((p[0] - ax) * dx + (p[1] - ay) * dy) / L, 0, 1)
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def in_polygon(p, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


# ---------------------------------------------------------------- objects
def new_style(**kw):
    s = dict(DEFAULT_STYLE)
    s.update(kw)
    return s


def make(kind, **g):
    """A fresh object (no id yet; Document.add gives it one)."""
    if kind not in TYPES:
        raise ValueError(f"unknown object type {kind!r}")
    base = {"type": kind, "name": "", "visible": True, "locked": False, "style": new_style()}
    defaults = {"point": {"x": 0, "y": 0}, "line": {"x1": 0, "y1": 0, "x2": 100, "y2": 0},
                "arrow": {"x1": 0, "y1": 0, "x2": 100, "y2": 0},
                "polyline": {"points": []}, "freehand": {"points": []},
                "rect": {"x": 0, "y": 0, "w": 100, "h": 60, "rot": 0},
                "square": {"x": 0, "y": 0, "side": 80, "rot": 0},
                "circle": {"cx": 0, "cy": 0, "r": 50},
                "ellipse": {"cx": 0, "cy": 0, "rx": 60, "ry": 40, "rot": 0},
                "polygon": {"cx": 0, "cy": 0, "r": 50, "n": 6, "rot": 0},
                "text": {"x": 0, "y": 0, "text": "Text", "size": 18, "rot": 0, "bold": False,
                         "italic": False, "align": "left"}}[kind]
    base.update(defaults)
    st = g.pop("style", None)
    base.update(g)
    if st:
        base["style"] = new_style(**st)
    if kind in ("text", "point"):
        base["style"]["fill"] = base["style"]["fill"] or base["style"]["stroke"]
    return base


def polygon_side(r, n):
    return 2 * r * math.sin(math.pi / n)


def vertices(o):
    """Corner points of a rect / square / polygon, or the points of a line/polyline; else []."""
    t = o["type"]
    if t in ("line", "arrow"):
        return [(o["x1"], o["y1"]), (o["x2"], o["y2"])]
    if t in ("polyline", "freehand"):
        return [tuple(p) for p in o["points"]]
    if t in ("rect", "square"):
        w, h = (o["w"], o["h"]) if t == "rect" else (o["side"], o["side"])
        cx, cy = o["x"] + w / 2, o["y"] + h / 2
        pts = [(o["x"], o["y"]), (o["x"] + w, o["y"]), (o["x"] + w, o["y"] + h), (o["x"], o["y"] + h)]
        return [rotate_point(px, py, cx, cy, o["rot"]) for px, py in pts] if o["rot"] else pts
    if t == "polygon":
        return [(o["cx"] + o["r"] * math.cos(math.radians(o["rot"] + 90 + 360 * k / o["n"])),
                 o["cy"] + o["r"] * math.sin(math.radians(o["rot"] + 90 + 360 * k / o["n"])))
                for k in range(int(o["n"]))]
    return []


def outline(o, steps=72):
    """A drawable polyline (closed shapes repeat the first point). Text has none."""
    t = o["type"]
    if t in ("rect", "square", "polygon"):
        v = vertices(o)
        return v + v[:1]
    if t in ("line", "arrow", "polyline", "freehand"):
        return vertices(o)
    if t == "circle":
        return [(o["cx"] + o["r"] * math.cos(2 * math.pi * k / steps),
                 o["cy"] + o["r"] * math.sin(2 * math.pi * k / steps)) for k in range(steps + 1)]
    if t == "ellipse":
        return [rotate_point(o["cx"] + o["rx"] * math.cos(2 * math.pi * k / steps),
                             o["cy"] + o["ry"] * math.sin(2 * math.pi * k / steps),
                             o["cx"], o["cy"], o["rot"]) for k in range(steps + 1)]
    return []


def text_size(o):
    """Rough width and height of a text object in document units."""
    lines = str(o["text"]).split("\n") or [""]
    return (max(len(l) for l in lines) * o["size"] * 0.58, len(lines) * o["size"] * 1.2)


def bbox(o):
    """(xmin, ymin, xmax, ymax) of the object (text uses its rotated estimate)."""
    t = o["type"]
    if t == "point":
        return o["x"], o["y"], o["x"], o["y"]
    if t == "text":
        w, h = text_size(o)
        pts = [rotate_point(o["x"] + a, o["y"] + b, o["x"], o["y"], o["rot"])
               for a, b in ((0, 0), (w, 0), (w, h), (0, h))]
    else:
        pts = outline(o) or [(0, 0)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def center(o):
    t = o["type"]
    if t in ("circle", "ellipse", "polygon"):
        return o["cx"], o["cy"]
    if t == "rect":
        return o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
    if t == "square":
        return o["x"] + o["side"] / 2, o["y"] + o["side"] / 2
    x0, y0, x1, y1 = bbox(o)
    return (x0 + x1) / 2, (y0 + y1) / 2


def hit(o, x, y, tol):
    """True if (x, y) touches the object: on its outline, or inside a filled shape."""
    t = o["type"]
    p = (x, y)
    if t == "point":
        return dist(p, (o["x"], o["y"])) <= tol * 1.5
    if t == "text":
        w, h = text_size(o)
        lx, ly = rotate_point(x, y, o["x"], o["y"], -o["rot"])
        return -tol <= lx - o["x"] <= w + tol and -tol <= ly - o["y"] <= h + tol
    pts = outline(o)
    if len(pts) < 2:
        return False
    if any(seg_dist(p, pts[i], pts[i + 1]) <= tol + o["style"]["width"] / 2 for i in range(len(pts) - 1)):
        return True
    closed = t in ("rect", "square", "polygon", "circle", "ellipse")
    return bool(closed and o["style"]["fill"] and in_polygon(p, pts[:-1]))


def translate(o, dx, dy):
    t = o["type"]
    if t in ("point", "rect", "square", "text"):
        o["x"] += dx
        o["y"] += dy
    elif t in ("circle", "ellipse", "polygon"):
        o["cx"] += dx
        o["cy"] += dy
    elif t in ("line", "arrow"):
        o["x1"] += dx
        o["x2"] += dx
        o["y1"] += dy
        o["y2"] += dy
    else:
        o["points"] = [[px + dx, py + dy] for px, py in o["points"]]


def rotate_object(o, deg, cx=None, cy=None):
    """Rotate by `deg` about (cx, cy) (default: its own centre)."""
    t = o["type"]
    cx, cy = (center(o) if cx is None else (cx, cy))
    if t in ("line", "arrow"):
        o["x1"], o["y1"] = rotate_point(o["x1"], o["y1"], cx, cy, deg)
        o["x2"], o["y2"] = rotate_point(o["x2"], o["y2"], cx, cy, deg)
    elif t in ("polyline", "freehand"):
        o["points"] = [list(rotate_point(px, py, cx, cy, deg)) for px, py in o["points"]]
    elif t == "point":
        o["x"], o["y"] = rotate_point(o["x"], o["y"], cx, cy, deg)
    else:
        ox, oy = center(o)
        nx, ny = rotate_point(ox, oy, cx, cy, deg)
        translate(o, nx - ox, ny - oy)
        if "rot" in o:
            o["rot"] = (o["rot"] + deg) % 360


# ---------------------------------------------------------------- inspector fields
def fields(o):
    """[(key, label, kind)] the inspector shows for this object. kind: num, int, text, bool."""
    t = o["type"]
    return {
        "point": [("x", "X", "num"), ("y", "Y", "num")],
        "arrow": [("x1", "Start X", "num"), ("y1", "Start Y", "num"), ("x2", "End X", "num"),
                  ("y2", "End Y", "num"), ("length", "Length", "num"), ("angle", "Angle (deg)", "num")],
        "line": [("x1", "Start X", "num"), ("y1", "Start Y", "num"), ("x2", "End X", "num"),
                 ("y2", "End Y", "num"), ("length", "Length", "num"), ("angle", "Angle (deg)", "num")],
        "rect": [("x", "X", "num"), ("y", "Y", "num"), ("w", "Width", "num"), ("h", "Height", "num"),
                 ("rot", "Rotation (deg)", "num")],
        "square": [("x", "X", "num"), ("y", "Y", "num"), ("side", "Side length", "num"),
                   ("rot", "Rotation (deg)", "num")],
        "circle": [("cx", "Center X", "num"), ("cy", "Center Y", "num"), ("r", "Radius", "num"),
                   ("diameter", "Diameter", "num")],
        "ellipse": [("cx", "Center X", "num"), ("cy", "Center Y", "num"), ("rx", "Radius X", "num"),
                    ("ry", "Radius Y", "num"), ("rot", "Rotation (deg)", "num")],
        "polygon": [("cx", "Center X", "num"), ("cy", "Center Y", "num"), ("r", "Radius", "num"),
                    ("n", "Sides", "int"), ("side", "Side length", "num"), ("rot", "Rotation (deg)", "num")],
        "text": [("text", "Content", "text"), ("x", "X", "num"), ("y", "Y", "num"),
                 ("size", "Font size", "num"), ("rot", "Rotation (deg)", "num"),
                 ("bold", "Bold", "bool"), ("italic", "Italic", "bool")],
        "polyline": [], "freehand": [],
    }[t]


def arrow_fields():
    return fields({"type": "line"})


def get_field(o, key):
    t = o["type"]
    if key == "length":
        return dist((o["x1"], o["y1"]), (o["x2"], o["y2"]))
    if key == "angle":
        return angle_deg((o["x1"], o["y1"]), (o["x2"], o["y2"])) % 360
    if key == "diameter":
        return o["r"] * 2
    if key == "side" and t == "polygon":
        return polygon_side(o["r"], o["n"])
    return o[key]


def set_field(o, key, value):
    """Change one geometric field. Returns (ok, message); the object is untouched on failure."""
    t = o["type"]
    kind = next((k for kk, _l, k in (fields(o) if t != "arrow" else arrow_fields()) if kk == key), None)
    if kind is None:
        return False, "Not editable."
    if kind == "text":
        o[key] = str(value)
        return True, ""
    if kind == "bool":
        o[key] = bool(value)
        return True, ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "Not a number."
    if not math.isfinite(v):
        return False, "Not a finite number."
    positive = key in ("w", "h", "side", "r", "rx", "ry", "size", "length", "diameter", "n")
    if positive and v <= 0:
        return False, "Must be greater than 0."
    if abs(v) > 1e7:
        return False, "Too large."
    if key == "n":
        if v != int(v) or not 3 <= v <= 200:
            return False, "Sides must be a whole number from 3 to 200."
        o["n"] = int(v)
    elif key == "length":
        a = math.radians(get_field(o, "angle"))
        o["x2"], o["y2"] = o["x1"] + v * math.cos(a), o["y1"] + v * math.sin(a)
    elif key == "angle":
        L = get_field(o, "length")
        o["x2"], o["y2"] = o["x1"] + L * math.cos(math.radians(v)), o["y1"] + L * math.sin(math.radians(v))
    elif key == "diameter":
        o["r"] = v / 2
    elif key == "side" and t == "polygon":
        o["r"] = v / (2 * math.sin(math.pi / o["n"]))
    elif key in ("rot",):
        o["rot"] = v % 360
    else:
        o[key] = v
    return True, ""


# ---------------------------------------------------------------- mathematics
def math_rows(o, unit="u"):
    """[(label, formula, substituted, result)] for the Mathematics panel; strings, safe for any
    (even degenerate) geometry."""
    t = o["type"]
    u = "" if unit == "u" else " " + unit
    u2 = (" u²" if unit == "u" else f" {unit}²")
    pi = math.pi
    rows = []

    def row(label, formula, subst, value, suffix=u):
        rows.append((label, formula, subst, fmt(value) + suffix))

    if t == "line" or t == "arrow":
        dx, dy = o["x2"] - o["x1"], o["y2"] - o["y1"]
        row("Length", "d = √(Δx² + Δy²)", f"√({fmt(dx)}² + {fmt(dy)}²)", math.hypot(dx, dy))
        row("Angle", "θ = atan2(Δy, Δx)", f"atan2({fmt(dy)}, {fmt(dx)})", get_field(o, "angle"), "°")
        row("Midpoint", "((x₁+x₂)/2, (y₁+y₂)/2)", "", 0, "")
        rows[-1] = ("Midpoint", "((x₁+x₂)/2, (y₁+y₂)/2)", "",
                    f"({fmt((o['x1'] + o['x2']) / 2)}, {fmt((o['y1'] + o['y2']) / 2)})")
    elif t == "rect":
        w, h = o["w"], o["h"]
        row("Area", "A = w × h", f"{fmt(w)} × {fmt(h)}", w * h, u2)
        row("Perimeter", "P = 2(w + h)", f"2({fmt(w)} + {fmt(h)})", 2 * (w + h))
        row("Diagonal", "d = √(w² + h²)", f"√({fmt(w)}² + {fmt(h)}²)", math.hypot(w, h))
    elif t == "square":
        s = o["side"]
        row("Area", "A = s²", f"{fmt(s)}²", s * s, u2)
        row("Perimeter", "P = 4s", f"4 × {fmt(s)}", 4 * s)
        row("Diagonal", "d = s√2", f"{fmt(s)} × √2", s * math.sqrt(2))
    elif t == "circle":
        r = o["r"]
        row("Area", "A = πr²", f"π × {fmt(r)}²", pi * r * r, u2)
        row("Circumference", "C = 2πr", f"2π × {fmt(r)}", 2 * pi * r)
        row("Diameter", "D = 2r", f"2 × {fmt(r)}", 2 * r)
    elif t == "ellipse":
        a, b = o["rx"], o["ry"]
        row("Area", "A = πab", f"π × {fmt(a)} × {fmt(b)}", pi * a * b, u2)
        h = ((a - b) ** 2) / ((a + b) ** 2) if a + b else 0
        row("Perimeter (approx.)", "P ≈ π(a+b)(1 + 3h/(10+√(4−3h)))", f"h = {fmt(h, 4)}",
            pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h))))
    elif t == "polygon":
        n, r = o["n"], o["r"]
        a = polygon_side(r, n)
        row("Side length", "a = 2r·sin(π/n)", f"2 × {fmt(r)} × sin(π/{n})", a)
        row("Perimeter", "P = n × a", f"{n} × {fmt(a)}", n * a)
        row("Area", "A = n·a² / (4·tan(π/n))", f"{n} × {fmt(a)}² / (4·tan(π/{n}))",
            n * a * a / (4 * math.tan(pi / n)), u2)
        row("Interior angle", "(n − 2) × 180° / n", f"({n} − 2) × 180° / {n}", (n - 2) * 180 / n, "°")
        row("Exterior angle", "360° / n", f"360° / {n}", 360 / n, "°")
    elif t in ("polyline", "freehand"):
        pts = o["points"]
        L = sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        row("Points", "", "", len(pts), "")
        row("Length", "Σ segment lengths", f"{max(len(pts) - 1, 0)} segments", L)
    return rows


# ---------------------------------------------------------------- view
class View:
    """Zoom and pan. (ox, oy) is where document (0, 0) sits on screen, in widget pixels with
    the origin at the widget's bottom-left (the same orientation as the document)."""

    def __init__(self, zoom=1.0, ox=40.0, oy=40.0):
        self.zoom, self.ox, self.oy = zoom, ox, oy

    def to_screen(self, x, y):
        return self.ox + x * self.zoom, self.oy + y * self.zoom

    def to_doc(self, sx, sy):
        return (sx - self.ox) / self.zoom, (sy - self.oy) / self.zoom

    def zoom_at(self, sx, sy, factor, lo=0.02, hi=200.0):
        """Zoom by `factor`, keeping the document point under (sx, sy) where it is."""
        dx, dy = self.to_doc(sx, sy)
        self.zoom = clamp(self.zoom * factor, lo, hi)
        self.ox, self.oy = sx - dx * self.zoom, sy - dy * self.zoom

    def pan(self, dsx, dsy):
        self.ox += dsx
        self.oy += dsy

    def fit(self, bounds, width, height, margin=30):
        """Show the document rectangle `bounds` (x0, y0, x1, y1) centred in a width x height view."""
        x0, y0, x1, y1 = bounds
        bw, bh = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        self.zoom = clamp(min((width - 2 * margin) / bw, (height - 2 * margin) / bh), 0.02, 200.0)
        self.ox = (width - bw * self.zoom) / 2 - x0 * self.zoom
        self.oy = (height - bh * self.zoom) / 2 - y0 * self.zoom


# ---------------------------------------------------------------- snapping
def snap_candidates(o):
    """[(x, y, kind)] points of an object other objects can snap to."""
    t = o["type"]
    out = []
    if t == "point":
        out.append((o["x"], o["y"], "point"))
    elif t in ("line", "arrow"):
        (a, b) = vertices(o)
        out += [(*a, "endpoint"), (*b, "endpoint"), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, "midpoint")]
    elif t in ("polyline", "freehand"):
        pts = vertices(o)
        out += [(*p, "endpoint") for p in (pts[:1] + pts[-1:] if t == "freehand" else pts)]
    elif t in ("rect", "square", "polygon"):
        v = vertices(o)
        out += [(*p, "corner") for p in v]
        out += [((v[i][0] + v[(i + 1) % len(v)][0]) / 2, (v[i][1] + v[(i + 1) % len(v)][1]) / 2, "midpoint")
                for i in range(len(v))]
        out.append((*center(o), "center"))
    elif t == "circle":
        cx, cy, r = o["cx"], o["cy"], o["r"]
        out += [(cx, cy, "center"), (cx + r, cy, "quadrant"), (cx - r, cy, "quadrant"),
                (cx, cy + r, "quadrant"), (cx, cy - r, "quadrant")]
    elif t == "ellipse":
        out.append((o["cx"], o["cy"], "center"))
    elif t == "text":
        out.append((o["x"], o["y"], "anchor"))
    return out


def line_intersections(objs):
    """Crossing points between straight segments of different objects."""
    segs = []
    for oi, o in enumerate(objs):
        if o["type"] in ("line", "arrow", "polyline", "rect", "square", "polygon"):
            pts = outline(o)
            segs += [(oi, pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    out = []
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if segs[i][0] == segs[j][0]:
                continue
            (x1, y1), (x2, y2) = segs[i][1], segs[i][2]
            (x3, y3), (x4, y4) = segs[j][1], segs[j][2]
            d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
            if abs(d) < 1e-12:
                continue
            t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
            u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
            if 0 <= t <= 1 and 0 <= u <= 1:
                out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1), "intersection"))
            if len(out) > 400:
                return out
    return out


def snap(doc, x, y, radius, exclude=(), points=True, grid=True, align=False):
    """Snap (x, y) to the nearest object point within `radius` document units, else to the grid.
    Returns (x, y, kind) where kind is "endpoint", "corner", "center", "midpoint", "quadrant",
    "intersection", "grid", "align" or None (nothing snapped)."""
    best, bd = None, radius
    cands = []
    if points or align:
        for o in doc.objects:
            if o["id"] in exclude or not o["visible"]:
                continue
            cands += snap_candidates(o)
    if points:
        cands_i = line_intersections([o for o in doc.objects if o["id"] not in exclude and o["visible"]])
        for cx, cy, k in cands + cands_i:
            d = math.hypot(cx - x, cy - y)
            if d < bd:
                best, bd = (cx, cy, k), d
    if best:
        return best
    sx, sy, kind = x, y, None
    if align:
        ax = min((c for c in cands if abs(c[0] - x) <= radius), key=lambda c: abs(c[0] - x), default=None)
        ay = min((c for c in cands if abs(c[1] - y) <= radius), key=lambda c: abs(c[1] - y), default=None)
        if ax:
            sx, kind = ax[0], "align"
        if ay:
            sy, kind = ay[1], "align"
    if grid and doc.settings["grid_spacing"] > 0 and kind is None:
        g = doc.settings["grid_spacing"]
        gx, gy = round(x / g) * g, round(y / g) * g
        if math.hypot(gx - x, gy - y) <= max(radius, g / 2):
            return gx, gy, "grid"
    return sx, sy, kind


def align(objs, how):
    """Align objects to each other: left, right, top, bottom, hcenter, vcenter."""
    if len(objs) < 2:
        return
    boxes = [bbox(o) for o in objs]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    for o, b in zip(objs, boxes):
        dx = dy = 0.0
        if how == "left":
            dx = x0 - b[0]
        elif how == "right":
            dx = x1 - b[2]
        elif how == "hcenter":
            dx = (x0 + x1) / 2 - (b[0] + b[2]) / 2
        elif how == "bottom":
            dy = y0 - b[1]
        elif how == "top":
            dy = y1 - b[3]
        elif how == "vcenter":
            dy = (y0 + y1) / 2 - (b[1] + b[3]) / 2
        translate(o, dx, dy)


# ---------------------------------------------------------------- document
def clean_object(d):
    """A safe object from untrusted data, or None."""
    if not isinstance(d, dict) or d.get("type") not in TYPES:
        return None
    try:
        o = make(d["type"])
        for k in o:
            if k in d and k != "style":
                if isinstance(o[k], bool):
                    o[k] = bool(d[k])
                elif isinstance(o[k], (int, float)):
                    v = float(d[k])
                    if not math.isfinite(v) or abs(v) > 1e9:
                        return None
                    o[k] = v
                elif isinstance(o[k], str):
                    o[k] = str(d[k])[:5000]
                elif k == "points":
                    o[k] = [[float(p[0]), float(p[1])] for p in d[k][:20000]]
        if o["type"] == "polygon":
            o["n"] = int(clamp(o["n"], 3, 200))
        st = d.get("style") or {}
        s = new_style()
        for k in ("stroke", "fill"):
            if isinstance(st.get(k), str) and (st[k] == "" or re.fullmatch(r"#[0-9A-Fa-f]{6}", st[k])):
                s[k] = st[k].upper()
        s["width"] = clamp(float(st.get("width", 2)), 0.1, 200)
        s["opacity"] = clamp(float(st.get("opacity", 1)), 0.0, 1.0)
        s["dash"] = st.get("dash") if st.get("dash") in DASHES else "solid"
        o["style"] = s
        o["id"] = int(d.get("id", 0))
        return o
    except (TypeError, ValueError, KeyError, IndexError):
        return None


class Document:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.objects = []
        self._next = 1
        self._undo, self._redo = [], []

    # ----- objects
    def add(self, o):
        if len(self.objects) >= MAX_OBJECTS:
            raise ValueError("Too many objects.")
        o["id"] = self._next
        self._next += 1
        if not o["name"]:
            n = sum(1 for x in self.objects if x["type"] == o["type"]) + 1
            o["name"] = f"{o['type'].capitalize()} {n:02d}"
        self.objects.append(o)
        return o

    def get(self, oid):
        return next((o for o in self.objects if o["id"] == oid), None)

    def remove(self, ids):
        ids = set(ids)
        self.objects = [o for o in self.objects if o["id"] not in ids]

    def duplicate(self, ids, offset=20):
        out = []
        for o in [x for x in self.objects if x["id"] in set(ids)]:
            c = copy.deepcopy(o)
            c["name"] = o["name"] + " copy"
            translate(c, offset, -offset)
            out.append(self.add(c))
        return out

    def move_order(self, oid, step):
        """Raise (+1) or lower (-1) an object in the drawing order."""
        i = next((k for k, o in enumerate(self.objects) if o["id"] == oid), None)
        if i is None or not 0 <= i + step < len(self.objects):
            return
        self.objects[i], self.objects[i + step] = self.objects[i + step], self.objects[i]

    def hit_test(self, x, y, tol):
        """The topmost visible, unlocked object under the point."""
        for o in reversed(self.objects):
            if o["visible"] and not o["locked"] and hit(o, x, y, tol):
                return o
        return None

    def bounds(self):
        s = self.settings
        return 0.0, 0.0, s["width"], s["height"]

    # ----- history: snapshots of the object list
    def _snap(self):
        return json.dumps([self.objects, self._next, self.settings])

    def checkpoint(self):
        """Call BEFORE a change: one call = one undo step (a whole drag is one change)."""
        self._undo.append(self._snap())
        del self._undo[:-MAX_UNDO]
        self._redo = []

    def _restore(self, s):
        self.objects, self._next, self.settings = json.loads(s)

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._snap())
        self._restore(self._undo.pop())
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._snap())
        self._restore(self._redo.pop())
        return True

    # ----- files
    def to_dict(self):
        return {"format": "srbd", "version": VERSION, "settings": self.settings,
                "objects": self.objects}

    def to_json(self):
        return json.dumps(self.to_dict(), indent=1, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict) or d.get("format") != "srbd":
            raise ValueError("This is not a Precision Canvas file.")
        if int(d.get("version", 0)) > VERSION:
            raise ValueError("This file was made by a newer Srboli.")
        doc = cls()
        s = d.get("settings") or {}
        for k, dv in DEFAULT_SETTINGS.items():
            v = s.get(k, dv)
            if isinstance(dv, bool):
                v = bool(v)
            elif isinstance(dv, (int, float)):
                try:
                    v = float(v) if isinstance(dv, float) else int(v)
                except (TypeError, ValueError):
                    v = dv
                if not math.isfinite(v) or v < 0:
                    v = dv
            elif not isinstance(v, type(dv)):
                v = dv
            doc.settings[k] = v
        doc.settings["units"] = doc.settings["units"] if doc.settings["units"] in UNITS else "u"
        doc.settings["grid_type"] = doc.settings["grid_type"] if doc.settings["grid_type"] in GRIDS else "square"
        doc.settings["width"] = clamp(doc.settings["width"], 1, 100000)
        doc.settings["height"] = clamp(doc.settings["height"], 1, 100000)
        used = set()
        for od in (d.get("objects") or [])[:MAX_OBJECTS]:
            o = clean_object(od)
            if o is None:
                continue
            if o["id"] <= 0 or o["id"] in used:
                o["id"] = max(used or {0}) + 1
            used.add(o["id"])
            doc.objects.append(o)
        doc._next = max(used or {0}) + 1
        return doc

    @classmethod
    def from_json(cls, text):
        try:
            return cls.from_dict(json.loads(text))
        except json.JSONDecodeError as e:
            raise ValueError(f"The file is damaged ({e.msg}).")


# ---------------------------------------------------------------- export
def _dash(style, scale=1.0):
    w = style["width"] * scale
    return {"solid": None, "dashed": (w * 4, w * 3), "dotted": (w, w * 2)}[style["dash"]]


def _arrow_head(o, size=None):
    x1, y1, x2, y2 = o["x1"], o["y1"], o["x2"], o["y2"]
    size = size or max(8, o["style"]["width"] * 5)
    a = math.atan2(y2 - y1, x2 - x1)
    return [(x2, y2), (x2 - size * math.cos(a - 0.4), y2 - size * math.sin(a - 0.4)),
            (x2 - size * math.cos(a + 0.4), y2 - size * math.sin(a + 0.4))]


def to_svg(doc):
    """The document as SVG text. SVG's Y axis points down, so every Y is flipped here."""
    s = doc.settings
    W, H = s["width"], s["height"]

    def P(p):
        return f"{p[0]:.3f},{H - p[1]:.3f}"

    def esc(t):
        return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;"))

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:g}" height="{H:g}" '
           f'viewBox="0 0 {W:g} {H:g}">',
           f'<rect width="{W:g}" height="{H:g}" fill="{esc(s["background"])}"/>']
    for o in doc.objects:
        if not o["visible"]:
            continue
        st = o["style"]
        attrs = (f'stroke="{st["stroke"] or "none"}" stroke-width="{st["width"]:g}" '
                 f'fill="{st["fill"] or "none"}" opacity="{st["opacity"]:g}"')
        d = _dash(st)
        if d:
            attrs += f' stroke-dasharray="{d[0]:g} {d[1]:g}"'
        t = o["type"]
        if t == "point":
            out.append(f'<circle cx="{o["x"]:.3f}" cy="{H - o["y"]:.3f}" r="{max(st["width"] * 1.5, 2):g}" '
                       f'fill="{st["stroke"]}" opacity="{st["opacity"]:g}"/>')
        elif t in ("line", "arrow"):
            out.append(f'<line x1="{o["x1"]:.3f}" y1="{H - o["y1"]:.3f}" x2="{o["x2"]:.3f}" '
                       f'y2="{H - o["y2"]:.3f}" {attrs} fill="none"/>')
            if t == "arrow":
                out.append(f'<polygon points="{" ".join(P(p) for p in _arrow_head(o))}" '
                           f'fill="{st["stroke"]}" opacity="{st["opacity"]:g}"/>')
        elif t in ("polyline", "freehand"):
            if len(o["points"]) > 1:
                out.append(f'<polyline points="{" ".join(P(p) for p in o["points"])}" {attrs} fill="none" '
                           f'stroke-linejoin="round" stroke-linecap="round"/>')
        elif t in ("rect", "square", "polygon"):
            out.append(f'<polygon points="{" ".join(P(p) for p in vertices(o))}" {attrs} '
                       f'stroke-linejoin="miter"/>')
        elif t == "circle":
            out.append(f'<circle cx="{o["cx"]:.3f}" cy="{H - o["cy"]:.3f}" r="{o["r"]:.3f}" {attrs}/>')
        elif t == "ellipse":
            out.append(f'<ellipse cx="{o["cx"]:.3f}" cy="{H - o["cy"]:.3f}" rx="{o["rx"]:.3f}" '
                       f'ry="{o["ry"]:.3f}" transform="rotate({-o["rot"]:g} {o["cx"]:.3f} {H - o["cy"]:.3f})" {attrs}/>')
        elif t == "text":
            weight = ' font-weight="bold"' if o["bold"] else ""
            style = ' font-style="italic"' if o["italic"] else ""
            lines = str(o["text"]).split("\n")
            tsp = "".join(f'<tspan x="{o["x"]:.3f}" dy="{0 if i == 0 else o["size"] * 1.2:g}">{esc(l)}</tspan>'
                          for i, l in enumerate(lines))
            y0 = H - o["y"] - (len(lines) - 1) * o["size"] * 1.2
            out.append(f'<text x="{o["x"]:.3f}" y="{y0:.3f}" font-size="{o["size"]:g}" font-family="sans-serif"'
                       f'{weight}{style} fill="{st["fill"] or st["stroke"]}" opacity="{st["opacity"]:g}" '
                       f'transform="rotate({-o["rot"]:g} {o["x"]:.3f} {H - o["y"]:.3f})">{tsp}</text>')
    out.append("</svg>")
    return "\n".join(out)


def render_png(doc, scale=1.0, transparent=False, background=None):
    """The document as a Pillow image (needs Pillow). `scale` = pixels per document unit."""
    from PIL import Image, ImageDraw, ImageFont
    s = doc.settings
    W, H = max(1, int(round(s["width"] * scale))), max(1, int(round(s["height"] * scale)))
    if W * H > 120_000_000:
        raise ValueError("That picture would be too large. Use a smaller scale.")
    bg = background or s["background"]
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0) if transparent else bg)
    hh = s["height"]

    def px(p):
        return (p[0] * scale, (hh - p[1]) * scale)

    def rgba(color, op):
        if not color:
            return None
        c = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        return c + (int(255 * op),)

    def dashed(d, pts, color, w, pattern):
        if not pattern:
            d.line(pts, fill=color, width=w, joint="curve")
            return
        on, off = pattern
        draw_on, left = True, on
        for a, b in zip(pts, pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            pos = 0.0
            while pos < L:
                step = min(left, L - pos)
                if draw_on:
                    p0 = (a[0] + (b[0] - a[0]) * pos / L, a[1] + (b[1] - a[1]) * pos / L)
                    p1 = (a[0] + (b[0] - a[0]) * (pos + step) / L, a[1] + (b[1] - a[1]) * (pos + step) / L)
                    d.line([p0, p1], fill=color, width=w)
                pos += step
                left -= step
                if left <= 1e-9:
                    draw_on = not draw_on
                    left = on if draw_on else off

    for o in doc.objects:
        if not o["visible"]:
            continue
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        st = o["style"]
        stroke, fill = rgba(st["stroke"], st["opacity"]), rgba(st["fill"], st["opacity"])
        w = max(1, int(round(st["width"] * scale)))
        pat = _dash(st, scale)
        t = o["type"]
        if t == "point":
            x, y = px((o["x"], o["y"]))
            r = max(st["width"] * 1.5, 2) * scale
            d.ellipse((x - r, y - r, x + r, y + r), fill=stroke)
        elif t == "text":
            size = max(6, int(o["size"] * scale))
            try:
                font = ImageFont.load_default(size=size)
            except TypeError:
                font = ImageFont.load_default()
            color = rgba(st["fill"] or st["stroke"], st["opacity"])
            lines = str(o["text"]).split("\n")
            tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            td = ImageDraw.Draw(tl)
            ax, ay = px((o["x"], o["y"]))
            top = ay - len(lines) * size * 1.2
            for i, line in enumerate(lines):
                td.text((ax, top + i * size * 1.2), line, fill=color, font=font)
            if o["rot"]:
                tl = tl.rotate(o["rot"], center=(ax, ay))
            layer = tl
        else:
            pts = [px(p) for p in outline(o)]
            closed = t in ("rect", "square", "polygon", "circle", "ellipse")
            if closed and fill:
                d.polygon(pts[:-1], fill=fill)
            if len(pts) > 1 and stroke:
                dashed(d, pts, stroke, w, pat)
            if t == "arrow":
                d.polygon([px(p) for p in _arrow_head(o)], fill=stroke)
        img = Image.alpha_composite(img, layer)
    return img if transparent else img.convert("RGB")


def exact(o, label):
    """An exact form (with pi / sqrt) for a Mathematics row, or "" when there is none."""
    t = o["type"]

    def num(v):
        return fmt(v, 4)

    if t == "circle":
        r = o["r"]
        if label == "Area":
            return f"{num(r * r)}π"
        if label == "Circumference":
            return f"{num(2 * r)}π"
    elif t == "square" and label == "Diagonal":
        return f"{num(o['side'])}√2"
    elif t == "ellipse" and label == "Area":
        return f"{num(o['rx'] * o['ry'])}π"
    elif t == "rect" and label == "Diagonal":
        s = o["w"] ** 2 + o["h"] ** 2
        if abs(s - round(s)) < 1e-9:
            return f"√{int(round(s))}"
    elif t in ("line", "arrow") and label == "Length":
        s = (o["x2"] - o["x1"]) ** 2 + (o["y2"] - o["y1"]) ** 2
        if abs(s - round(s)) < 1e-9:
            return f"√{int(round(s))}"
    return ""
