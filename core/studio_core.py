# core/studio_core.py - Srboli Studio: the document model and canvas engine. No Kivy.
#
# One infinite canvas; everything on it is an independent object:
#   text   (a box of text, light markdown)      shape (rect, rounded, ellipse, line, arrow)
#   frame  (an optional bounded area: page, slide ...)    group (several objects moved as one)
# World coordinates: x grows right, y grows DOWN (like a web page). An object occupies the box
# (x, y, w, h) and is turned `rot` degrees clockwise about its centre.
# Relations: obj["parent"] is the id of the frame or group that holds it (or None).
import copy
import io
import json
import math
import os
import re
import time
import zipfile

FORMAT = "srbcanvas"
VERSION = 1
TYPES = ("text", "shape", "frame", "group")
SHAPES = ("rect", "rounded", "ellipse", "line", "arrow")
FRAME_PRESETS = {"Slide 16:9": (1280, 720), "A4 portrait": (794, 1123),
                 "A4 landscape": (1123, 794), "Square": (800, 800), "Custom": (600, 400)}
MIN_SIZE = 4.0
MAX_UNDO = 200
MAX_OBJECTS = 5000
MAX_PACKAGE = 200 * 1024 * 1024          # unpacked size we are willing to read

DEFAULT_SETTINGS = {"title": "Untitled", "grid": True, "grid_size": 40.0, "snap_grid": False,
                    "snap_objects": True, "background": "#2B2D31"}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fmt(v, nd=1):
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.{nd}f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------- objects
def make(kind, **kw):
    """A new object of `kind` ("text", "shape", "frame", "group") with defaults; no id yet."""
    if kind not in TYPES:
        raise ValueError(f"unknown object type {kind!r}")
    o = {"type": kind, "name": "", "x": 0.0, "y": 0.0, "w": 160.0, "h": 100.0, "rot": 0.0,
         "visible": True, "locked": False, "parent": None, "opacity": 1.0}
    if kind == "text":
        o.update(w=240.0, h=40.0, text="Text", size=24.0, color="#F2F2F2", bold=False,
                 italic=False, align="left", mode="markdown", fill="", pad=8.0, autofit=True)
    elif kind == "shape":
        o.update(shape="rect", fill="#4A7BD0", stroke="#F2F2F2", width=2.0, radius=16.0,
                 fx=False, fy=False)
    elif kind == "frame":
        o.update(w=1280.0, h=720.0, bg="#FFFFFF", border="#8A8D93", preset="Slide 16:9")
    kw_style = kw.pop("style", None)
    o.update(kw)
    if kw_style:
        o.update(kw_style)
    return o


def center(o):
    return o["x"] + o["w"] / 2, o["y"] + o["h"] / 2


def rotate_pt(px, py, cx, cy, deg):
    """Rotate clockwise on screen (y down) about (cx, cy)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    dx, dy = px - cx, py - cy
    return cx + dx * c - dy * s, cy + dx * s + dy * c


def corners(o):
    """The four corners (top-left, top-right, bottom-right, bottom-left) after rotation."""
    cx, cy = center(o)
    pts = [(o["x"], o["y"]), (o["x"] + o["w"], o["y"]), (o["x"] + o["w"], o["y"] + o["h"]),
           (o["x"], o["y"] + o["h"])]
    return [rotate_pt(px, py, cx, cy, o["rot"]) for px, py in pts] if o["rot"] else pts


def bbox(o):
    """(x0, y0, x1, y1), axis aligned, covering the rotated object."""
    pts = corners(o)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else clamp(((px - a[0]) * dx + (py - a[1]) * dy) / L, 0.0, 1.0)
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def line_ends(o):
    """The two end points of a line / arrow object (world coordinates)."""
    x0, x1 = (o["x"] + o["w"], o["x"]) if o.get("fx") else (o["x"], o["x"] + o["w"])
    y0, y1 = (o["y"] + o["h"], o["y"]) if o.get("fy") else (o["y"], o["y"] + o["h"])
    a, b = (x0, y0), (x1, y1)           # a = tail, b = head (the arrow head is at b)
    if o["rot"]:
        cx, cy = center(o)
        a, b = rotate_pt(*a, cx, cy, o["rot"]), rotate_pt(*b, cx, cy, o["rot"])
    return a, b


def hit(o, px, py, tol):
    """Is the world point on this object? Frames only answer on their border and title strip."""
    t = o["type"]
    cx, cy = center(o)
    lx, ly = rotate_pt(px, py, cx, cy, -o["rot"]) if o["rot"] else (px, py)
    if t == "shape" and o["shape"] in ("line", "arrow"):
        a, b = line_ends(o)
        return seg_dist(px, py, a, b) <= tol + o["width"] / 2
    inside = o["x"] <= lx <= o["x"] + o["w"] and o["y"] <= ly <= o["y"] + o["h"]
    if t == "frame":
        if inside:
            edge = min(lx - o["x"], o["x"] + o["w"] - lx, ly - o["y"], o["y"] + o["h"] - ly)
            return edge <= tol
        return o["x"] <= lx <= o["x"] + min(o["w"], 220) and o["y"] - tol * 4 <= ly <= o["y"]
    if t == "shape" and o["shape"] == "ellipse":
        rx, ry = max(o["w"] / 2, 1e-9), max(o["h"] / 2, 1e-9)
        return ((lx - cx) / (rx + tol)) ** 2 + ((ly - cy) / (ry + tol)) ** 2 <= 1
    return o["x"] - tol <= lx <= o["x"] + o["w"] + tol and o["y"] - tol <= ly <= o["y"] + o["h"] + tol


# ---------------------------------------------------------------- text blocks
_BULLET = re.compile(r"^\s*([-*+]|\d+[.)])\s+(.*)$")


def parse_blocks(text, mode="markdown"):
    """Split text into display blocks [(kind, text)]; kind: h1 h2 h3 li quote code p.
    "plain" mode makes every line a paragraph."""
    lines = str(text).split("\n")
    if mode != "markdown":
        return [("p", l) for l in lines]
    out, code = [], None
    for l in lines:
        if l.strip().startswith("```"):
            if code is None:
                code = []
            else:
                out.append(("code", "\n".join(code)))
                code = None
            continue
        if code is not None:
            code.append(l)
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", l)
        if m:
            out.append((f"h{len(m.group(1))}", m.group(2)))
        elif l.startswith(">"):
            out.append(("quote", l[1:].strip()))
        elif _BULLET.match(l):
            mm = _BULLET.match(l)
            marker = "•" if mm.group(1) in "-*+" else mm.group(1)
            out.append(("li", f"{marker} {mm.group(2)}"))
        else:
            out.append(("p", l))
    if code is not None:
        out.append(("code", "\n".join(code)))
    return out or [("p", "")]


def inline_markup(text, escape):
    """**bold**, *italic* and `code` -> Kivy markup. `escape` escapes [ ] & in the raw text."""
    s = escape(text)
    s = re.sub(r"\*\*(.+?)\*\*", r"[b]\1[/b]", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"[i]\1[/i]", s)
    return s


BLOCK_SCALE = {"h1": 1.9, "h2": 1.45, "h3": 1.2, "li": 1.0, "quote": 1.0, "code": 0.9, "p": 1.0}


# ---------------------------------------------------------------- the document
class Document:
    def __init__(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.objects = []
        self._next = 1
        self._undo, self._redo = [], []

    # ----- lookup
    def get(self, oid):
        return next((o for o in self.objects if o["id"] == oid), None)

    def children(self, oid):
        return [o for o in self.objects if o["parent"] == oid]

    def descendants(self, oid):
        out, todo = [], [oid]
        while todo:
            cur = todo.pop()
            for c in self.children(cur):
                out.append(c)
                todo.append(c["id"])
        return out

    def ancestors(self, o):
        out, seen = [], set()
        p = o["parent"]
        while p is not None and p not in seen:
            seen.add(p)
            po = self.get(p)
            if po is None:
                break
            out.append(po)
            p = po["parent"]
        return out

    def effective_visible(self, o):
        return o["visible"] and all(a["visible"] for a in self.ancestors(o))

    def effective_locked(self, o):
        return o["locked"] or any(a["locked"] for a in self.ancestors(o))

    def top_level(self, o):
        """The object a click on `o` selects: its outermost group (frames are not climbed)."""
        cur = o
        for a in self.ancestors(o):
            if a["type"] == "group":
                cur = a
        return cur

    def draw_order(self):
        """Visible objects, back to front: frames first, then the rest in list order."""
        vis = [o for o in self.objects if self.effective_visible(o) and o["type"] != "group"]
        return [o for o in vis if o["type"] == "frame"] + [o for o in vis if o["type"] != "frame"]

    # ----- changes
    def add(self, o, parent=None):
        if len(self.objects) >= MAX_OBJECTS:
            raise ValueError("Too many objects.")
        o["id"] = self._next
        self._next += 1
        if parent is not None:
            o["parent"] = parent
        if not o["name"]:
            n = sum(1 for x in self.objects if x["type"] == o["type"]) + 1
            label = o.get("shape", o["type"]) if o["type"] == "shape" else o["type"]
            o["name"] = f"{label.capitalize()} {n}"
        self.objects.append(o)
        return o

    def remove(self, ids):
        gone = set(ids)
        for i in list(gone):
            gone |= {d["id"] for d in self.descendants(i)}
        self.objects = [o for o in self.objects if o["id"] not in gone]

    def duplicate(self, ids, offset=24.0):
        """Copies of the objects and everything inside them; returns the new top-level copies."""
        ids = [i for i in ids if self.get(i)]
        mapping, order = {}, []
        for i in ids:
            order.append(self.get(i))
            order += self.descendants(i)
        for o in order:
            c = copy.deepcopy(o)
            old = c["id"]
            nid = self._next
            self._next += 1
            c["id"] = nid
            mapping[old] = nid
            self.objects.append(c)
        out = []
        for old, nid in mapping.items():
            c = self.get(nid)
            if c["parent"] in mapping:
                c["parent"] = mapping[c["parent"]]
            elif old in ids:
                out.append(c)
        for c in out:
            c["name"] += " copy"
            translate_tree(self, c, offset, offset)
        return out

    def group(self, ids):
        """Group top-level objects that share a parent. Returns the group, or None."""
        objs = [o for o in (self.get(i) for i in ids) if o and o["type"] != "frame"]
        if len(objs) < 2 or len({o["parent"] for o in objs}) != 1:
            return None
        parent = objs[0]["parent"]
        g = make("group", parent=parent)
        self.add(g)
        # keep the group where its first member was in the stacking order
        self.objects.remove(g)
        idx = min(self.objects.index(o) for o in objs)
        self.objects.insert(idx, g)
        for o in objs:
            o["parent"] = g["id"]
        recalc_group(self, g)
        return g

    def ungroup(self, gid):
        g = self.get(gid)
        if not g or g["type"] != "group":
            return []
        kids = self.children(gid)
        for k in kids:
            k["parent"] = g["parent"]
        self.objects.remove(g)
        return kids

    def move_order(self, oid, step):
        """Raise (+1) or lower (-1) among objects of the same kind (frames / non-frames)."""
        o = self.get(oid)
        if not o:
            return
        same = [x for x in self.objects if (x["type"] == "frame") == (o["type"] == "frame")]
        i = same.index(o)
        if not 0 <= i + step < len(same):
            return
        other = same[i + step]
        a, b = self.objects.index(o), self.objects.index(other)
        self.objects[a], self.objects[b] = self.objects[b], self.objects[a]

    def to_edge(self, oid, front):
        o = self.get(oid)
        if o:
            self.objects.remove(o)
            if front:
                self.objects.append(o)
            else:
                self.objects.insert(0, o)

    def hit_test(self, x, y, tol):
        """The top-level object under the point (nothing hidden or locked)."""
        for o in reversed(self.draw_order()):
            if self.effective_locked(o):
                continue
            if hit(o, x, y, tol):
                return self.top_level(o)
        return None

    def content_bounds(self):
        vis = [bbox(o) for o in self.objects if o["type"] != "group" and self.effective_visible(o)]
        if not vis:
            return None
        return (min(b[0] for b in vis), min(b[1] for b in vis),
                max(b[2] for b in vis), max(b[3] for b in vis))

    # ----- history (snapshots; call checkpoint() BEFORE a change)
    def _snap(self):
        return json.dumps([self.objects, self._next, self.settings])

    def checkpoint(self):
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

    # ----- serialisation
    def to_dict(self):
        return {"settings": self.settings, "objects": self.objects}

    @classmethod
    def from_dict(cls, d):
        d = migrate(d)
        doc = cls()
        s = d.get("settings") or {}
        for k, dv in DEFAULT_SETTINGS.items():
            v = s.get(k, dv)
            if isinstance(dv, bool):
                v = bool(v)
            elif isinstance(dv, float):
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    v = dv
                if not math.isfinite(v) or v <= 0:
                    v = dv
            elif isinstance(dv, str):
                v = str(v)[:200] if isinstance(v, str) else dv
                if k == "background" and not _hex(v):
                    v = dv
            doc.settings[k] = v
        used = set()
        for od in (d.get("objects") or [])[:MAX_OBJECTS]:
            o = clean_object(od)
            if o is None:
                continue
            if o["id"] <= 0 or o["id"] in used:
                o["id"] = max(used or {0}) + 1
            used.add(o["id"])
            doc.objects.append(o)
        ids = {o["id"] for o in doc.objects}
        for o in doc.objects:                                  # drop dangling or cyclic parents
            if o["parent"] not in ids or o["parent"] == o["id"]:
                o["parent"] = None
        for o in doc.objects:                                  # break parent cycles
            if any(a["id"] == o["id"] for a in doc.ancestors(o)):
                o["parent"] = None
        doc._next = max(used or {0}) + 1
        return doc


def _hex(v):
    return isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v) is not None


def clean_object(d):
    """A safe object from untrusted data, or None."""
    if not isinstance(d, dict) or d.get("type") not in TYPES:
        return None
    try:
        o = make(d["type"])
        for k, dv in list(o.items()):
            if k not in d:
                continue
            v = d[k]
            if k == "parent":
                o[k] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
            elif isinstance(dv, bool):
                o[k] = bool(v)
            elif isinstance(dv, float):
                v = float(v)
                if not math.isfinite(v) or abs(v) > 1e8:
                    return None
                o[k] = v
            elif isinstance(dv, str):
                o[k] = str(v)[:50000] if k == "text" else str(v)[:200]
        for k in ("color", "fill", "stroke", "bg", "border"):
            if k in o and o[k] != "" and not _hex(o[k]):
                o[k] = make(d["type"])[k]
        o["w"], o["h"] = max(o["w"], 0.0), max(o["h"], 0.0)
        if o["type"] != "group":
            o["w"], o["h"] = (max(o["w"], 0.0), max(o["h"], 0.0)) if o.get("shape") in ("line", "arrow") \
                else (max(o["w"], MIN_SIZE), max(o["h"], MIN_SIZE))
        o["opacity"] = clamp(o["opacity"], 0.0, 1.0)
        o["rot"] = o["rot"] % 360
        if o["type"] == "shape" and o["shape"] not in SHAPES:
            o["shape"] = "rect"
        if o["type"] == "text":
            o["size"] = clamp(o["size"], 4.0, 400.0)
            o["align"] = o["align"] if o["align"] in ("left", "center", "right") else "left"
            o["mode"] = o["mode"] if o["mode"] in ("markdown", "plain") else "markdown"
        if o["type"] == "shape":
            o["width"] = clamp(o["width"], 0.0, 200.0)
        o["id"] = int(d.get("id", 0))
        return o
    except (TypeError, ValueError, KeyError):
        return None


def migrate(d):
    """Bring older canvas.json data up to VERSION. (Only version 1 exists so far.)"""
    if not isinstance(d, dict):
        raise ValueError("The canvas data is damaged.")
    v = int(d.get("version", 1))
    if v > VERSION:
        raise ValueError("This file was made by a newer Srboli Studio.")
    return d


# ---------------------------------------------------------------- transforms
def translate_tree(doc, o, dx, dy):
    for t in [o] + doc.descendants(o["id"]):
        t["x"] += dx
        t["y"] += dy


def recalc_group(doc, g):
    """A group's box is the box around everything inside it."""
    kids = [k for k in doc.descendants(g["id"]) if k["type"] != "group"]
    if not kids:
        return
    bs = [bbox(k) for k in kids]
    g["x"], g["y"] = min(b[0] for b in bs), min(b[1] for b in bs)
    g["w"], g["h"] = max(b[2] for b in bs) - g["x"], max(b[3] for b in bs) - g["y"]
    g["rot"] = 0.0


def refresh_groups(doc):
    for g in [o for o in doc.objects if o["type"] == "group"]:
        recalc_group(doc, g)


def scale_tree(doc, o, ax, ay, sx, sy):
    """Scale `o` (and what is inside it) about the point (ax, ay)."""
    for t in [o] + doc.descendants(o["id"]):
        cx, cy = center(t)
        ncx, ncy = ax + (cx - ax) * sx, ay + (cy - ay) * sy
        t["w"], t["h"] = t["w"] * abs(sx), t["h"] * abs(sy)
        t["x"], t["y"] = ncx - t["w"] / 2, ncy - t["h"] / 2
        if t["type"] == "text" and t["autofit"]:
            t["size"] = clamp(t["size"] * (abs(sx) + abs(sy)) / 2, 4.0, 400.0)
        if t["type"] == "shape" and t["shape"] in ("line", "arrow"):
            if sx < 0:
                t["fx"] = not t["fx"]
            if sy < 0:
                t["fy"] = not t["fy"]


def rotate_tree(doc, o, cx, cy, deg):
    for t in [o] + doc.descendants(o["id"]):
        if t["type"] == "group":
            continue
        tx, ty = center(t)
        nx, ny = rotate_pt(tx, ty, cx, cy, deg)
        t["x"], t["y"] = nx - t["w"] / 2, ny - t["h"] / 2
        t["rot"] = (t["rot"] + deg) % 360


def resize_box(o, handle, px, py, keep_ratio=False):
    """Drag a resize handle of one object to the world point (px, py).
    handle = (hx, hy), each -1, 0 or 1 (e.g. (1, 1) = bottom-right). The opposite edge stays put."""
    hx, hy = handle
    cx, cy = center(o)
    lx, ly = rotate_pt(px, py, cx, cy, -o["rot"]) if o["rot"] else (px, py)
    lx, ly = lx - cx, ly - cy
    w, h = o["w"], o["h"]
    nw = max(hx * lx + w / 2, MIN_SIZE) if hx else w
    nh = max(hy * ly + h / 2, MIN_SIZE) if hy else h
    if keep_ratio and hx and hy and w > 0 and h > 0:
        k = max(nw / w, nh / h)
        nw, nh = w * k, h * k
    dx, dy = hx * (nw - w) / 2, hy * (nh - h) / 2
    ndx, ndy = rotate_pt(dx, dy, 0, 0, o["rot"]) if o["rot"] else (dx, dy)
    ncx, ncy = cx + ndx, cy + ndy
    o["w"], o["h"] = nw, nh
    o["x"], o["y"] = ncx - nw / 2, ncy - nh / 2


def assign_parent(doc, o):
    """After a move: put a top-level object into the frame under its centre (or none)."""
    if o["type"] == "frame" or (o["parent"] is not None and doc.get(o["parent"]) and
                                doc.get(o["parent"])["type"] == "group"):
        return
    cx, cy = center(o) if o["type"] != "group" else center(o)
    new = None
    skip = {o["id"]} | {d["id"] for d in doc.descendants(o["id"])}
    for f in reversed([x for x in doc.objects if x["type"] == "frame" and x["id"] not in skip
                       and doc.effective_visible(x)]):
        lx, ly = rotate_pt(cx, cy, *center(f), -f["rot"]) if f["rot"] else (cx, cy)
        if f["x"] <= lx <= f["x"] + f["w"] and f["y"] <= ly <= f["y"] + f["h"]:
            new = f["id"]
            break
    o["parent"] = new


def selection_box(doc, objs):
    """Box used for the selection handles: (x, y, w, h, rot). A single plain object keeps its
    own rotation; groups and multi-selections use the axis-aligned box around everything."""
    if len(objs) == 1 and objs[0]["type"] not in ("group",):
        o = objs[0]
        return o["x"], o["y"], o["w"], o["h"], o["rot"]
    bs = [bbox(o) for o in objs]
    x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
    x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
    return x0, y0, x1 - x0, y1 - y0, 0.0


def align(objs, how):
    """Align top-level objects (moving whatever they contain with them is the caller's job
    through translate deltas): returns [(obj, dx, dy)]."""
    if len(objs) < 2:
        return []
    bs = [bbox(o) for o in objs]
    x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
    x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
    out = []
    for o, b in zip(objs, bs):
        dx = dy = 0.0
        if how == "left":
            dx = x0 - b[0]
        elif how == "right":
            dx = x1 - b[2]
        elif how == "hcenter":
            dx = (x0 + x1) / 2 - (b[0] + b[2]) / 2
        elif how == "top":
            dy = y0 - b[1]
        elif how == "bottom":
            dy = y1 - b[3]
        elif how == "vcenter":
            dy = (y0 + y1) / 2 - (b[1] + b[3]) / 2
        out.append((o, dx, dy))
    return out


def distribute(objs, axis):
    """Even gaps between 3+ objects along "h" or "v": returns [(obj, dx, dy)]."""
    if len(objs) < 3:
        return []
    i = 0 if axis == "h" else 1
    ordered = sorted(objs, key=lambda o: bbox(o)[i])
    first, last = bbox(ordered[0]), bbox(ordered[-1])
    total = (last[i + 2] - first[i]) - sum(bbox(o)[i + 2] - bbox(o)[i] for o in ordered)
    gap = total / (len(ordered) - 1)
    pos, out = first[i], []
    for o in ordered:
        b = bbox(o)
        d = pos - b[i]
        out.append((o, d if axis == "h" else 0.0, d if axis == "v" else 0.0))
        pos += (b[i + 2] - b[i]) + gap
    return out


def snap_box(others, box, thr):
    """Edge / centre alignment snapping for a box being moved.
    others: [(x0, y0, x1, y1)]; box: (x0, y0, x1, y1). Returns (dx, dy, guides) where guides is
    [("v", x) or ("h", y)] lines to draw."""
    best_x = best_y = None
    gx = gy = None
    bx = [box[0], (box[0] + box[2]) / 2, box[2]]
    by = [box[1], (box[1] + box[3]) / 2, box[3]]
    for o in others:
        ox = [o[0], (o[0] + o[2]) / 2, o[2]]
        oy = [o[1], (o[1] + o[3]) / 2, o[3]]
        for a in bx:
            for b in ox:
                d = b - a
                if abs(d) <= thr and (best_x is None or abs(d) < abs(best_x)):
                    best_x, gx = d, b
        for a in by:
            for b in oy:
                d = b - a
                if abs(d) <= thr and (best_y is None or abs(d) < abs(best_y)):
                    best_y, gy = d, b
    guides = ([("v", gx)] if gx is not None else []) + ([("h", gy)] if gy is not None else [])
    return best_x or 0.0, best_y or 0.0, guides


def snap_grid(v, size):
    return round(v / size) * size if size > 0 else v


# ---------------------------------------------------------------- .srbcanvas package
def manifest(doc, now=None):
    return {"format": FORMAT, "version": VERSION, "app": "Srboli Studio",
            "title": doc.settings.get("title", "Untitled"),
            "saved": now or time.strftime("%Y-%m-%dT%H:%M:%S"),
            "objects": len(doc.objects)}


def save_package(doc, path, view=None, thumbnail=None, assets=None):
    """Write the workspace as a ZIP package (manifest.json, canvas.json, assets/, previews/).
    The previous file is kept as <name>.bak. `assets` maps a file name to bytes."""
    canvas = dict(doc.to_dict())
    canvas["version"] = VERSION
    if view:
        canvas["view"] = list(view)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(doc), indent=1))
        z.writestr("canvas.json", json.dumps(canvas, ensure_ascii=False))
        for name, data in (assets or {}).items():
            z.writestr("assets/" + os.path.basename(name), data)
        if thumbnail:
            z.writestr("previews/thumbnail.png", thumbnail)
    if os.path.exists(path):
        try:
            os.replace(path, path + ".bak")
        except OSError:
            pass
    os.replace(tmp, path)


def load_package(path):
    """Read a .srbcanvas file. Returns (Document, view or None, meta). Raises ValueError."""
    try:
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_PACKAGE:
                raise ValueError("The file is too large to open safely.")
            names = set(z.namelist())
            if "manifest.json" not in names or "canvas.json" not in names:
                raise ValueError("This is not a Srboli Studio file.")
            meta = json.loads(z.read("manifest.json").decode("utf-8"))
            if meta.get("format") != FORMAT:
                raise ValueError("This is not a Srboli Studio file.")
            if int(meta.get("version", 1)) > VERSION:
                raise ValueError("This file was made by a newer Srboli Studio.")
            canvas = json.loads(z.read("canvas.json").decode("utf-8"))
    except zipfile.BadZipFile:
        raise ValueError("The file is damaged (not a valid package).")
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
        raise ValueError("The file is damaged (unreadable data).")
    doc = Document.from_dict(canvas)
    view = canvas.get("view")
    if not (isinstance(view, list) and len(view) == 3 and all(
            isinstance(v, (int, float)) and math.isfinite(v) for v in view)):
        view = None
    return doc, view, meta


def recovery_path(folder, name="workspace"):
    return os.path.join(folder, f"{name}.autosave.srbcanvas")


# ---------------------------------------------------------------- previews
def render_preview(doc, max_side=320):
    """A small PNG (bytes) of the whole canvas, or None without Pillow / without content."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    b = doc.content_bounds()
    if not b:
        return None
    pad = 20.0
    x0, y0, x1, y1 = b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad
    k = max_side / max(x1 - x0, y1 - y0, 1.0)
    W, H = max(1, int((x1 - x0) * k)), max(1, int((y1 - y0) * k))
    img = Image.new("RGB", (W, H), doc.settings.get("background", "#2B2D31"))
    d = ImageDraw.Draw(img)

    def P(px, py):
        return ((px - x0) * k, (py - y0) * k)

    for o in doc.draw_order():
        pts = [P(*c) for c in corners(o)]
        if o["type"] == "frame":
            d.polygon(pts, fill=o["bg"], outline=o["border"])
        elif o["type"] == "text":
            if o["fill"]:
                d.polygon(pts, fill=o["fill"])
            n = max(1, int(o["h"] / max(o["size"] * 1.3, 1)))
            for i in range(min(n, 12)):
                ly = o["y"] + o["pad"] + (i + 0.5) * o["size"] * 1.3
                if ly > o["y"] + o["h"]:
                    break
                d.line([P(o["x"] + o["pad"], ly), P(o["x"] + o["w"] * (0.9 if i < n - 1 else 0.5), ly)],
                       fill=o["color"], width=max(1, int(o["size"] * k * 0.5)))
        elif o["type"] == "shape":
            if o["shape"] in ("line", "arrow"):
                a, bb = line_ends(o)
                d.line([P(*a), P(*bb)], fill=o["stroke"], width=max(1, int(o["width"] * k)))
            elif o["shape"] == "ellipse":
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                d.ellipse((min(xs), min(ys), max(xs), max(ys)), fill=o["fill"] or None, outline=o["stroke"])
            else:
                d.polygon(pts, fill=o["fill"] or None, outline=o["stroke"])
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


# ---------------------------------------------------------------- lines, view, recovery
def set_line_end(o, idx, px, py):
    """Move the tail (idx 0) or head (idx 1) of a line / arrow to a world point. A turned line
    is first straightened (its turn is folded into the end points)."""
    pts = list(line_ends(o))
    pts[idx] = (px, py)
    (ax, ay), (bx, by) = pts
    o["x"], o["y"] = min(ax, bx), min(ay, by)
    o["w"], o["h"] = abs(bx - ax), abs(by - ay)
    o["fx"], o["fy"] = ax > bx, ay > by
    o["rot"] = 0.0


def roots(doc, ids):
    """The objects of `ids` that are not inside another object of `ids`."""
    ids = {i for i in ids if doc.get(i)}
    out = []
    for i in ids:
        o = doc.get(i)
        if not any(a["id"] in ids for a in doc.ancestors(o)):
            out.append(o)
    return sorted(out, key=lambda o: doc.objects.index(o))


class View:
    """Pan and zoom. World y grows down; screen y (Kivy) grows up from the bottom, so the
    conversion needs the canvas height `h`. (ox, oy) is the world point at the top-left."""

    def __init__(self, zoom=1.0, ox=0.0, oy=0.0):
        self.zoom, self.ox, self.oy = zoom, ox, oy
        self.h = 600.0

    def to_screen(self, x, y):
        return (x - self.ox) * self.zoom, self.h - (y - self.oy) * self.zoom

    def to_world(self, sx, sy):
        return sx / self.zoom + self.ox, (self.h - sy) / self.zoom + self.oy

    def pan(self, dsx, dsy):
        """Move the picture by a screen delta (Kivy touch dx, dy)."""
        self.ox -= dsx / self.zoom
        self.oy += dsy / self.zoom

    def zoom_at(self, sx, sy, factor):
        wx, wy = self.to_world(sx, sy)
        self.zoom = clamp(self.zoom * factor, 0.02, 40.0)
        self.ox = wx - sx / self.zoom
        self.oy = wy - (self.h - sy) / self.zoom

    def fit(self, bounds, w, h, pad=40.0):
        self.h = h
        if not bounds:
            self.zoom, self.ox, self.oy = 1.0, -w / 2, -h / 2
            return
        bw, bh = max(bounds[2] - bounds[0], 1.0), max(bounds[3] - bounds[1], 1.0)
        self.zoom = clamp(min((w - 2 * pad) / bw, (h - 2 * pad) / bh, 4.0), 0.02, 40.0)
        self.ox = (bounds[0] + bounds[2]) / 2 - w / 2 / self.zoom
        self.oy = (bounds[1] + bounds[3]) / 2 - h / 2 / self.zoom

    def to_list(self):
        return [self.zoom, self.ox, self.oy]

    def from_list(self, v):
        self.zoom, self.ox, self.oy = clamp(float(v[0]), 0.02, 40.0), float(v[1]), float(v[2])


def autosave(doc, folder, view=None):
    """Write the recovery copy; never raises."""
    try:
        os.makedirs(folder, exist_ok=True)
        save_package(doc, recovery_path(folder), view=view)
        return True
    except OSError:
        return False


def has_recovery(folder):
    return os.path.exists(recovery_path(folder))


def clear_recovery(folder):
    for p in (recovery_path(folder), recovery_path(folder) + ".bak"):
        try:
            os.remove(p)
        except OSError:
            pass


def set_geom(doc, o, key, val):
    """Apply a typed value for x, y, w, h or rot to one object (groups move/scale/turn what they
    hold). Returns False when the value is refused."""
    try:
        val = float(val)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(val) or abs(val) > 1e7:
        return False
    line = o["type"] == "shape" and o.get("shape") in ("line", "arrow")
    if key in ("x", "y"):
        translate_tree(doc, o, val - o["x"] if key == "x" else 0.0,
                       val - o["y"] if key == "y" else 0.0)
    elif key in ("w", "h"):
        if val < (0.0 if line else MIN_SIZE):
            return False
        if o["type"] == "group":
            if o[key] <= 0:
                return False
            sx = val / o["w"] if key == "w" else 1.0
            sy = val / o["h"] if key == "h" else 1.0
            scale_tree(doc, o, o["x"], o["y"], sx, sy)
            recalc_group(doc, o)
        else:
            o[key] = val
            if o["type"] == "text" and key == "h":
                o["autofit"] = False
    elif key == "rot":
        if o["type"] == "group":
            rotate_tree(doc, o, *center(o), val)
            recalc_group(doc, o)
        else:
            o["rot"] = val % 360
    else:
        return False
    refresh_groups(doc)
    return True
