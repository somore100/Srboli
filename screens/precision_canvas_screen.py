# screens/precision_canvas_screen.py - Precision Canvas: paint with mathematical precision.
# Editable geometric objects (not pixels) with exact numbers, snapping, a live maths panel,
# undo/redo, layers, .srbd save/load and SVG/PNG export. Logic: core/precision_canvas_core.py.
import copy
import math
import os
import time

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, Mesh, PopMatrix, PushMatrix, Rectangle,
                           Rotate, Triangle)
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.stencilview import StencilView
from kivy.uix.textinput import TextInput

import app_data
from core import drawing_core
from core import precision_canvas_core as pc
from core import theme

OFF = (0.25, 0.25, 0.25, 1)
TOOLS = [("select", "Select"), ("pan", "Pan"), ("point", "Point"), ("line", "Line"),
         ("arrow", "Arrow"), ("polyline", "Polyline"), ("rect", "Rect"), ("square", "Square"),
         ("circle", "Circle"), ("ellipse", "Ellipse"), ("polygon", "Polygon"),
         ("text", "Text"), ("freehand", "Free")]
HINTS = {
    "select": "Click to select, drag to move, drag a box to select several. Shift adds.",
    "pan": "Drag to pan. The mouse wheel zooms at the cursor; two fingers pan and pinch.",
    "point": "Click to place a point.",
    "line": "Drag from the start to the end of the line.",
    "arrow": "Drag from the tail to the head.",
    "polyline": "Click each corner. Double-click or press Enter to finish, Esc to cancel.",
    "rect": "Drag from one corner to the opposite corner.",
    "square": "Drag from one corner; the side follows the larger distance.",
    "circle": "Drag from the centre outwards; the distance is the radius.",
    "ellipse": "Drag across the box that holds the ellipse.",
    "polygon": "Drag from the centre outwards. Change the number of sides below.",
    "text": "Click where the text starts.",
    "freehand": "Hold and draw. Switches to Free mode (no snapping).",
}
MODES = {"Strict": "strict", "Assisted": "assisted", "Free": "free"}
MODE_NAMES = {v: k for k, v in MODES.items()}
FOLDER = "precision"


def _label(text, size=12, color=None, h=None, **kw):
    lb = Label(text=text, font_size=sp(size), color=color or (1, 1, 1, 1), halign="left",
               valign="middle", size_hint_y=None, height=h or dp(24), markup=True, **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lb


def _wrap_label(text, size=12, color=None):
    lb = Label(text=text, font_size=sp(size), color=color or theme.MUTED, halign="left",
               valign="top", size_hint_y=None, markup=True)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lb.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(4)))
    return lb


def _rgb(hexs, a=1.0):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


# ====================================================================== the canvas
class PCanvas(StencilView):
    """Draws a Document and turns touches into precise edits."""

    def __init__(self, doc, **kw):
        super().__init__(**kw)
        self.doc = doc
        self.view = pc.View()
        self.tool = "select"
        self.sel = set()
        self.sides = 6
        self.style = pc.new_style()
        self.shift = False
        self.on_change = lambda: None
        self.on_select = lambda: None
        self.on_hint = lambda text: None
        self.on_cursor = lambda x, y: None
        self.on_live = lambda: None
        self.on_view = lambda: None
        self.on_text_request = lambda x, y: None
        self.on_tool = lambda tool: None
        self._touches = {}
        self._pinch = None
        self._mode = None
        self._start = self._cur = None
        self._poly = []
        self._free = []
        self._snapk = None
        self._hover = None
        self._fitted = False
        self._origs = {}
        self._moved = False
        self._handle = None
        self._marquee = None
        self._ref = None
        self._tex_cache = {}
        self.bind(pos=self.redraw, size=self._resized)

    # ----- helpers
    def _resized(self, *a):
        if not self._fitted and self.width > 50 and self.height > 50:
            self._fitted = True
            self.fit()
        self.redraw()

    def _loc(self, pos):
        return pos[0] - self.x, pos[1] - self.y

    def S(self, x, y):
        sx, sy = self.view.to_screen(x, y)
        return self.x + sx, self.y + sy

    def fit(self):
        self.view.fit(self.doc.bounds(), self.width, self.height)
        self.redraw()
        self.on_view()

    def zoom_by(self, f):
        self.view.zoom_at(self.width / 2, self.height / 2, f)
        self.redraw()
        self.on_view()

    def selected(self):
        return [o for o in self.doc.objects if o["id"] in self.sel]

    def set_sel(self, ids):
        self.sel = set(ids)
        self.on_select()
        self.redraw()

    def prune_sel(self):
        alive = {o["id"] for o in self.doc.objects}
        if not self.sel <= alive:
            self.sel &= alive
            self.on_select()

    def _mode_name(self):
        return self.doc.settings["mode"]

    def _point(self, pos, exclude=()):
        """Document point under a touch, snapped according to the mode."""
        x, y = self.view.to_doc(*self._loc(pos))
        s = self.doc.settings
        if s["mode"] == "free":
            return x, y, None
        return pc.snap(self.doc, x, y, 10 / self.view.zoom, exclude=exclude,
                       points=s["snap_points"], grid=s["snap_grid"], align=s["snap_align"])

    def _angle_lock(self, a, p, kind):
        s = self.doc.settings
        if s["mode"] == "free" or kind not in (None, "grid", "align"):
            return p
        step = s["angle_step"] if (s["mode"] == "strict" or self.shift) else 0
        if self.shift and not step:
            step = 15
        return pc.snap_angle(a, p, step) if step else p

    # ----- building a new object from a drag
    def _build(self, a, b):
        t, dx, dy = self.tool, b[0] - a[0], b[1] - a[1]
        eps = 1e-9
        st = copy.deepcopy(self.style)
        if t in ("line", "arrow"):
            if math.hypot(dx, dy) < eps:
                return None
            return pc.make(t, x1=a[0], y1=a[1], x2=b[0], y2=b[1], style=st)
        if t == "rect":
            if abs(dx) < eps or abs(dy) < eps:
                return None
            return pc.make(t, x=min(a[0], b[0]), y=min(a[1], b[1]), w=abs(dx), h=abs(dy), style=st)
        if t == "square":
            side = max(abs(dx), abs(dy))
            if side < eps:
                return None
            return pc.make(t, x=a[0] if dx >= 0 else a[0] - side,
                           y=a[1] if dy >= 0 else a[1] - side, side=side, style=st)
        if t == "circle":
            r = math.hypot(dx, dy)
            return pc.make(t, cx=a[0], cy=a[1], r=r, style=st) if r > eps else None
        if t == "ellipse":
            if abs(dx) < eps or abs(dy) < eps:
                return None
            return pc.make(t, cx=(a[0] + b[0]) / 2, cy=(a[1] + b[1]) / 2, rx=abs(dx) / 2,
                           ry=abs(dy) / 2, style=st)
        if t == "polygon":
            r = math.hypot(dx, dy)
            if r < eps:
                return None
            rot = math.degrees(math.atan2(dy, dx)) - 90
            step = self.doc.settings["angle_step"]
            if self.doc.settings["mode"] == "strict" and step:
                rot = round(rot / step) * step
            return pc.make(t, cx=a[0], cy=a[1], r=r, n=self.sides, rot=rot % 360, style=st)
        return None

    def _preview(self):
        if self._mode == "create" and self._start and self._cur:
            return self._build(self._start, self._cur)
        if self._mode == "freehand" and len(self._free) > 1:
            return pc.make("freehand", points=self._free, style=copy.deepcopy(self.style))
        if self.tool == "polyline" and self._poly:
            pts = self._poly + ([list(self._hover)] if self._hover else [])
            return pc.make("polyline", points=pts, style=copy.deepcopy(self.style))
        return None

    # ----- handles
    def handles(self, o):
        t = o["type"]
        if t in ("line", "arrow"):
            return [("p1", o["x1"], o["y1"]), ("p2", o["x2"], o["y2"])]
        if t == "polyline":
            return [(f"pt{i}", x, y) for i, (x, y) in enumerate(o["points"])]
        if t == "circle":
            return [("r", o["cx"] + o["r"], o["cy"])]
        if t == "polygon":
            v = pc.vertices(o)
            return [("r", v[0][0], v[0][1])]
        if t == "rect" and not o["rot"]:
            return [("c", o["x"] + o["w"], o["y"] + o["h"])]
        if t == "square" and not o["rot"]:
            return [("c", o["x"] + o["side"], o["y"] + o["side"])]
        if t == "ellipse" and not o["rot"]:
            return [("rx", o["cx"] + o["rx"], o["cy"]), ("ry", o["cx"], o["cy"] + o["ry"])]
        return []

    def _drag_handle(self, o, key, p, kind):
        t = o["type"]
        if t in ("line", "arrow"):
            other = (o["x2"], o["y2"]) if key == "p1" else (o["x1"], o["y1"])
            p = self._angle_lock(other, p, kind)
            if key == "p1":
                o["x1"], o["y1"] = p
            else:
                o["x2"], o["y2"] = p
        elif t == "polyline":
            i = int(key[2:])
            prev = o["points"][i - 1] if i > 0 else None
            if prev is not None:
                p = self._angle_lock(tuple(prev), p, kind)
            o["points"][i] = [p[0], p[1]]
        elif t in ("circle", "polygon"):
            r = math.hypot(p[0] - o["cx"], p[1] - o["cy"])
            if r > 1e-9:
                o["r"] = r
            if t == "polygon":
                rot = math.degrees(math.atan2(p[1] - o["cy"], p[0] - o["cx"])) - 90
                step = self.doc.settings["angle_step"]
                if self.doc.settings["mode"] == "strict" and step:
                    rot = round(rot / step) * step
                o["rot"] = rot % 360
        elif t == "rect" and key == "c":
            o["w"], o["h"] = max(p[0] - o["x"], 1e-6), max(p[1] - o["y"], 1e-6)
        elif t == "square" and key == "c":
            o["side"] = max(p[0] - o["x"], p[1] - o["y"], 1e-6)
        elif t == "ellipse":
            if key == "rx":
                o["rx"] = max(abs(p[0] - o["cx"]), 1e-6)
            else:
                o["ry"] = max(abs(p[1] - o["cy"]), 1e-6)

    # ----- touches
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        btn = getattr(touch, "button", "left")
        if btn in ("scrollup", "scrolldown"):
            lx, ly = self._loc(touch.pos)
            self.view.zoom_at(lx, ly, 1.15 if btn == "scrollup" else 1 / 1.15)
            self.redraw()
            self.on_view()
            return True
        touch.grab(self)
        self._touches[touch.uid] = touch
        if len(self._touches) >= 2:
            self._cancel()
            self._pinch = None
            self._mode = "pinch"
            return True
        if btn in ("middle", "right") or self.tool == "pan":
            self._mode = "pan"
            return True
        x, y, kind = self._point(touch.pos)
        self._snapk = (x, y, kind)
        t = self.tool
        if t == "select":
            self._select_down(touch, x, y)
        elif t == "point":
            self._add(pc.make("point", x=x, y=y, style=copy.deepcopy(self.style)))
            self._mode = "done"
        elif t == "text":
            self._mode = "done"
            self.on_text_request(x, y)
        elif t == "polyline":
            if touch.is_double_tap:
                self.finish_polyline()
                self._mode = "done"
            else:
                if self._poly:
                    p = self._angle_lock(tuple(self._poly[-1]), (x, y), kind)
                else:
                    p = (x, y)
                self._poly.append([p[0], p[1]])
                self._mode = "poly"
                self._hover = p
        elif t == "freehand":
            if self.doc.settings["mode"] != "free":
                self.doc.settings["mode"] = "free"
                self.on_change()
            fx, fy = self.view.to_doc(*self._loc(touch.pos))
            self._free = [[fx, fy]]
            self._mode = "freehand"
        else:
            self._start = self._cur = (x, y)
            self._mode = "create"
        self.redraw()
        return True

    def _select_down(self, touch, x, y):
        tol = 8 / self.view.zoom
        rx, ry = self.view.to_doc(*self._loc(touch.pos))
        sel = self.selected()
        if len(sel) == 1:
            for key, hx, hy in self.handles(sel[0]):
                if math.hypot(hx - rx, hy - ry) <= 12 / self.view.zoom:
                    self._mode, self._handle, self._moved = "handle", key, False
                    return
        o = self.doc.hit_test(rx, ry, tol)
        if o is not None:
            if self.shift:
                self.sel ^= {o["id"]}
            elif o["id"] not in self.sel:
                self.sel = {o["id"]}
            self.on_select()
            if o["id"] in self.sel:
                self._mode, self._moved = "move", False
                self._start = (rx, ry)
                self._origs = {s["id"]: copy.deepcopy(s) for s in self.selected()}
                first = self.selected()[0]
                cands = pc.snap_candidates(first)
                self._ref = min(((c[0], c[1]) for c in cands),
                                key=lambda c: math.hypot(c[0] - rx, c[1] - ry),
                                default=pc.center(first))
            else:
                self._mode = "done"
        else:
            if not self.shift:
                self.sel = set()
                self.on_select()
            self._mode = "marquee"
            self._marquee = ((rx, ry), (rx, ry))

    def on_touch_move(self, touch):
        if touch.uid not in self._touches:
            return super().on_touch_move(touch)
        if self._mode == "pinch":
            two = list(self._touches.values())
            if len(two) >= 2:
                a, b = two[0], two[1]
                mid = self._loc(((a.x + b.x) / 2, (a.y + b.y) / 2))
                d = math.hypot(a.x - b.x, a.y - b.y)
                if self._pinch and self._pinch[1] > 1:
                    self.view.pan(mid[0] - self._pinch[0][0], mid[1] - self._pinch[0][1])
                    self.view.zoom_at(mid[0], mid[1], d / self._pinch[1])
                    self.redraw()
                    self.on_view()
                self._pinch = (mid, d)
            return True
        if self._mode == "pan":
            self.view.pan(touch.dx, touch.dy)
            self.redraw()
            self.on_view()
            return True
        if self._mode is None or self._mode == "done":
            return True
        mode = self._mode
        if mode == "freehand":
            fx, fy = self.view.to_doc(*self._loc(touch.pos))
            lx, ly = self._free[-1]
            if math.hypot(fx - lx, fy - ly) * self.view.zoom >= 2.5:
                self._free.append([fx, fy])
        elif mode == "create":
            x, y, kind = self._point(touch.pos)
            if self.tool in ("line", "arrow"):
                x, y = self._angle_lock(self._start, (x, y), kind)
            self._cur = (x, y)
            self._snapk = (x, y, kind)
            self._hint_for(self._preview())
        elif mode == "poly":
            pass
        elif mode == "move":
            self._move(touch)
        elif mode == "handle":
            o = self.selected()[0]
            x, y, kind = self._point(touch.pos, exclude={o["id"]})
            if not self._moved:
                self.doc.checkpoint()
                self._moved = True
            self._drag_handle(o, self._handle, (x, y), kind)
            self._snapk = (x, y, kind)
            self.on_live()
        elif mode == "marquee":
            rx, ry = self.view.to_doc(*self._loc(touch.pos))
            self._marquee = (self._marquee[0], (rx, ry))
        self.redraw()
        return True

    def _move(self, touch):
        rx, ry = self.view.to_doc(*self._loc(touch.pos))
        dx, dy = rx - self._start[0], ry - self._start[1]
        if not self._moved and math.hypot(dx, dy) * self.view.zoom < 3:
            return
        s = self.doc.settings
        if s["mode"] != "free":
            tx, ty, kind = pc.snap(self.doc, self._ref[0] + dx, self._ref[1] + dy,
                                   10 / self.view.zoom, exclude=set(self._origs),
                                   points=s["snap_points"], grid=s["snap_grid"],
                                   align=s["snap_align"])
            self._snapk = (tx, ty, kind)
            dx, dy = tx - self._ref[0], ty - self._ref[1]
        if not self._moved:
            self.doc.checkpoint()
            self._moved = True
        for o in self.selected():
            orig = self._origs.get(o["id"])
            if orig:
                for k, v in orig.items():
                    o[k] = copy.deepcopy(v)
                pc.translate(o, dx, dy)
        self.on_live()

    def _hint_for(self, o):
        if o is None:
            return
        t = o["type"]
        if t in ("line", "arrow"):
            self.on_hint(f"Length {pc.fmt(pc.get_field(o, 'length'))}   Angle {pc.fmt(pc.get_field(o, 'angle'))}°")
        elif t in ("rect", "ellipse"):
            w, h = (o["w"], o["h"]) if t == "rect" else (o["rx"] * 2, o["ry"] * 2)
            self.on_hint(f"{pc.fmt(w)} × {pc.fmt(h)}")
        elif t == "square":
            self.on_hint(f"Side {pc.fmt(o['side'])}")
        elif t in ("circle", "polygon"):
            self.on_hint(f"Radius {pc.fmt(o['r'])}")
        self.on_live()

    def on_touch_up(self, touch):
        if touch.uid not in self._touches:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        self._touches.pop(touch.uid, None)
        if self._mode == "pinch":
            if len(self._touches) < 2:
                self._mode = "done" if self._touches else None
                self._pinch = None
            return True
        mode, self._mode = self._mode, None
        if mode == "create":
            o = self._build(self._start, self._cur)
            if o is not None:
                self._add(o)
        elif mode == "freehand":
            if len(self._free) > 1:
                self._add(pc.make("freehand", points=self._free, style=copy.deepcopy(self.style)))
            self._free = []
        elif mode == "poly":
            self._mode = "poly"      # stays active between clicks
            self._mode = None
        elif mode == "move" or mode == "handle":
            if self._moved:
                self.on_change()
        elif mode == "marquee":
            (x0, y0), (x1, y1) = self._marquee
            self._marquee = None
            if abs(x1 - x0) * self.view.zoom > 4 or abs(y1 - y0) * self.view.zoom > 4:
                lo = (min(x0, x1), min(y0, y1))
                hi = (max(x0, x1), max(y0, y1))
                picked = {o["id"] for o in self.doc.objects if o["visible"] and not o["locked"]
                          and self._inside(pc.bbox(o), lo, hi)}
                self.sel = (self.sel | picked) if self.shift else picked
                self.on_select()
        self._snapk = None
        self._start = self._cur = None
        self.redraw()
        return True

    @staticmethod
    def _inside(b, lo, hi):
        return b[0] >= lo[0] and b[1] >= lo[1] and b[2] <= hi[0] and b[3] <= hi[1]

    def _cancel(self):
        self._mode = None
        self._start = self._cur = None
        self._free = []
        self._marquee = None
        if self._moved:
            self.on_change()
        self._moved = False

    def _add(self, o):
        self.doc.checkpoint()
        try:
            self.doc.add(o)
        except ValueError as e:
            self.doc._undo.pop()
            self.on_hint(str(e))
            return
        self.sel = {o["id"]}
        self.on_select()
        self.on_change()

    def finish_polyline(self):
        pts = self._poly
        self._poly = []
        while len(pts) > 1 and pts[-1] == pts[-2]:
            pts.pop()
        if len(pts) >= 2:
            self._add(pc.make("polyline", points=pts, style=copy.deepcopy(self.style)))
        self.redraw()

    def cancel_polyline(self):
        self._poly = []
        self.redraw()

    def hover(self, pos):
        if not self.collide_point(*pos):
            return
        x, y, kind = self._point(pos) if self.tool not in ("select", "pan", "text", "freehand") else (
            *self.view.to_doc(*self._loc(pos)), None)
        rx, ry = self.view.to_doc(*self._loc(pos))
        self.on_cursor(rx, ry)
        changed = False
        if self.tool not in ("select", "pan", "freehand", "text") and self._mode is None:
            if self.tool == "polyline" and self._poly:
                p = self._angle_lock(tuple(self._poly[-1]), (x, y), kind)
                self._hover = p
            self._snapk = (x, y, kind)
            changed = True
        if changed:
            self.redraw()

    # ----- drawing
    def redraw(self, *a):
        self.canvas.clear()
        v, s = self.view, self.doc.settings
        with self.canvas:
            Color(0.13, 0.14, 0.16, 1)
            Rectangle(pos=self.pos, size=self.size)
            px, py = self.S(0, 0)
            Color(*_rgb(s["background"]))
            Rectangle(pos=(px, py), size=(s["width"] * v.zoom, s["height"] * v.zoom))
            if s["grid"]:
                self._grid()
            Color(0.5, 0.5, 0.5, 0.8)
            Line(rectangle=(px, py, s["width"] * v.zoom, s["height"] * v.zoom), width=1)
            for o in self.doc.objects:
                if o["visible"]:
                    self._draw(o)
            pv = self._preview()
            if pv:
                self._draw(pv, ghost=True)
            for o in self.selected():
                if o["visible"]:
                    self._draw_sel(o)
            if self._marquee:
                (x0, y0), (x1, y1) = self._marquee
                ax, ay = self.S(min(x0, x1), min(y0, y1))
                Color(*theme.ACCENT[:3], 0.25)
                Rectangle(pos=(ax, ay), size=(abs(x1 - x0) * v.zoom, abs(y1 - y0) * v.zoom))
                Color(*theme.ACCENT)
                Line(rectangle=(ax, ay, abs(x1 - x0) * v.zoom, abs(y1 - y0) * v.zoom), width=1)
            if self._snapk and self._snapk[2]:
                self._draw_snap()

    def _grid(self):
        s, v = self.doc.settings, self.view
        g = s["grid_spacing"]
        if g <= 0 or g * v.zoom < 5:
            return
        x0, y0 = v.to_doc(0, 0)
        x1, y1 = v.to_doc(self.width, self.height)
        x0, x1 = max(x0, 0), min(x1, s["width"])
        y0, y1 = max(y0, 0), min(y1, s["height"])
        if x1 <= x0 or y1 <= y0:
            return
        i0, i1 = int(x0 // g), int(x1 // g) + 1
        j0, j1 = int(y0 // g), int(y1 // g) + 1
        if (i1 - i0) * (j1 - j0) > 40000:
            return
        major = max(1, int(s["grid_major"]))
        sx0, sy0 = self.S(x0, y0)
        sx1, sy1 = self.S(x1, y1)
        dark = sum(_rgb(s["background"])[:3]) < 1.5
        base = 1.0 if dark else 0.0
        if s["grid_type"] == "dots":
            Color(base, base, base, 0.45)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    gx, gy = self.S(i * g, j * g)
                    if sx0 - 1 <= gx <= sx1 + 1 and sy0 - 1 <= gy <= sy1 + 1:
                        sz = 3 if (i % major == 0 and j % major == 0) else 1.6
                        Ellipse(pos=(gx - sz / 2, gy - sz / 2), size=(sz, sz))
            return
        for i in range(i0, i1 + 1):
            gx = self.S(i * g, 0)[0]
            if sx0 - 1 <= gx <= sx1 + 1:
                Color(base, base, base, 0.30 if i % major == 0 else 0.12)
                Line(points=[gx, sy0, gx, sy1], width=1)
        for j in range(j0, j1 + 1):
            gy = self.S(0, j * g)[1]
            if sy0 - 1 <= gy <= sy1 + 1:
                Color(base, base, base, 0.30 if j % major == 0 else 0.12)
                Line(points=[sx0, gy, sx1, gy], width=1)

    def _flat(self, pts):
        out = []
        for x, y in pts:
            out += self.S(x, y)
        return out

    def _draw(self, o, ghost=False):
        st, z = o["style"], self.view.zoom
        a = st["opacity"] * (0.7 if ghost else 1)
        t = o["type"]
        lw = max(1.0, st["width"] * z)
        if t == "point":
            x, y = self.S(o["x"], o["y"])
            r = max(st["width"] * 1.5, 2) * z
            Color(*_rgb(st["stroke"], a))
            Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))
            return
        if t == "text":
            self._draw_text(o, a)
            return
        pts = pc.outline(o, 96)
        if len(pts) < 2:
            return
        closed = t in ("rect", "square", "polygon", "circle", "ellipse")
        if closed and st["fill"]:
            Color(*_rgb(st["fill"], a))
            flat = self._flat(pts[:-1])
            cx, cy = self.S(*pc.center(o))
            verts = [cx, cy, 0, 0]
            for i in range(0, len(flat), 2):
                verts += [flat[i], flat[i + 1], 0, 0]
            verts += [flat[0], flat[1], 0, 0]
            n = len(verts) // 4
            Mesh(vertices=verts, indices=list(range(n)), mode="triangle_fan")
        if st["stroke"]:
            Color(*_rgb(st["stroke"], a))
            kw = {}
            if st["dash"] == "dashed":
                kw = {"dash_length": lw * 4, "dash_offset": lw * 3}
            elif st["dash"] == "dotted":
                kw = {"dash_length": lw, "dash_offset": lw * 2}
            Line(points=self._flat(pts), width=lw / 2 if lw > 1 else 0.6, joint="round",
                 cap="round", **kw)
        if t == "arrow":
            h = pc._arrow_head(o, max(8, st["width"] * 5))
            Color(*_rgb(st["stroke"], a))
            fl = self._flat(h)
            Triangle(points=fl)

    def _draw_text(self, o, a):
        key = (o["text"], o["size"], o["bold"], o["italic"], round(self.view.zoom, 3))
        tex = self._tex_cache.get(key)
        if tex is None:
            if len(self._tex_cache) > 200:
                self._tex_cache.clear()
            size = max(4, min(400, o["size"] * self.view.zoom))
            lb = CoreLabel(text=o["text"], font_size=size, bold=o["bold"], italic=o["italic"])
            lb.refresh()
            tex = self._tex_cache[key] = lb.texture
        if tex is None:
            return
        st = o["style"]
        x, y = self.S(o["x"], o["y"])
        Color(*_rgb(st["fill"] or st["stroke"], a))
        PushMatrix()
        Rotate(angle=o["rot"], origin=(x, y))
        Rectangle(texture=tex, pos=(x, y), size=tex.size)
        PopMatrix()

    def _draw_sel(self, o):
        x0, y0, x1, y1 = pc.bbox(o)
        ax, ay = self.S(x0, y0)
        bx, by = self.S(x1, y1)
        Color(*theme.ACCENT)
        Line(rectangle=(ax - 4, ay - 4, bx - ax + 8, by - ay + 8), width=1, dash_length=5,
             dash_offset=4)
        if len(self.sel) == 1:
            for _k, hx, hy in self.handles(o):
                sx, sy = self.S(hx, hy)
                Color(1, 1, 1, 1)
                Rectangle(pos=(sx - 5, sy - 5), size=(10, 10))
                Color(*theme.ACCENT)
                Line(rectangle=(sx - 5, sy - 5, 10, 10), width=1.2)

    def _draw_snap(self):
        x, y, kind = self._snapk
        sx, sy = self.S(x, y)
        Color(1.0, 0.55, 0.1, 1)
        if kind == "grid":
            Line(points=[sx - 5, sy, sx + 5, sy], width=1.2)
            Line(points=[sx, sy - 5, sx, sy + 5], width=1.2)
        elif kind == "align":
            Line(points=[sx - 8, sy - 8, sx + 8, sy + 8], width=1.2)
        else:
            Line(circle=(sx, sy, 7), width=1.5)


# ====================================================================== the screen
class PrecisionCanvasScreen(Screen):
    title = "Precision Canvas"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.doc = pc.Document()
        self.path = None
        self.dirty = False
        self.clip = []
        self.tab = "props"
        self._inputs = {}
        self._popups = 0
        self._narrow = None
        self._panel_open = False
        self._ctrl = False

        root = BoxLayout(orientation="vertical", spacing=dp(2), padding=dp(4))
        root.add_widget(self._build_toolbar())
        self.main = BoxLayout(spacing=dp(3))
        self.palette = self._build_palette()
        self.canvas_w = PCanvas(self.doc)
        self.canvas_w.on_change = self._doc_changed
        self.canvas_w.on_select = self._sel_changed
        self.canvas_w.on_hint = self._hint
        self.canvas_w.on_cursor = self._cursor
        self.canvas_w.on_live = self._live
        self.canvas_w.on_view = self._view_changed
        self.canvas_w.on_text_request = self.ask_text
        self.center_col = BoxLayout(orientation="vertical")
        self.inspector = self._build_inspector()
        self.main.add_widget(self.palette)
        self.main.add_widget(self.center_col)
        root.add_widget(self.main)
        root.add_widget(self._build_status())
        self.add_widget(root)
        self.bind(size=lambda *a: self._relayout())
        self.set_tool("select")
        self._relayout(force=True)
        self._refresh_all()

    # ------------------------------------------------------------ layout
    def _relayout(self, force=False):
        narrow = self.width < dp(900)
        if not force and narrow == self._narrow:
            return
        self._narrow = narrow
        for w in (self.canvas_w, self.inspector):
            if w.parent:
                w.parent.remove_widget(w)
        for w in list(self.center_col.children):
            self.center_col.remove_widget(w)
        self.center_col.add_widget(self.canvas_w)
        if self.inspector.parent:
            self.inspector.parent.remove_widget(self.inspector)
        if narrow:
            self.inspector.size_hint = (1, None)
            self.inspector.height = dp(300)
            if self._panel_open:
                self.center_col.add_widget(self.inspector)
        else:
            self.inspector.size_hint = (None, 1)
            self.inspector.width = dp(310)
            self.main.add_widget(self.inspector)

    def toggle_panel(self):
        self._panel_open = not self._panel_open
        self._relayout(force=True)

    def _build_toolbar(self):
        sv = ScrollView(size_hint_y=None, height=dp(42), do_scroll_y=False, bar_width=dp(3))
        bar = BoxLayout(size_hint_x=None, spacing=dp(3))
        bar.bind(minimum_width=bar.setter("width"))
        self.zoom_label = Label(text="100%", font_size=sp(12), size_hint_x=None, width=dp(54))

        def add(text, fn, w=64):
            b = Button(text=text, size_hint_x=None, width=dp(w), font_size=sp(12))
            b.bind(on_release=lambda *a: fn())
            bar.add_widget(b)
            return b

        add("< Back", lambda: self._guard(self._leave), 70)
        t = Label(text="[b]Precision Canvas[/b]", markup=True, font_size=sp(14),
                  size_hint_x=None, width=dp(140))
        self.title_label = t
        bar.add_widget(t)
        add("New", self.new_doc, 50)
        add("Open", self.open_dialog, 56)
        add("Save", self.save, 54)
        add("Save As", self.save_as_dialog, 70)
        self.undo_btn = add("Undo", self.undo, 56)
        self.redo_btn = add("Redo", self.redo, 56)
        add("Copy", self.copy, 54)
        add("Paste", self.paste, 56)
        add("Duplicate", self.duplicate, 82)
        add("Delete", self.delete, 62)
        add("Zoom -", lambda: self.canvas_w.zoom_by(1 / 1.25), 62)
        bar.add_widget(self.zoom_label)
        add("Zoom +", lambda: self.canvas_w.zoom_by(1.25), 62)
        add("Fit", self.canvas_w_fit, 44)
        add("Export", self.export_dialog, 62)
        self.panel_btn = add("Panel", self.toggle_panel, 60)
        sv.add_widget(bar)
        return sv

    def canvas_w_fit(self):
        self.canvas_w.fit()

    def _build_palette(self):
        col = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(66), spacing=dp(2))
        self.tool_btns = {}
        for key, label in TOOLS:
            b = Button(text=label, font_size=sp(11))
            b.bind(on_release=lambda *a, k=key: self.set_tool(k))
            col.add_widget(b)
            self.tool_btns[key] = b
        self.sides_sp = Spinner(text="6 sides", values=[f"{n} sides" for n in (3, 4, 5, 6, 8, 10, 12)],
                                font_size=sp(10), size_hint_y=None, height=dp(30))
        self.sides_sp.bind(text=lambda w, t: setattr(self.canvas_w, "sides", int(t.split()[0])))
        col.add_widget(self.sides_sp)
        return col

    def _build_status(self):
        bar = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(3))
        self.cursor_label = _label("x 0   y 0", 11, theme.MUTED, h=dp(34))
        self.cursor_label.size_hint_x = None
        self.cursor_label.width = dp(130)
        self.hint_label = _label("", 11, theme.MUTED, h=dp(34))
        self.hint_label.shorten = True
        self.hint_label.shorten_from = "right"
        self.mode_sp = Spinner(text="Strict", values=list(MODES), font_size=sp(11),
                               size_hint_x=None, width=dp(84))
        self.mode_sp.bind(text=lambda w, t: self._set_setting("mode", MODES[t]))
        self.grid_btn = Button(text="Grid", font_size=sp(11), size_hint_x=None, width=dp(52))
        self.grid_btn.bind(on_release=lambda *a: self._set_setting("grid", not self.doc.settings["grid"]))
        self.snap_btn = Button(text="Snap", font_size=sp(11), size_hint_x=None, width=dp(52))
        self.snap_btn.bind(on_release=lambda *a: self._set_setting(
            "snap_grid", not self.doc.settings["snap_grid"]))
        self.zoom_status = _label("", 11, theme.MUTED, h=dp(34))
        self.zoom_status.size_hint_x = None
        self.zoom_status.width = dp(60)
        for w in (self.cursor_label, self.hint_label, self.zoom_status, self.mode_sp,
                  self.grid_btn, self.snap_btn):
            bar.add_widget(w)
        return bar

    def _build_inspector(self):
        box = BoxLayout(orientation="vertical", spacing=dp(2))
        tabs = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(2))
        self.tab_btns = {}
        for key, label in (("props", "Properties"), ("maths", "Maths"), ("layers", "Layers"),
                           ("doc", "Document")):
            b = Button(text=label, font_size=sp(11))
            b.bind(on_release=lambda *a, k=key: self.set_tab(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        box.add_widget(tabs)
        self.sv = ScrollView(do_scroll_x=False, bar_width=dp(4))
        self.panel = GridLayout(cols=1, size_hint_y=None, spacing=dp(4), padding=dp(4))
        self.panel.bind(minimum_height=self.panel.setter("height"))
        self.sv.add_widget(self.panel)
        box.add_widget(self.sv)
        return box

    # ------------------------------------------------------------ lifecycle / keys
    def on_pre_enter(self, *a):
        Window.bind(on_key_down=self._key_down, on_key_up=self._key_up, mouse_pos=self._mouse)
        self.canvas_w._fitted = self.canvas_w._fitted

    def on_leave(self, *a):
        Window.unbind(on_key_down=self._key_down, on_key_up=self._key_up, mouse_pos=self._mouse)

    def _mouse(self, win, pos):
        if self._popups == 0:
            self.canvas_w.hover(pos)

    def _typing(self):
        return any(getattr(t, "focus", False) for t in self._all_inputs())

    def _all_inputs(self):
        for w in self.panel.walk():
            if isinstance(w, TextInput):
                yield w

    def _key_up(self, win, key, *a):
        if key in (303, 304):
            self.canvas_w.shift = False
        if key in (305, 306, 309, 310, 311, 312):
            self._ctrl = False
        return False

    def _key_down(self, win, key, scancode, text, modifiers):
        if key in (303, 304):
            self.canvas_w.shift = True
        if key in (305, 306, 309, 310, 311, 312):
            self._ctrl = True
        if self._popups or not self.manager or self.manager.current != self.name:
            return False
        if self._typing():
            return False
        ctrl = "ctrl" in modifiers or "meta" in modifiers
        shift = "shift" in modifiers
        if ctrl and key == 122:          # z
            self.redo() if shift else self.undo()
        elif ctrl and key == 121:        # y
            self.redo()
        elif ctrl and key == 115:        # s
            self.save()
        elif ctrl and key == 100:        # d
            self.duplicate()
        elif ctrl and key == 99:         # c
            self.copy()
        elif ctrl and key == 118:        # v
            self.paste()
        elif ctrl and key == 97:         # a
            self.canvas_w.set_sel([o["id"] for o in self.doc.objects
                                   if o["visible"] and not o["locked"]])
        elif key in (127, 8):
            self.delete()
        elif key == 27:
            if self.canvas_w._poly:
                self.canvas_w.cancel_polyline()
            else:
                self.canvas_w.set_sel(())
        elif key in (13, 271):
            if self.canvas_w._poly:
                self.canvas_w.finish_polyline()
        elif key in (273, 274, 275, 276) and self.canvas_w.sel:
            step = (self.doc.settings["grid_spacing"] if shift else 1) or 1
            dx = {275: step, 276: -step}.get(key, 0)
            dy = {273: step, 274: -step}.get(key, 0)
            self._edit(lambda: [pc.translate(o, dx, dy) for o in self.canvas_w.selected()])
        else:
            return False
        return True

    # ------------------------------------------------------------ state
    def _hint(self, text):
        self.hint_label.text = text

    def _cursor(self, x, y):
        u = self.doc.settings["units"]
        self.cursor_label.text = f"x {pc.fmt(x)}   y {pc.fmt(y)}" + ("" if u == "u" else f" {u}")

    def _view_changed(self):
        pct = f"{self.canvas_w.view.zoom * 100:.0f}%"
        self.zoom_label.text = pct
        self.zoom_status.text = pct

    def _live(self):
        if self.tab == "maths":
            self.refresh_panel()
        else:
            self._sync_values()

    def set_tool(self, tool):
        if self.canvas_w._poly and tool != "polyline":
            self.canvas_w.finish_polyline()
        self.canvas_w.tool = tool
        for k, b in self.tool_btns.items():
            b.background_color = theme.ACCENT if k == tool else OFF
        self.hint_label.text = HINTS[tool]
        self.canvas_w._snapk = None
        self.canvas_w.redraw()

    def set_tab(self, tab):
        self.tab = tab
        self.refresh_panel()

    def _set_setting(self, key, val):
        if self.doc.settings.get(key) == val:
            return
        self.doc.checkpoint()
        self.doc.settings[key] = val
        self._doc_changed()
        self.canvas_w.redraw()

    def _doc_changed(self):
        self.dirty = True
        self.canvas_w.prune_sel()
        self._refresh_all()

    def _sel_changed(self):
        self.refresh_panel()

    def _refresh_all(self):
        s = self.doc.settings
        self.undo_btn.disabled = not self.doc._undo
        self.redo_btn.disabled = not self.doc._redo
        self.mode_sp.text = MODE_NAMES.get(s["mode"], "Strict")
        self.grid_btn.background_color = theme.ACCENT if s["grid"] else OFF
        self.snap_btn.background_color = theme.ACCENT if s["snap_grid"] else OFF
        name = os.path.basename(self.path) if self.path else "Untitled"
        self.title_label.text = f"[b]{name}{'*' if self.dirty else ''}[/b]"
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == self.tab else OFF
        self.canvas_w.redraw()
        self._view_changed()
        self.refresh_panel()

    def _edit(self, fn):
        """One undo step around a change made by `fn`."""
        self.doc.checkpoint()
        fn()
        self._doc_changed()

    # ------------------------------------------------------------ toolbar actions
    def undo(self):
        if self.doc.undo():
            self.dirty = True
            self.canvas_w.prune_sel()
            self._refresh_all()

    def redo(self):
        if self.doc.redo():
            self.dirty = True
            self.canvas_w.prune_sel()
            self._refresh_all()

    def delete(self):
        ids = [o["id"] for o in self.canvas_w.selected() if not o["locked"]]
        if ids:
            self._edit(lambda: self.doc.remove(ids))
            self.canvas_w.sel = set()
            self.canvas_w.on_select()

    def duplicate(self):
        ids = [o["id"] for o in self.canvas_w.selected()]
        if ids:
            new = []
            self._edit(lambda: new.extend(self.doc.duplicate(ids)))
            self.canvas_w.set_sel([o["id"] for o in new])

    def copy(self):
        self.clip = [copy.deepcopy(o) for o in self.canvas_w.selected()]
        self._hint(f"Copied {len(self.clip)} object(s).")

    def paste(self):
        if not self.clip:
            return
        new = []

        def do():
            for o in self.clip:
                c = copy.deepcopy(o)
                pc.translate(c, 20, -20)
                new.append(self.doc.add(c))
            for o in self.clip:
                pc.translate(o, 20, -20)   # the next paste lands further along

        self._edit(do)
        self.canvas_w.set_sel([o["id"] for o in new])

    def new_doc(self):
        self._guard(self._reset)

    def _reset(self):
        self.doc = pc.Document()
        self.canvas_w.doc = self.doc
        self.canvas_w.sel = set()
        self.canvas_w._poly = []
        self.path, self.dirty = None, False
        self.canvas_w.fit()
        self._refresh_all()

    def _leave(self):
        if self.manager:
            self.manager.current = "dashboard"

    def _guard(self, then):
        if not self.dirty:
            then()
            return
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        lay.add_widget(Label(text="This drawing has unsaved changes."))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        pop = self._popup("Unsaved changes", lay, 0.9, dp(170))
        for text, fn in (("Save", lambda: (self.save(), then()) if self.path else
                          self.save_as_dialog(then)),
                         ("Discard", then), ("Cancel", lambda: None)):
            b = Button(text=text)
            b.bind(on_release=lambda *a, f=fn: (pop.dismiss(), f()))
            row.add_widget(b)
        lay.add_widget(row)
        pop.open()

    # ------------------------------------------------------------ popups
    def _popup(self, title, content, wfrac=0.9, height=None, **kw):
        p = Popup(title=title, content=content, size_hint=(None, None if height else 0.9),
                  **kw)
        w = min(Window.width * wfrac, dp(560))
        p.width = w
        if height:
            p.height = min(height, Window.height * 0.95)
        p.bind(on_open=lambda *a: setattr(self, "_popups", self._popups + 1),
               on_dismiss=lambda *a: setattr(self, "_popups", max(0, self._popups - 1)))
        return p

    def ask_text(self, x, y):
        ti = TextInput(text="Text", multiline=True, font_size=sp(16), size_hint_y=None,
                       height=dp(100))
        ok = Button(text="Place text", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        lay.add_widget(ti)
        lay.add_widget(ok)
        pop = self._popup("Text", lay, 0.9, dp(240))

        def go(*a):
            pop.dismiss()
            if ti.text.strip():
                st = copy.deepcopy(self.canvas_w.style)
                self.canvas_w._add(pc.make("text", x=x, y=y, text=ti.text, size=18, style=st))

        ok.bind(on_release=go)
        pop.open()
        Clock.schedule_once(lambda dt: (setattr(ti, "focus", True), ti.select_all()), 0.2)

    def pick_color(self, title, allow_none, cb):
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        grid = GridLayout(cols=6, spacing=dp(3), size_hint_y=None, height=dp(120))
        pop = self._popup(title, lay, 0.9, dp(330))
        for h in drawing_core.PALETTE:
            b = Button(background_normal="", background_color=_rgb(h))
            b.bind(on_release=lambda *a, c=h: (pop.dismiss(), cb(c)))
            grid.add_widget(b)
        lay.add_widget(grid)
        ti = TextInput(text="#", multiline=False, size_hint_y=None, height=dp(38), font_size=sp(15))
        msg = _label("Type #RRGGBB", 11, theme.MUTED)
        use = Button(text="Use this colour", size_hint_y=None, height=dp(42))

        def go(*a):
            from core import color_core
            c = color_core.parse_color(ti.text)
            if c:
                pop.dismiss()
                cb("#%02X%02X%02X" % tuple(c))
            else:
                msg.text = "Not a colour."

        use.bind(on_release=go)
        for w in (msg, ti, use):
            lay.add_widget(w)
        if allow_none:
            none = Button(text="No fill", size_hint_y=None, height=dp(40))
            none.bind(on_release=lambda *a: (pop.dismiss(), cb("")))
            lay.add_widget(none)
        pop.open()

    # ------------------------------------------------------------ files
    def _folder(self):
        return app_data.subdir(FOLDER)

    def _chooser_popup(self, title, save, ext, cb, default_name=""):
        lay = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))
        fc = FileChooserListView(path=self._folder(), filters=[f"*{ext}"] if ext else [])
        lay.add_widget(fc)
        name = TextInput(text=default_name, multiline=False, size_hint_y=None, height=dp(38),
                         font_size=sp(14), hint_text="File name")
        if save:
            lay.add_widget(name)
        msg = _label("", 11, theme.DANGER)
        lay.add_widget(msg)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        ok = Button(text="Save" if save else "Open")
        cancel = Button(text="Cancel")
        row.add_widget(ok)
        row.add_widget(cancel)
        lay.add_widget(row)
        pop = self._popup(title, lay, 0.95, Window.height * 0.9)

        def go(*a):
            if save:
                n = name.text.strip()
                if not n or any(c in n for c in '/\\:*?"<>|'):
                    msg.text = "Type a file name (no slashes)."
                    return
                path = os.path.join(fc.path, n)
            else:
                if not fc.selection:
                    msg.text = "Choose a file."
                    return
                path = fc.selection[0]
            pop.dismiss()
            cb(path)

        fc.bind(selection=lambda w, sel: (sel and not save) and None)
        if save:
            fc.bind(selection=lambda w, sel: sel and setattr(name, "text", os.path.basename(sel[0])))
        ok.bind(on_release=go)
        cancel.bind(on_release=lambda *a: pop.dismiss())
        pop.open()

    def open_dialog(self):
        self._guard(lambda: self._chooser_popup("Open drawing", False, ".srbd", self.load))

    def load(self, path):
        try:
            if os.path.getsize(path) > 60_000_000:
                raise ValueError("The file is too large.")
            with open(path, encoding="utf-8") as f:
                doc = pc.Document.from_json(f.read())
        except (OSError, ValueError, UnicodeDecodeError) as e:
            self._hint(f"Could not open: {e}")
            return
        self.doc = doc
        self.canvas_w.doc = doc
        self.canvas_w.sel = set()
        self.path, self.dirty = path, False
        self.canvas_w.fit()
        self._refresh_all()
        self._hint(f"Opened {os.path.basename(path)} ({len(doc.objects)} objects).")

    def save(self):
        if not self.path:
            self.save_as_dialog()
            return
        self._write(self.path)

    def save_as_dialog(self, then=None):
        self._chooser_popup("Save drawing", True, ".srbd",
                            lambda p: (self._write(p), then and then()),
                            os.path.basename(self.path) if self.path else "drawing.srbd")

    def _write(self, path):
        from core import jsonio
        if not path.lower().endswith(".srbd"):
            path += ".srbd"
        try:
            jsonio.write_json_atomic(path, self.doc.to_dict(), indent=1, ensure_ascii=False)
        except OSError as e:
            self._hint(f"Could not save: {e}")
            return
        self.path, self.dirty = path, False
        self._refresh_all()
        self._hint(f"Saved {path}")

    def export_dialog(self):
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        fmt_sp = Spinner(text="SVG (vector)", values=["SVG (vector)", "PNG (picture)"],
                         size_hint_y=None, height=dp(40))
        scale = Spinner(text="1x", values=["1x", "2x", "3x", "4x"], size_hint_y=None, height=dp(40))
        trans = Button(text="Transparent background: off", size_hint_y=None, height=dp(40))
        state = {"t": False}

        def tog(*a):
            state["t"] = not state["t"]
            trans.text = f"Transparent background: {'on' if state['t'] else 'off'}"

        trans.bind(on_release=tog)
        base = os.path.splitext(os.path.basename(self.path))[0] if self.path else "drawing"
        name = TextInput(text=base, multiline=False, size_hint_y=None, height=dp(40))
        msg = _label(f"Saved in {self._folder()}", 11, theme.MUTED, h=dp(40))
        go = Button(text="Export", size_hint_y=None, height=dp(44))
        for w in (fmt_sp, scale, trans, name, msg, go):
            lay.add_widget(w)
        pop = self._popup("Export", lay, 0.9, dp(400))

        def run(*a):
            n = name.text.strip()
            if not n or any(c in n for c in '/\\:*?"<>|'):
                msg.text = "Type a file name."
                msg.color = theme.DANGER
                return
            svg = fmt_sp.text.startswith("SVG")
            path = os.path.join(self._folder(), n + (".svg" if svg else ".png"))
            try:
                if svg:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(pc.to_svg(self.doc))
                else:
                    pc.render_png(self.doc, int(scale.text[0]), transparent=state["t"]).save(path)
            except ImportError:
                msg.text = "PNG export needs Pillow."
                msg.color = theme.DANGER
                return
            except (OSError, ValueError, MemoryError) as e:
                msg.text = f"Failed: {e}"
                msg.color = theme.DANGER
                return
            pop.dismiss()
            self._hint(f"Exported {path}")

        go.bind(on_release=run)
        pop.open()

    # ------------------------------------------------------------ inspector panel
    def refresh_panel(self):
        self._inputs = {}
        self.panel.clear_widgets()
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == self.tab else OFF
        {"props": self._props, "maths": self._maths, "layers": self._layers,
         "doc": self._docpanel}[self.tab]()

    def _num_input(self, text, commit, multiline=False, h=32):
        ti = TextInput(text=text, multiline=multiline, write_tab=False, font_size=sp(13),
                       size_hint_y=None, height=dp(h), padding=(dp(6), dp(6)))
        ti._orig = text

        def fire(*a):
            if ti.text != ti._orig:
                commit(ti.text)
                ti._orig = ti.text

        if not multiline:
            ti.bind(on_text_validate=fire)
        ti.bind(focus=lambda w, f: (not f) and fire())
        return ti

    def _field_row(self, label, widget):
        row = BoxLayout(size_hint_y=None, height=widget.height, spacing=dp(4))
        lb = _label(label, 11, theme.MUTED, h=widget.height)
        lb.size_hint_x = 0.45
        row.add_widget(lb)
        widget.size_hint_x = 0.55
        row.add_widget(widget)
        self.panel.add_widget(row)

    def _props(self):
        sel = self.canvas_w.selected()
        if len(sel) == 1:
            o = sel[0]
            self.panel.add_widget(_label(f"[b]{o['type'].capitalize()}[/b]", 13))
            self._field_row("Name", self._num_input(o["name"], lambda t: self._set_name(o, t)))
            for key, lab, kind in pc.fields(o):
                self._field_row(lab, self._field_widget(o, key, kind))
            self.panel.add_widget(_label("Numbers accept maths: 2*pi, sqrt(2)*10", 10, theme.MUTED))
        elif len(sel) > 1:
            self.panel.add_widget(_label(f"[b]{len(sel)} objects selected[/b]", 13))
            grid = GridLayout(cols=3, size_hint_y=None, height=dp(80), spacing=dp(3))
            for lab, how in (("Left", "left"), ("Centre", "hcenter"), ("Right", "right"),
                             ("Top", "top"), ("Middle", "vcenter"), ("Bottom", "bottom")):
                b = Button(text=lab, font_size=sp(11))
                b.bind(on_release=lambda *a, h=how: self._edit(
                    lambda: pc.align(self.canvas_w.selected(), h)))
                grid.add_widget(b)
            self.panel.add_widget(_label("Align", 11, theme.MUTED))
            self.panel.add_widget(grid)
        else:
            self.panel.add_widget(_label("[b]Defaults for new objects[/b]", 13))
        self._style_editor(sel)

    def _field_widget(self, o, key, kind):
        if kind == "bool":
            b = Button(text="Yes" if o[key] else "No", size_hint_y=None, height=dp(32), font_size=sp(12))
            b.bind(on_release=lambda *a: self._apply(o, key, not o[key]))
            return b
        if kind == "text":
            ti = self._num_input(o[key], lambda t: self._apply(o, key, t), multiline=True, h=64)
        else:
            ti = self._num_input(pc.fmt(pc.get_field(o, key), 4).replace(",", ""),
                                 lambda t: self._apply(o, key, t))
        self._inputs[key] = ti
        return ti

    def _set_name(self, o, text):
        self._edit(lambda: o.__setitem__("name", text.strip()[:60] or o["name"]))

    def _apply(self, o, key, text):
        """Apply a typed value (maths allowed) to a field; one undo step, refused if invalid."""
        kind = next((k for kk, _l, k in pc.fields(o) if kk == key), None)
        val = text
        if kind in ("num", "int"):
            try:
                val = pc.calc(text)
            except ValueError as e:
                self._hint(f"{key}: {e}")
                self._sync_values(force=True)
                return
        trial = copy.deepcopy(o)
        ok, msg = pc.set_field(trial, key, val)
        if not ok:
            self._hint(msg)
            self._sync_values(force=True)
            return
        self.doc.checkpoint()
        pc.set_field(o, key, val)
        self.dirty = True
        self._refresh_all_keep_inputs()

    def _refresh_all_keep_inputs(self):
        s = self.doc.settings
        self.undo_btn.disabled = not self.doc._undo
        self.redo_btn.disabled = not self.doc._redo
        name = os.path.basename(self.path) if self.path else "Untitled"
        self.title_label.text = f"[b]{name}*[/b]"
        self.canvas_w.redraw()
        if self.tab == "props":
            self._sync_values(force=True)
        else:
            self.refresh_panel()

    def _sync_values(self, force=False):
        sel = self.canvas_w.selected()
        if len(sel) != 1:
            return
        o = sel[0]
        for key, ti in self._inputs.items():
            if ti.focus and not force:
                continue
            try:
                v = o[key] if isinstance(o.get(key), str) else pc.fmt(pc.get_field(o, key), 4).replace(",", "")
            except KeyError:
                continue
            ti.text = ti._orig = v

    def _style_editor(self, sel):
        targets = sel or None
        st = sel[0]["style"] if sel else self.canvas_w.style
        self.panel.add_widget(_label("[b]Style[/b]", 12))

        def set_style(**kw):
            if targets:
                self._edit(lambda: [o["style"].update(kw) for o in targets])
            else:
                self.canvas_w.style.update(kw)
                self.refresh_panel()

        sb = Button(text=st["stroke"] or "none", background_normal="",
                    background_color=_rgb(st["stroke"] or "#808080"), size_hint_y=None, height=dp(32),
                    font_size=sp(11), color=(1, 1, 1, 1) if sum(_rgb(st["stroke"] or "#808080")[:3]) < 1.6 else (0, 0, 0, 1))
        sb.bind(on_release=lambda *a: self.pick_color("Stroke colour", False,
                                                      lambda c: set_style(stroke=c)))
        self._field_row("Stroke", sb)
        fb = Button(text=st["fill"] or "none", background_normal="",
                    background_color=_rgb(st["fill"] or "#404040"), size_hint_y=None, height=dp(32),
                    font_size=sp(11), color=(1, 1, 1, 1) if sum(_rgb(st["fill"] or "#404040")[:3]) < 1.6 else (0, 0, 0, 1))
        fb.bind(on_release=lambda *a: self.pick_color("Fill colour", True,
                                                      lambda c: set_style(fill=c)))
        self._field_row("Fill", fb)

        def num(key, lo, hi):
            def commit(t):
                try:
                    v = pc.clamp(pc.calc(t), lo, hi)
                except ValueError as e:
                    self._hint(str(e))
                    return
                set_style(**{key: v})
            return commit

        self._field_row("Line width", self._num_input(pc.fmt(st["width"]), num("width", 0.1, 200)))
        dash = Spinner(text=st["dash"], values=list(pc.DASHES), size_hint_y=None, height=dp(32),
                       font_size=sp(12))
        dash.bind(text=lambda w, t: t != st["dash"] and set_style(dash=t))
        self._field_row("Line style", dash)
        self._field_row("Opacity (0-1)", self._num_input(pc.fmt(st["opacity"]), num("opacity", 0, 1)))

    def _maths(self):
        sel = self.canvas_w.selected()
        u = self.doc.settings["units"]
        if len(sel) == 1:
            o = sel[0]
            self.panel.add_widget(_label(f"[b]{o['name']}[/b]", 13))
            rows = pc.math_rows(o, u)
            if not rows:
                self.panel.add_widget(_wrap_label("No measurements for this object."))
            for label, formula, subst, result in rows:
                self.panel.add_widget(_label(f"[b]{label}[/b]", 12, h=dp(20)))
                if formula:
                    self.panel.add_widget(_wrap_label(formula, 11))
                if subst:
                    self.panel.add_widget(_wrap_label("= " + subst, 11))
                ex = pc.exact(o, label)
                txt = f"[b]= {result}[/b]" + (f"\n[color=9fc7ff]exact: {ex}[/color]" if ex else "")
                self.panel.add_widget(_wrap_label(txt, 13, (1, 1, 1, 1)))
        elif len(sel) > 1:
            b = [pc.bbox(o) for o in sel]
            x0, y0 = min(v[0] for v in b), min(v[1] for v in b)
            x1, y1 = max(v[2] for v in b), max(v[3] for v in b)
            self.panel.add_widget(_label(f"[b]{len(sel)} objects[/b]", 13))
            for lab, val in (("Group width", x1 - x0), ("Group height", y1 - y0)):
                self.panel.add_widget(_wrap_label(f"{lab}: [b]{pc.fmt(val)}[/b]", 12, (1, 1, 1, 1)))
        else:
            s = self.doc.settings
            self.panel.add_widget(_label("[b]Page[/b]", 13))
            self.panel.add_widget(_wrap_label(
                f"Area = w × h\n= {pc.fmt(s['width'])} × {pc.fmt(s['height'])}\n"
                f"[b]= {pc.fmt(s['width'] * s['height'])}[/b]", 12, (1, 1, 1, 1)))
            self.panel.add_widget(_wrap_label("Select an object to see its formulas.", 11))

    def _layers(self):
        if not self.doc.objects:
            self.panel.add_widget(_wrap_label("No objects yet."))
        for o in reversed(self.doc.objects):
            row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(2))
            sel = o["id"] in self.canvas_w.sel
            name = Button(text=o["name"], font_size=sp(11), halign="left",
                          background_color=theme.ACCENT if sel else OFF)
            name.bind(on_release=lambda b, oid=o["id"]: self._layer_click(b, oid))
            eye = Button(text="Hide" if o["visible"] else "Show", size_hint_x=None, width=dp(44),
                         font_size=sp(10))
            eye.bind(on_release=lambda *a, ob=o: self._edit(
                lambda: ob.__setitem__("visible", not ob["visible"])))
            lock = Button(text="Unlock" if o["locked"] else "Lock", size_hint_x=None, width=dp(50),
                          font_size=sp(10))
            lock.bind(on_release=lambda *a, ob=o: self._edit(
                lambda: ob.__setitem__("locked", not ob["locked"])))
            up = Button(text="^", size_hint_x=None, width=dp(26), font_size=sp(11))
            up.bind(on_release=lambda *a, oid=o["id"]: self._edit(lambda: self.doc.move_order(oid, 1)))
            dn = Button(text="v", size_hint_x=None, width=dp(26), font_size=sp(11))
            dn.bind(on_release=lambda *a, oid=o["id"]: self._edit(lambda: self.doc.move_order(oid, -1)))
            for w in (name, eye, lock, up, dn):
                row.add_widget(w)
            self.panel.add_widget(row)
        self.panel.add_widget(_wrap_label("Tap a name to select; tap it again to rename. "
                                          "^ / v change the stacking order.", 10))

    def _layer_click(self, btn, oid):
        o = self.doc.get(oid)
        if o is None:
            return
        if o["locked"] or not o["visible"] or oid in self.canvas_w.sel:
            self._rename(o)
            return
        self.canvas_w.set_sel([oid])

    def _rename(self, o):
        ti = TextInput(text=o["name"], multiline=False, size_hint_y=None, height=dp(40))
        ok = Button(text="Rename", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        lay.add_widget(ti)
        lay.add_widget(ok)
        pop = self._popup("Rename layer", lay, 0.9, dp(190))
        ok.bind(on_release=lambda *a: (pop.dismiss(), self._set_name(o, ti.text)))
        ti.bind(on_text_validate=lambda *a: (pop.dismiss(), self._set_name(o, ti.text)))
        pop.open()
        Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0.2)

    def _docpanel(self):
        s = self.doc.settings

        def numset(key, lo, hi, as_int=False):
            def commit(t):
                try:
                    v = pc.calc(t)
                except ValueError as e:
                    self._hint(f"{key}: {e}")
                    return
                if v < lo or v > hi:
                    self._hint(f"{key}: use a value from {lo:g} to {hi:g}.")
                    return
                self._set_setting(key, int(round(v)) if as_int else v)
                self.refresh_panel()
            return commit

        self.panel.add_widget(_label("[b]Page[/b]", 13))
        self._field_row("Width", self._num_input(pc.fmt(s["width"]).replace(",", ""), numset("width", 1, 100000)))
        self._field_row("Height", self._num_input(pc.fmt(s["height"]).replace(",", ""), numset("height", 1, 100000)))
        units = Spinner(text=s["units"], values=list(pc.UNITS), size_hint_y=None, height=dp(32), font_size=sp(12))
        units.bind(text=lambda w, t: t != s["units"] and self._set_setting("units", t))
        self._field_row("Units", units)
        bg = Button(text=s["background"], background_normal="", background_color=_rgb(s["background"]),
                    color=(0, 0, 0, 1) if sum(_rgb(s["background"])[:3]) > 1.5 else (1, 1, 1, 1),
                    size_hint_y=None, height=dp(32), font_size=sp(11))
        bg.bind(on_release=lambda *a: self.pick_color("Background", False,
                                                      lambda c: self._set_setting("background", c)))
        self._field_row("Background", bg)
        self.panel.add_widget(_label("[b]Grid and snapping[/b]", 13))
        self._field_row("Grid spacing", self._num_input(pc.fmt(s["grid_spacing"]).replace(",", ""),
                                                        numset("grid_spacing", 0.001, 100000)))
        self._field_row("Major every", self._num_input(str(s["grid_major"]), numset("grid_major", 1, 100, True)))
        gt = Spinner(text=s["grid_type"], values=list(pc.GRIDS), size_hint_y=None, height=dp(32), font_size=sp(12))
        gt.bind(text=lambda w, t: t != s["grid_type"] and self._set_setting("grid_type", t))
        self._field_row("Grid style", gt)
        self._field_row("Angle step (deg)", self._num_input(str(s["angle_step"]), numset("angle_step", 0, 90, True)))
        for key, lab in (("grid", "Show grid"), ("snap_grid", "Snap to grid"),
                         ("snap_points", "Snap to points"), ("snap_align", "Alignment guides")):
            b = Button(text="On" if s[key] else "Off", size_hint_y=None, height=dp(32), font_size=sp(12),
                       background_color=theme.ACCENT if s[key] else OFF)
            b.bind(on_release=lambda *a, k=key: (self._set_setting(k, not self.doc.settings[k]),
                                                 self.refresh_panel()))
            self._field_row(lab, b)
        self.panel.add_widget(_wrap_label(
            "Strict: snaps to the grid and to points, and locks angles. Assisted: snaps but does "
            "not lock angles unless Shift is held. Free: no snapping at all.", 10))
