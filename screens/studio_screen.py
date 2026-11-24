# screens/studio_screen.py - Srboli Studio: one infinite workspace of independent objects
# (text, shapes, frames, groups). The document and all editing rules live in core/studio_core.py;
# this file draws the canvas, turns touches into edits and builds the toolbar, sidebar and panels.
import copy
import io
import math
import os

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.text.markup import MarkupLabel
from kivy.core.window import Window
from kivy.graphics import (Color, Ellipse, Line, PopMatrix, PushMatrix, Rectangle, Rotate,
                           RoundedRectangle, Triangle)
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.stencilview import StencilView
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup

import app_data
from core import drawing_core
from core import studio_core as sc
from core import studio_data as sd
from core import studio_export as se
from core import theme

FOLDER = "studio"
EXT = ".srbcanvas"
TOOLS = [("select", "Select"), ("pan", "Pan"), ("text", "Text"), ("rect", "Rectangle"),
         ("rounded", "Rounded"), ("ellipse", "Ellipse"), ("line", "Line"), ("arrow", "Arrow"),
         ("frame", "Frame"), ("table", "Table"), ("chart", "Chart"), ("image", "Image")]
SHAPE_TOOLS = ("rect", "rounded", "ellipse", "line", "arrow")
HINTS = {
    "select": "Click an object to select it. Drag to move, drag a handle to resize or turn. "
              "Drag on empty space to select several (Shift adds). Double-click text to edit.",
    "pan": "Drag to pan. The mouse wheel zooms; two fingers pan and pinch.",
    "text": "Click to place a text box (or drag its width).",
    "rect": "Drag to draw a rectangle, or click for a default one.",
    "rounded": "Drag to draw a rounded rectangle.",
    "ellipse": "Drag to draw an ellipse.",
    "line": "Drag from the start to the end. Shift snaps the angle.",
    "arrow": "Drag from the tail to the head. Shift snaps the angle.",
    "table": "Drag to draw a table (or click for a default one). Double-click it to edit cells; "
             "text starting with = is a formula, e.g. =SUM(B2:B4).",
    "chart": "Drag to draw a chart. With a table selected the chart links to it and updates "
             "whenever the table changes.",
    "image": "Choose a PNG, JPEG or GIF picture to place in the middle of the view.",
    "frame": "Drag to draw a frame (a page or slide). Objects dropped inside move with it.",
}
HANDLE_R = 11.0          # screen px


def _label(text, size=12, color=None, h=None, **kw):
    lb = Label(text=text, font_size=sp(size), color=color or (1, 1, 1, 1), halign="left",
               valign="middle", size_hint_y=None, height=h or dp(24), markup=True, **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lb


def _rgb(hexs, a=1.0):
    h = (hexs or "#000000").lstrip("#")
    if len(h) != 6:
        h = "000000"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


def markup_for(o, zoom):
    """Kivy markup for a text object at a zoom level (headings, lists, quotes, code)."""
    base = o["size"] * zoom
    out = []
    for kind, txt in sc.parse_blocks(o["text"], o["mode"]):
        px = max(1, int(round(base * sc.BLOCK_SCALE[kind])))
        if o["mode"] == "markdown" and kind != "code":
            body = sc.inline_markup(txt, escape_markup)
        else:
            body = escape_markup(txt)
        if kind.startswith("h"):
            body = f"[b]{body}[/b]"
        elif kind == "quote":
            body = f"[i]| {body}[/i]"
        out.append(f"[size={px}]{body or ' '}[/size]")
    return "\n".join(out)


def _core_label(o, zoom):
    inner = max(1.0, (o["w"] - 2 * o["pad"]) * zoom)
    return MarkupLabel(text=markup_for(o, zoom), color=_rgb(o["color"]),
                     font_size=max(1, int(round(o["size"] * zoom))), halign=o["align"],
                     bold=o["bold"], italic=o["italic"], text_size=(inner, None))


def measure_height(o):
    """Height (world units) a text object needs for its content at its current width."""
    lb = _core_label(o, 1.0)
    lb.refresh()
    tex = lb.texture
    return (tex.height if tex else o["size"]) + 2 * o["pad"]


def refit_text(o):
    if o["type"] == "text" and o["autofit"]:
        o["h"] = max(sc.MIN_SIZE, measure_height(o))


def handles_for(o_or_box, line=None):
    """Handle list [(key, wx, wy)] for a box dict (x, y, w, h, rot) or a line object."""
    if line is not None:
        a, b = sc.line_ends(line)
        return [(("end", 0), a[0], a[1]), (("end", 1), b[0], b[1])]
    b = o_or_box
    cx, cy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    out = []
    for hx in (-1, 0, 1):
        for hy in (-1, 0, 1):
            if hx == 0 and hy == 0:
                continue
            px, py = sc.rotate_pt(cx + hx * b["w"] / 2, cy + hy * b["h"] / 2, cx, cy, b["rot"])
            out.append((("r", hx, hy), px, py))
    return out


# ====================================================================== the canvas
class StudioCanvas(StencilView):
    def __init__(self, doc, **kw):
        super().__init__(**kw)
        self.doc = doc
        self.view = sc.View()
        self.tool = "select"
        self.sel = set()
        self.shift = False
        self.on_change = lambda: None
        self.on_select = lambda: None
        self.on_view = lambda: None
        self.on_hint = lambda t: None
        self.on_live = lambda: None
        self.on_tool = lambda t: None
        self.on_edit_text = lambda o: None
        self.on_edit_table = lambda o: None
        self._touches = {}
        self._grids = {}
        self._imgs = {}
        self.only = None                      # ids to draw (slide mode); None = the whole workspace
        self._pinch = None
        self._mode = None
        self._start = self._cur = None
        self._origs = {}
        self._moved = False
        self._handle = None
        self._marquee = None
        self._guides = []
        self._sbox = None
        self._fitted = False
        self._tex = {}
        self.bind(pos=self.redraw, size=self._resized)

    # ----- helpers
    def _resized(self, *a):
        self.view.h = self.height
        if not self._fitted and self.width > 50 and self.height > 50:
            self._fitted = True
            self.fit()
        self.redraw()

    def _loc(self, pos):
        return pos[0] - self.x, pos[1] - self.y

    def W(self, pos):
        self.view.h = self.height
        return self.view.to_world(*self._loc(pos))

    def S(self, x, y):
        sx, sy = self.view.to_screen(x, y)
        return self.x + sx, self.y + sy

    def fit(self):
        self.view.fit(self.doc.content_bounds(), self.width, self.height)
        self.redraw()
        self.on_view()

    def zoom_by(self, f):
        self.view.h = self.height
        self.view.zoom_at(self.width / 2, self.height / 2, f)
        self.redraw()
        self.on_view()

    def selected(self):
        return [o for o in self.doc.objects if o["id"] in self.sel]

    def set_sel(self, ids):
        self.sel = {i for i in ids if self.doc.get(i)}
        self.on_select()
        self.redraw()

    def prune_sel(self):
        alive = {o["id"] for o in self.doc.objects}
        if not self.sel <= alive:
            self.sel &= alive
            self.on_select()

    def _snap_pt(self, x, y):
        s = self.doc.settings
        if s["snap_grid"]:
            return sc.snap_grid(x, s["grid_size"]), sc.snap_grid(y, s["grid_size"])
        return x, y

    def set_tool(self, tool):
        self.tool = tool
        self._mode = None
        self.redraw()

    # ----- handles
    def _single(self):
        r = sc.roots(self.doc, self.sel)
        if len(r) == 1 and not self.doc.effective_locked(r[0]):
            return r[0]
        return None

    def _handles(self):
        o = self._single()
        if o is None:
            return None, []
        if o["type"] == "shape" and o["shape"] in ("line", "arrow"):
            return o, handles_for(None, line=o)
        x, y, w, h, rot = sc.selection_box(self.doc, [o])
        box = {"x": x, "y": y, "w": w, "h": h, "rot": rot}
        hs = handles_for(box)
        cx, cy = x + w / 2, y + h / 2
        rx, ry = sc.rotate_pt(cx, cy - h / 2 - 30 / self.view.zoom, cx, cy, rot)
        hs.append((("rot",), rx, ry))
        return o, hs

    # ----- touches
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        btn = getattr(touch, "button", "left")
        if btn in ("scrollup", "scrolldown"):
            self.view.h = self.height
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
        x, y = self.W(touch.pos)
        if self.tool == "select":
            self._select_down(touch, x, y)
        else:
            self._start = self._cur = self._snap_pt(x, y)
            self._mode = "create"
        self.redraw()
        return True

    def _select_down(self, touch, x, y):
        tol = 6 / self.view.zoom
        o, hs = self._handles()
        if o is not None:
            lx, ly = self._loc(touch.pos)
            for key, hx, hy in hs:
                sx, sy = self.view.to_screen(hx, hy)
                if math.hypot(sx - lx, sy - ly) <= dp(HANDLE_R):
                    self._mode, self._handle, self._moved = "handle", key, False
                    self._begin_origs([o])
                    return
        hit = self.doc.hit_test(x, y, tol)
        if hit is None:
            # a click on a selected child (chosen from Layers) still moves it
            for s in self.selected():
                if not self.doc.effective_locked(s) and sc.hit(s, x, y, tol):
                    hit = s
                    break
        if hit is not None:
            if touch.is_double_tap and hit["type"] in ("text", "table"):
                self.set_sel([hit["id"]])
                self._mode = "done"
                (self.on_edit_text if hit["type"] == "text" else self.on_edit_table)(hit)
                return
            if self.shift:
                self.sel ^= {hit["id"]}
            elif hit["id"] not in self.sel:
                self.sel = {hit["id"]}
            self.on_select()
            if hit["id"] in self.sel:
                self._mode, self._moved = "move", False
                self._start = (x, y)
                self._begin_origs(sc.roots(self.doc, self.sel))
            else:
                self._mode = "done"
        else:
            if not self.shift:
                self.sel = set()
                self.on_select()
            self._mode = "marquee"
            self._marquee = ((x, y), (x, y))

    def _begin_origs(self, objs):
        self._origs = {}
        for o in objs:
            for t in [o] + self.doc.descendants(o["id"]):
                self._origs[t["id"]] = copy.deepcopy(t)
        bs = [sc.bbox(o) for o in objs if o["type"] != "group"] or [sc.bbox(o) for o in objs]
        bs += [sc.bbox(self._origs[t["id"]]) for o in objs for t in self.doc.descendants(o["id"])
               if t["type"] != "group"]
        self._sbox = (min(b[0] for b in bs), min(b[1] for b in bs),
                      max(b[2] for b in bs), max(b[3] for b in bs))

    def _restore(self):
        for i, orig in self._origs.items():
            o = self.doc.get(i)
            if o is not None:
                o.clear()
                o.update(copy.deepcopy(orig))

    def on_touch_move(self, touch):
        if touch.uid not in self._touches:
            return super().on_touch_move(touch)
        if self._mode == "pinch":
            two = list(self._touches.values())
            if len(two) >= 2:
                a, b = two[0], two[1]
                mid = self._loc(((a.x + b.x) / 2, (a.y + b.y) / 2))
                d = math.hypot(a.x - b.x, a.y - b.y)
                self.view.h = self.height
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
        if self._mode in (None, "done"):
            return True
        x, y = self.W(touch.pos)
        if self._mode == "create":
            self._cur = self._snap_pt(x, y)
            if self.tool in ("line", "arrow") and self.shift:
                self._cur = self._angle_lock(self._start, self._cur)
        elif self._mode == "move":
            self._move(x, y)
        elif self._mode == "handle":
            self._drag_handle(x, y)
        elif self._mode == "marquee":
            self._marquee = (self._marquee[0], (x, y))
        self.redraw()
        return True

    @staticmethod
    def _angle_lock(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        r = math.hypot(dx, dy)
        ang = round(math.degrees(math.atan2(dy, dx)) / 15) * 15
        return a[0] + r * math.cos(math.radians(ang)), a[1] + r * math.sin(math.radians(ang))

    def _checkpoint_once(self):
        if not self._moved:
            self.doc.checkpoint()
            self._moved = True

    def _move(self, x, y):
        dx, dy = x - self._start[0], y - self._start[1]
        if not self._moved and math.hypot(dx, dy) * self.view.zoom < 3:
            return
        s = self.doc.settings
        self._guides = []
        b = self._sbox
        if s["snap_grid"]:
            dx = sc.snap_grid(b[0] + dx, s["grid_size"]) - b[0]
            dy = sc.snap_grid(b[1] + dy, s["grid_size"]) - b[1]
        elif s["snap_objects"]:
            others = [sc.bbox(o) for o in self.doc.objects
                      if o["id"] not in self._origs and o["type"] != "group"
                      and self.doc.effective_visible(o)][:400]
            sx, sy, self._guides = sc.snap_box(
                others, (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy), 6 / self.view.zoom)
            dx, dy = dx + sx, dy + sy
        self._checkpoint_once()
        for i, orig in self._origs.items():
            o = self.doc.get(i)
            if o is not None:
                o["x"], o["y"] = orig["x"] + dx, orig["y"] + dy
        sc.refresh_groups(self.doc)
        self.on_live()

    def _drag_handle(self, x, y):
        o = self._single_by_origin()
        if o is None:
            return
        self._checkpoint_once()
        self._restore()
        key = self._handle
        x, y = self._snap_pt(x, y)
        if key[0] == "end":
            if self.shift:
                a, b = sc.line_ends(o)
                fixed = b if key[1] == 0 else a
                x, y = self._angle_lock(fixed, (x, y))
            sc.set_line_end(o, key[1], x, y)
        elif key[0] == "rot":
            cx, cy = sc.center(o)
            ang = math.degrees(math.atan2(y - cy, x - cx)) + 90
            snapped = round(ang / 15) * 15
            if self.shift or abs(ang - snapped) < 3:
                ang = snapped
            ang %= 360
            if o["type"] == "group":
                sc.rotate_tree(self.doc, o, cx, cy, ang)
                sc.recalc_group(self.doc, o)
            else:
                o["rot"] = ang
        else:
            _, hx, hy = key
            if o["type"] == "group":
                ax = o["x"] + (o["w"] * (0 if hx > 0 else 1) if hx else o["w"] / 2)
                ay = o["y"] + (o["h"] * (0 if hy > 0 else 1) if hy else o["h"] / 2)
                h0x = o["x"] + o["w"] * (hx + 1) / 2
                h0y = o["y"] + o["h"] * (hy + 1) / 2
                sx = (x - ax) / (h0x - ax) if hx and abs(h0x - ax) > 1e-9 else 1.0
                sy = (y - ay) / (h0y - ay) if hy and abs(h0y - ay) > 1e-9 else 1.0
                sx = sx if abs(sx) > 0.05 else 0.05
                sy = sy if abs(sy) > 0.05 else 0.05
                sc.scale_tree(self.doc, o, ax, ay, sx, sy)
                sc.recalc_group(self.doc, o)
            else:
                sc.resize_box(o, (hx, hy), x, y, keep_ratio=self.shift)
                if o["type"] == "text":
                    if hy:
                        o["autofit"] = False
                    else:
                        refit_text(o)
        sc.refresh_groups(self.doc)
        self.on_live()

    def _single_by_origin(self):
        ids = [i for i in self._origs if self.doc.get(i) and self.doc.get(i)["id"] in self.sel]
        return self.doc.get(ids[0]) if ids else None

    def on_touch_up(self, touch):
        if touch.uid not in self._touches:
            return super().on_touch_up(touch)
        touch.ungrab(self)
        self._touches.pop(touch.uid, None)
        if self._mode == "pinch":
            if not self._touches:
                self._mode = None
            self._pinch = None
            return True
        mode = self._mode
        self._mode = None
        if mode == "create":
            self._finish_create()
        elif mode in ("move", "handle"):
            if self._moved:
                if mode == "move":
                    for o in sc.roots(self.doc, self.sel):
                        sc.assign_parent(self.doc, o)
                if mode == "handle":
                    for o in self.selected():
                        refit_text(o)
                sc.refresh_groups(self.doc)
                self.on_change()
        elif mode == "marquee":
            self._finish_marquee()
        self._guides = []
        self._marquee = None
        self._origs = {}
        self.redraw()
        return True

    def _cancel(self):
        if self._moved and self._origs:
            self._restore()
        self._mode = None
        self._origs = {}
        self._guides = []
        self._marquee = None

    def _finish_marquee(self):
        (x0, y0), (x1, y1) = self._marquee
        if math.hypot(x1 - x0, y1 - y0) * self.view.zoom < 4:
            return
        lo, hi = (min(x0, x1), min(y0, y1)), (max(x0, x1), max(y0, y1))
        found = set(self.sel) if self.shift else set()
        for o in self.doc.objects:
            if not self.doc.effective_visible(o) or self.doc.effective_locked(o):
                continue
            top = self.doc.top_level(o)
            if top is not o:
                continue
            b = sc.bbox(o)
            if b[0] >= lo[0] and b[1] >= lo[1] and b[2] <= hi[0] and b[3] <= hi[1]:
                found.add(o["id"])
        self.set_sel(found)

    def _finish_create(self):
        a, b = self._start, self._cur
        if a is None or b is None:
            return
        t = self.tool
        click = math.hypot(b[0] - a[0], b[1] - a[1]) * self.view.zoom < 6
        self.doc.checkpoint()
        if t == "frame":
            o = sc.make("frame", x=a[0], y=a[1])
            if not click:
                o.update(x=min(a[0], b[0]), y=min(a[1], b[1]), w=max(abs(b[0] - a[0]), 40.0),
                         h=max(abs(b[1] - a[1]), 40.0), preset="Custom")
        elif t == "text":
            o = sc.make("text", x=a[0], y=a[1])
            if not click:
                o["x"], o["w"] = min(a[0], b[0]), max(abs(b[0] - a[0]), 40.0)
            o["h"] = measure_height(o)
        elif t in ("table", "chart"):
            o = sc.make(t, x=a[0], y=a[1])
            if not click:
                o.update(x=min(a[0], b[0]), y=min(a[1], b[1]), w=max(abs(b[0] - a[0]), 60.0),
                         h=max(abs(b[1] - a[1]), 40.0))
            tabs = [x for x in self.selected() if x["type"] == "table"]
            if t == "chart" and len(tabs) == 1:
                o["source"] = tabs[0]["id"]
                o["data"] = sd.chart_data(o, tabs[0])
        elif t in ("line", "arrow"):
            o = sc.make("shape", shape=t, x=a[0], y=a[1], w=160.0, h=0.0)
            if not click:
                o.update(x=min(a[0], b[0]), y=min(a[1], b[1]), w=abs(b[0] - a[0]),
                         h=abs(b[1] - a[1]), fx=a[0] > b[0], fy=a[1] > b[1])
        else:
            o = sc.make("shape", shape=t)
            if click:
                o["x"], o["y"] = a[0] - o["w"] / 2, a[1] - o["h"] / 2
            else:
                o.update(x=min(a[0], b[0]), y=min(a[1], b[1]), w=max(abs(b[0] - a[0]), sc.MIN_SIZE),
                         h=max(abs(b[1] - a[1]), sc.MIN_SIZE))
        self.doc.add(o)
        sc.assign_parent(self.doc, o)
        self.sel = {o["id"]}
        self.tool = "select"
        self.on_tool("select")
        self.on_select()
        self.on_change()
        if t == "text":
            self.on_edit_text(o)

    # ----- drawing
    def redraw(self, *a):
        self.view.h = self.height
        self.canvas.clear()
        z = self.view.zoom
        with self.canvas:
            Color(*(_rgb(self.doc.settings["background"]) if self.only is None else (0, 0, 0, 1)))
            Rectangle(pos=self.pos, size=self.size)
            if self.doc.settings["grid"] and self.only is None:
                self._grid()
            for o in self.doc.draw_order():
                if self.only is None or o["id"] in self.only:
                    self._draw(o)
            if self.only is None:
                self._draw_selection()
            for kind, v in self._guides:
                Color(1, 0.35, 0.65, 0.9)
                if kind == "v":
                    sx = self.S(v, 0)[0]
                    Line(points=[sx, self.y, sx, self.top], width=1)
                else:
                    sy = self.S(0, v)[1]
                    Line(points=[self.x, sy, self.right, sy], width=1)
            if self._mode == "create" and self._start and self._cur:
                self._draw_preview()
            if self._mode == "marquee" and self._marquee:
                (x0, y0), (x1, y1) = self._marquee
                ax, ay = self.S(min(x0, x1), max(y0, y1))
                Color(0.3, 0.6, 1, 0.15)
                Rectangle(pos=(ax, ay), size=(abs(x1 - x0) * z, abs(y1 - y0) * z))
                Color(0.3, 0.6, 1, 0.9)
                Line(rectangle=(ax, ay, abs(x1 - x0) * z, abs(y1 - y0) * z), width=1)

    def _grid(self):
        z = self.view.zoom
        g = self.doc.settings["grid_size"]
        while g * z < 14:
            g *= 2
        x0, y0 = self.view.to_world(0, self.height)
        x1, y1 = self.view.to_world(self.width, 0)
        Color(1, 1, 1, 0.07)
        n = 0
        x = math.floor(x0 / g) * g
        while x <= x1 and n < 300:
            sx = self.S(x, 0)[0]
            Line(points=[sx, self.y, sx, self.top], width=1)
            x += g
            n += 1
        y = math.floor(y0 / g) * g
        n = 0
        while y <= y1 and n < 300:
            sy = self.S(0, y)[1]
            Line(points=[self.x, sy, self.right, sy], width=1)
            y += g
            n += 1

    def _text_texture(self, o):
        z = self.view.zoom
        key = (o["id"], o["text"], o["size"], o["bold"], o["italic"], o["align"], o["mode"],
               o["color"], round(o["w"], 1), round(z, 3), o["pad"])
        tex = self._tex.get(key)
        if tex is None:
            if len(self._tex) > 200:
                self._tex.clear()
            lb = _core_label(o, z)
            lb.refresh()
            tex = lb.texture
            self._tex[key] = tex
        return tex

    def _begin_rot(self, o):
        if not o["rot"]:
            return False
        PushMatrix()
        Rotate(angle=-o["rot"], origin=self.S(*sc.center(o)))
        return True

    def _draw(self, o):
        z = self.view.zoom
        a = o["opacity"]
        t = o["type"]
        if t == "shape" and o["shape"] in ("line", "arrow"):
            p, q = sc.line_ends(o)
            p, q = self.S(*p), self.S(*q)
            Color(*_rgb(o["stroke"], a))
            wd = max(1.0, o["width"] * z)
            Line(points=[p[0], p[1], q[0], q[1]], width=wd)
            if o["shape"] == "arrow":
                L = math.hypot(q[0] - p[0], q[1] - p[1])
                if L > 1:
                    ux, uy = (q[0] - p[0]) / L, (q[1] - p[1]) / L
                    hl = min(max(12.0 * z, wd * 3), L)
                    hw = hl * 0.45
                    bx, by = q[0] - ux * hl, q[1] - uy * hl
                    Triangle(points=[q[0], q[1], bx - uy * hw, by + ux * hw,
                                     bx + uy * hw, by - ux * hw])
            return
        sx, sy = self.S(o["x"], o["y"] + o["h"])
        w, h = o["w"] * z, o["h"] * z
        if sx > self.right + w + 4000 or sx < self.x - w - 4000:
            return
        rot = self._begin_rot(o)
        if t == "frame":
            Color(*_rgb(o["bg"], a))
            Rectangle(pos=(sx, sy), size=(w, h))
            if self.only is None:                 # no border or title while presenting / exporting
                Color(*_rgb(o["border"], 1))
                Line(rectangle=(sx, sy, w, h), width=1.2)
                tex = self._title_tex(o["name"])
                Color(*_rgb(o["border"], 1))
                Rectangle(texture=tex, pos=(sx, sy + h + 2), size=tex.size)
        elif t == "text":
            if o["fill"]:
                Color(*_rgb(o["fill"], a))
                Rectangle(pos=(sx, sy), size=(w, h))
            if o["size"] * z >= 2.5:
                tex = self._text_texture(o)
                if tex:
                    Color(1, 1, 1, a)
                    Rectangle(texture=tex, pos=(sx + o["pad"] * z, sy + h - o["pad"] * z - tex.height),
                              size=tex.size)
            else:
                Color(*_rgb(o["color"], a * 0.6))
                Rectangle(pos=(sx + o["pad"] * z, sy + h / 2), size=(max(w - 2 * o["pad"] * z, 1), 1.5))
        elif t == "table":
            self._draw_table(o, sx, sy, w, h, a)
        elif t == "chart":
            self._draw_chart(o, sx, sy, w, h, a)
        elif t == "image":
            self._draw_image(o, sx, sy, w, h, a)
        elif t == "shape":
            sh = o["shape"]
            wd = max(0.0, o["width"] * z)
            wd = max(1.0, wd) if o["width"] > 0 else 0
            if sh == "ellipse":
                if o["fill"]:
                    Color(*_rgb(o["fill"], a))
                    Ellipse(pos=(sx, sy), size=(w, h))
                if wd:
                    Color(*_rgb(o["stroke"], a))
                    Line(ellipse=(sx, sy, w, h), width=wd)
            elif sh == "rounded":
                r = min(o["radius"] * z, w / 2, h / 2)
                if o["fill"]:
                    Color(*_rgb(o["fill"], a))
                    RoundedRectangle(pos=(sx, sy), size=(w, h), radius=[r])
                if wd:
                    Color(*_rgb(o["stroke"], a))
                    Line(rounded_rectangle=(sx, sy, w, h, r), width=wd)
            else:
                if o["fill"]:
                    Color(*_rgb(o["fill"], a))
                    Rectangle(pos=(sx, sy), size=(w, h))
                if wd:
                    Color(*_rgb(o["stroke"], a))
                    Line(rectangle=(sx, sy, w, h), width=wd)
        if rot:
            PopMatrix()

    def _title_tex(self, text):
        key = ("title", text)
        tex = self._tex.get(key)
        if tex is None:
            lb = CoreLabel(text=text or "Frame", font_size=int(sp(12)))
            lb.refresh()
            tex = lb.texture
            self._tex[key] = tex
        return tex

    def _draw_selection(self):
        objs = self.selected()
        if not objs:
            return
        for o in objs:
            self._outline(o, (0.3, 0.6, 1, 0.55), 1)
        roots = sc.roots(self.doc, self.sel)
        if len(roots) > 1:
            x, y, w, h, rot = sc.selection_box(self.doc, roots)
            self._outline({"x": x, "y": y, "w": w, "h": h, "rot": rot}, (0.3, 0.6, 1, 0.9), 1.4)
            return
        o, hs = self._handles()
        if o is None:
            return
        x, y, w, h, rot = sc.selection_box(self.doc, [o])
        if not (o["type"] == "shape" and o["shape"] in ("line", "arrow")):
            self._outline({"x": x, "y": y, "w": w, "h": h, "rot": rot}, (0.3, 0.6, 1, 1), 1.5)
        r = dp(5)
        for key, hx, hy in hs:
            px, py = self.S(hx, hy)
            if key[0] == "rot":
                top = self.S(*sc.rotate_pt(x + w / 2, y, x + w / 2, y + h / 2, rot))
                Color(0.3, 0.6, 1, 0.8)
                Line(points=[top[0], top[1], px, py], width=1)
                Color(1, 1, 1, 1)
                Ellipse(pos=(px - r, py - r), size=(2 * r, 2 * r))
                Color(0.3, 0.6, 1, 1)
                Line(ellipse=(px - r, py - r, 2 * r, 2 * r), width=1.2)
            else:
                Color(1, 1, 1, 1)
                Rectangle(pos=(px - r, py - r), size=(2 * r, 2 * r))
                Color(0.3, 0.6, 1, 1)
                Line(rectangle=(px - r, py - r, 2 * r, 2 * r), width=1.2)

    def _outline(self, o, color, width):
        if o.get("type") == "shape" and o.get("shape") in ("line", "arrow"):
            p, q = sc.line_ends(o)
            p, q = self.S(*p), self.S(*q)
            Color(*color)
            Line(points=[p[0], p[1], q[0], q[1]], width=width)
            return
        pts = []
        for px, py in sc.corners(o):
            pts += list(self.S(px, py))
        Color(*color)
        Line(points=pts, width=width, close=True)

    def _draw_preview(self):
        a, b = self._start, self._cur
        Color(0.3, 0.6, 1, 0.9)
        if self.tool in ("line", "arrow"):
            p, q = self.S(*a), self.S(*b)
            Line(points=[p[0], p[1], q[0], q[1]], width=1.5)
            return
        x0, y0 = self.S(min(a[0], b[0]), max(a[1], b[1]))
        w, h = abs(b[0] - a[0]) * self.view.zoom, abs(b[1] - a[1]) * self.view.zoom
        if self.tool == "ellipse":
            Line(ellipse=(x0, y0, w, h), width=1.5)
        else:
            Line(rectangle=(x0, y0, w, h), width=1.5)

    # ----- tables, charts, pictures
    def _tex_for(self, text, px, color, bold=False):
        px = max(1, int(round(px)))
        key = ("t", text, px, color, bold)
        tex = self._tex.get(key)
        if tex is None:
            if len(self._tex) > 600:
                self._tex.clear()
            lb = CoreLabel(text=text, font_size=px, color=_rgb(color), bold=bold)
            lb.refresh()
            tex = lb.texture
            self._tex[key] = tex
        return tex

    def _label_at(self, text, px, color, x, y, anchor="l", bold=False, maxw=None):
        """Draw a one-line label whose left/centre/right edge (anchor) is at screen x, centred at y."""
        if px < 4 or not text:
            return
        tex = self._tex_for(text, px, color, bold)
        if tex is None:
            return
        tw = tex.width
        if maxw is not None and tw > maxw:
            if maxw < 4:
                return
            tex = tex.get_region(0, 0, maxw, tex.height)
            tw = maxw
        left = x if anchor == "l" else x - tw / 2 if anchor == "c" else x - tw
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(left, y - tex.height / 2), size=(tw, tex.height))

    def _grid_for(self, o):
        key = (o["id"], hash(repr(o["cells"])))
        g = self._grids.get(key)
        if g is None:
            if len(self._grids) > 60:
                self._grids.clear()
            g = sd.display_grid(o["cells"])
            self._grids[key] = g
        return g

    def _draw_table(self, o, sx, sy, w, h, a):
        z = self.view.zoom
        rows = sd.visible_rows(o)
        cols = len(o["cells"][0])
        grid = self._grid_for(o)
        rh, cw = h / len(rows), w / cols
        px = min(o["size"], rh / z * 0.62) * z
        for k, r in enumerate(rows):
            hdr = o["header"] and r == 0
            top = sy + h - k * rh
            Color(*_rgb(o["hdr_bg"] if hdr else o["cell_bg"], a))
            Rectangle(pos=(sx, top - rh), size=(w, rh))
            if px >= 4:
                fg = o["hdr_fg"] if hdr else o["cell_fg"]
                for c in range(cols):
                    txt = grid[r][c]
                    right = not hdr and sd.num(txt) is not None
                    x = sx + (c + 1) * cw - 4 * z if right else sx + c * cw + 4 * z
                    self._label_at(txt, px, fg, x, top - rh / 2, "r" if right else "l", hdr,
                                   maxw=int(cw - 8 * z))
        Color(*_rgb(o["grid"], a))
        for k in range(len(rows) + 1):
            y = sy + h - k * rh
            Line(points=[sx, y, sx + w, y], width=1)
        for c in range(cols + 1):
            Line(points=[sx + c * cw, sy, sx + c * cw, sy + h], width=1)

    def _draw_chart(self, o, sx, sy, w, h, a):
        z = self.view.zoom
        data = sc.chart_data_for(self.doc, o)
        lay = sd.chart_layout(o, data, o["w"], o["h"])
        top = sy + h

        def P(lx, ly):
            return sx + lx * z, top - ly * z
        Color(*_rgb(o["bg"], a))
        Rectangle(pos=(sx, sy), size=(w, h))
        fg = o["fg"]
        small = 11 * z
        if o["title"]:
            self._label_at(o["title"], 15 * z, fg, sx + w / 2, top - 15 * z, "c", True, maxw=int(w - 8))
        px_, py_, pw_, ph_ = lay["plot"]
        if lay["kind"] != "pie":
            for val, ly in lay["ticks"]:
                x0, y0 = P(px_, ly)
                Color(*_rgb(fg, 0.15 * a))
                Line(points=[x0, y0, x0 + pw_ * z, y0], width=1)
                self._label_at(sd.fmt_axis(val), small, fg, x0 - 4 * z, y0, "r")
            stride = max(1, math.ceil(len(lay["cats"]) * 46 / pw_))
            for i, (lab, lx) in enumerate(lay["cats"]):
                if i % stride == 0:
                    x0, _ = P(lx, 0)
                    self._label_at(lab, small, fg, x0, P(0, py_ + ph_ + 14)[1], "c",
                                   maxw=int(stride * pw_ / len(lay["cats"]) * z))
            Color(*_rgb(fg, a))
            ax, ay = P(px_, lay["zero_y"])
            Line(points=[ax, ay, ax + pw_ * z, ay], width=1.2)
            bx, by = P(px_, py_)
            Line(points=[bx, by, bx, P(px_, py_ + ph_)[1]], width=1.2)
        if lay["kind"] == "bar":
            for x, y, bw, bh, si in lay["bars"]:
                bx, by = P(x, y + bh)
                Color(*_rgb(sd.CHART_COLORS[si % len(sd.CHART_COLORS)], a))
                Rectangle(pos=(bx, by), size=(bw * z, bh * z))
        elif lay["kind"] == "line":
            for si, pts in enumerate(lay["lines"]):
                col = sd.CHART_COLORS[si % len(sd.CHART_COLORS)]
                flat = []
                for lx, ly in pts:
                    flat += list(P(lx, ly))
                Color(*_rgb(col, a))
                if len(flat) >= 4:
                    Line(points=flat, width=max(1.5, 2 * z))
                r = max(2.0, 3.5 * z)
                for lx, ly in pts:
                    qx, qy = P(lx, ly)
                    Ellipse(pos=(qx - r, qy - r), size=(2 * r, 2 * r))
        elif lay["kind"] == "pie" and "pie" in lay:
            cx, cy, rad = lay["pie"]
            qx, qy = P(cx, cy)
            for start, sweep, i in lay["slices"]:
                Color(*_rgb(sd.CHART_COLORS[i % len(sd.CHART_COLORS)], a))
                Ellipse(pos=(qx - rad * z, qy - rad * z), size=(2 * rad * z, 2 * rad * z),
                        angle_start=start, angle_end=start + sweep + 0.3)
        for name, ci, lx, ly in lay["legend"]:
            qx, qy = P(lx, ly + 8)
            Color(*_rgb(sd.CHART_COLORS[ci], a))
            Rectangle(pos=(qx, qy - 5 * z), size=(10 * z, 10 * z))
            self._label_at(name, small, fg, qx + 14 * z, qy, "l",
                           maxw=int(max(o["w"] - lx - 16, 10) * z))

    def _asset_texture(self, name):
        if name in self._imgs:
            return self._imgs[name]
        tex = None
        data = self.doc.assets.get(name)
        if data:
            try:
                tex = CoreImage(io.BytesIO(data), ext=os.path.splitext(name)[1].lstrip(".") or "png").texture
            except Exception:
                tex = None
        self._imgs[name] = tex
        return tex

    def _draw_image(self, o, sx, sy, w, h, a):
        tex = self._asset_texture(o["asset"])
        if tex is None:
            Color(0.35, 0.35, 0.38, a)
            Rectangle(pos=(sx, sy), size=(w, h))
            Color(0.8, 0.8, 0.85, a)
            Line(points=[sx, sy, sx + w, sy + h], width=1)
            Line(points=[sx, sy + h, sx + w, sy], width=1)
            return
        Color(1, 1, 1, a)
        Rectangle(texture=tex, pos=(sx, sy), size=(w, h))


# ====================================================================== slides
class SlideCanvas(StudioCanvas):
    """Draws one frame (a slide) fitted to its box; a tap goes to the next / previous slide."""

    def __init__(self, doc, **kw):
        self.frame = None
        self.on_nav = lambda step: None
        super().__init__(doc, **kw)

    def show(self, frame):
        self.frame = frame
        self.only = se.slide_ids(self.doc, frame)
        self.fit()

    def fit(self):
        if self.frame is not None and self.width > 1 and self.height > 1:
            self.view.fit(sc.bbox(self.frame), self.width, self.height, pad=0)
        self.redraw()

    def _resized(self, *a):
        self.view.h = self.height
        self.fit()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        btn = getattr(touch, "button", "left")
        if btn == "scrollup":
            self.on_nav(-1)
        elif btn == "scrolldown":
            self.on_nav(1)
        elif btn == "right" or (touch.x - self.x) < self.width * 0.3:
            self.on_nav(-1)
        else:
            self.on_nav(1)
        return True

    def on_touch_move(self, touch):
        return True

    def on_touch_up(self, touch):
        return True


class SlideShow(ModalView):
    def __init__(self, doc, slides, index, **kw):
        super().__init__(size_hint=(1, 1), auto_dismiss=False, background="",
                         background_color=(0, 0, 0, 1), **kw)
        self.doc, self.slides = doc, slides
        self.i = max(0, min(index, len(slides) - 1))
        col = BoxLayout(orientation="vertical")
        self.cv = SlideCanvas(doc)
        self.cv.on_nav = self.step
        col.add_widget(self.cv)
        bar = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4), padding=(dp(4), 0))
        for text, fn, w in (("< Prev", lambda: self.step(-1), 70), ("Next >", lambda: self.step(1), 70)):
            b = Button(text=text, size_hint_x=None, width=dp(w), font_size=sp(12))
            b.bind(on_release=lambda *a, f=fn: f())
            bar.add_widget(b)
        self.count = Label(text="", font_size=sp(12), color=(0.8, 0.8, 0.8, 1))
        bar.add_widget(self.count)
        ex = Button(text="Exit (Esc)", size_hint_x=None, width=dp(90), font_size=sp(12))
        ex.bind(on_release=lambda *a: self.dismiss())
        bar.add_widget(ex)
        col.add_widget(bar)
        self.add_widget(col)
        self.bind(on_open=lambda *a: Window.bind(on_key_down=self._key), on_dismiss=lambda *a: Window.unbind(on_key_down=self._key))
        self.go(self.i)

    def go(self, i):
        self.i = max(0, min(i, len(self.slides) - 1))
        self.cv.show(self.slides[self.i])
        self.count.text = f"{self.i + 1} / {len(self.slides)}   {self.slides[self.i]['name']}"

    def step(self, d):
        if d > 0 and self.i == len(self.slides) - 1:
            return
        self.go(self.i + d)

    def _key(self, win, key, *a):
        if key in (275, 32, 281, 13, 271):
            self.step(1)
        elif key in (276, 280, 8):
            self.step(-1)
        elif key == 278:
            self.go(0)
        elif key == 279:
            self.go(len(self.slides) - 1)
        elif key == 27:
            self.dismiss()
        else:
            return False
        return True


def render_slide_png(doc, frame, path, scale=1.0):
    """Draw one slide off screen and save it as a PNG; returns (width, height)."""
    from kivy.graphics import ClearBuffers, ClearColor, Fbo
    w, h = se.slide_pixels(frame, scale=scale)
    cv = SlideCanvas(doc)
    cv.pos, cv.size = (0, 0), (w, h)
    cv.show(frame)
    fbo = Fbo(size=(w, h))
    with fbo:
        ClearColor(0, 0, 0, 0)
        ClearBuffers()
    fbo.add(cv.canvas)
    fbo.draw()
    fbo.texture.save(path, flipped=True)
    fbo.remove(cv.canvas)
    return w, h


# ====================================================================== the screen
class StudioScreen(Screen):
    title = "Srboli Studio"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.doc = sc.Document()
        self.path = None
        self.dirty = False
        self.tab = "props"
        self._fields = {}
        self._popups = 0
        self._narrow = None
        self._panel_open = False
        self._asked_recovery = False
        self._autosave_ev = None

        root = BoxLayout(orientation="vertical", spacing=dp(2), padding=dp(4))
        root.add_widget(self._build_toolbar())
        self.main = BoxLayout(spacing=dp(3))
        self.sidebar = self._build_sidebar()
        self.canvas_w = StudioCanvas(self.doc)
        cw = self.canvas_w
        cw.on_change, cw.on_select = self._doc_changed, self._sel_changed
        cw.on_view, cw.on_hint, cw.on_live = self._view_changed, self._hint, self._live
        cw.on_tool, cw.on_edit_text = self._tool_changed, self.edit_text
        cw.on_edit_table = self.edit_table
        self.center_col = BoxLayout(orientation="vertical")
        self.panel = self._build_panel()
        self.main.add_widget(self.sidebar)
        self.main.add_widget(self.center_col)
        root.add_widget(self.main)
        self.hint_label = _label(HINTS["select"], 11, theme.MUTED, h=dp(22))
        root.add_widget(self.hint_label)
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
        for w in (self.canvas_w, self.panel):
            if w.parent:
                w.parent.remove_widget(w)
        self.center_col.clear_widgets()
        self.center_col.add_widget(self.canvas_w)
        if narrow:
            self.panel.size_hint = (1, None)
            self.panel.height = dp(300)
            if self._panel_open:
                self.center_col.add_widget(self.panel)
        else:
            self.panel.size_hint = (None, 1)
            self.panel.width = dp(300)
            self.main.add_widget(self.panel)

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
        self.title_label = Label(text="[b]Srboli Studio[/b]", markup=True, font_size=sp(14),
                                 size_hint_x=None, width=dp(190), halign="left")
        self.title_label.bind(size=lambda w, s: setattr(w, "text_size", s))
        bar.add_widget(self.title_label)
        add("New", self.new_doc, 50)
        add("Open", self.open_dialog, 56)
        add("Save", self.save, 54)
        add("Save As", self.save_as_dialog, 70)
        self.undo_btn = add("Undo", self.undo, 56)
        self.redo_btn = add("Redo", self.redo, 56)
        add("Duplicate", self.duplicate, 82)
        add("Delete", self.delete, 62)
        add("Group", self.group, 58)
        add("Ungroup", self.ungroup, 70)
        add("Zoom -", lambda: self.canvas_w.zoom_by(1 / 1.25), 62)
        bar.add_widget(self.zoom_label)
        add("Zoom +", lambda: self.canvas_w.zoom_by(1.25), 62)
        add("Fit", lambda: self.canvas_w.fit(), 44)
        add("Present", self.present, 66)
        add("Export slides", self.export_dialog, 100)
        self.panel_btn = add("Panel", self.toggle_panel, 60)
        sv.add_widget(bar)
        return sv

    def _build_sidebar(self):
        col = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(72), spacing=dp(2))
        self.tool_btns = {}
        for key, text in TOOLS:
            b = Button(text=text, font_size=sp(11), background_normal="")
            b.bind(on_release=lambda w, k=key: self.set_tool(k))
            col.add_widget(b)
            self.tool_btns[key] = b
        return col

    def _build_panel(self):
        box = BoxLayout(orientation="vertical", spacing=dp(2))
        tabs = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(2))
        self.tab_btns = {}
        for key, text in (("props", "Properties"), ("layers", "Layers"), ("doc", "Document")):
            b = Button(text=text, font_size=sp(12), background_normal="")
            b.bind(on_release=lambda w, k=key: self.set_tab(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        box.add_widget(tabs)
        self.panel_scroll = ScrollView(bar_width=dp(4))
        self.panel_body = GridLayout(cols=1, spacing=dp(4), padding=dp(4), size_hint_y=None)
        self.panel_body.bind(minimum_height=self.panel_body.setter("height"))
        self.panel_scroll.add_widget(self.panel_body)
        box.add_widget(self.panel_scroll)
        return box

    # ------------------------------------------------------------ keyboard
    def on_pre_enter(self, *a):
        Window.bind(on_key_down=self._key_down, on_key_up=self._key_up)
        if not self._asked_recovery:
            self._asked_recovery = True
            if sc.has_recovery(self._folder()) and not self.doc.objects:
                Clock.schedule_once(lambda dt: self._offer_recovery(), 0.3)

    def on_leave(self, *a):
        Window.unbind(on_key_down=self._key_down, on_key_up=self._key_up)

    def _key_up(self, win, key, *a):
        if key in (303, 304):
            self.canvas_w.shift = False
        return False

    def _typing(self):
        return any(getattr(t, "focus", False) for t in self.panel.walk() if isinstance(t, TextInput))

    def _key_down(self, win, key, scancode, text, modifiers):
        if key in (303, 304):
            self.canvas_w.shift = True
        if self._popups or (self.manager and self.manager.current != self.name):
            return False
        if self._typing():
            return False
        ctrl = "ctrl" in modifiers or "meta" in modifiers
        shift = "shift" in modifiers
        if ctrl and key == 122:
            self.redo() if shift else self.undo()
        elif ctrl and key == 121:
            self.redo()
        elif ctrl and key == 115:
            self.save()
        elif ctrl and key == 100:
            self.duplicate()
        elif ctrl and key == 103:
            self.ungroup() if shift else self.group()
        elif ctrl and key == 97:
            self.canvas_w.set_sel([o["id"] for o in self.doc.objects
                                   if self.doc.effective_visible(o) and not self.doc.effective_locked(o)
                                   and self.doc.top_level(o) is o])
        elif key in (127, 8):
            self.delete()
        elif key == 27:
            self.set_tool("select")
            self.canvas_w.set_sel(())
        elif key in (273, 274, 275, 276) and self.canvas_w.sel:
            step = (self.doc.settings["grid_size"] if shift else 1) or 1
            dx = {275: step, 276: -step}.get(key, 0)
            dy = {274: step, 273: -step}.get(key, 0)
            self._edit(lambda: [sc.translate_tree(self.doc, o, dx, dy)
                                for o in sc.roots(self.doc, self.canvas_w.sel)])
        else:
            return False
        return True

    # ------------------------------------------------------------ state
    def _hint(self, text):
        self.hint_label.text = text

    def set_tool(self, tool):
        if tool == "image":
            self.add_image_dialog()
            tool = "select"
        self.canvas_w.set_tool(tool)
        self._tool_changed(tool)
        self._hint(HINTS[tool])

    def _tool_changed(self, tool):
        self.canvas_w.tool = tool
        for k, b in self.tool_btns.items():
            b.background_color = theme.ACCENT if k == tool else (0.25, 0.25, 0.25, 1)

    def set_tab(self, tab):
        self.tab = tab
        self.refresh_panel()

    def _view_changed(self):
        self.zoom_label.text = f"{int(round(self.canvas_w.view.zoom * 100))}%"

    def _live(self):
        self._sync_values()

    def _doc_changed(self):
        self.dirty = True
        self.canvas_w.prune_sel()
        self._refresh_all()
        if self._autosave_ev:
            self._autosave_ev.cancel()
        self._autosave_ev = Clock.schedule_once(lambda dt: self._autosave(), 4)

    def _sel_changed(self):
        self.refresh_panel()

    def _refresh_all(self):
        name = self.doc.settings["title"]
        mark = " *" if self.dirty else ""
        self.title_label.text = f"[b]{escape_markup(name)}{mark}[/b]"
        self.undo_btn.disabled = not self.doc._undo
        self.redo_btn.disabled = not self.doc._redo
        self.canvas_w.redraw()
        self.refresh_panel()

    def _edit(self, fn):
        """One undoable change made from a panel or key: checkpoint, change, refresh."""
        self.doc.checkpoint()
        fn()
        sc.refresh_groups(self.doc)
        self._doc_changed()

    def undo(self):
        if self.doc.undo():
            self.canvas_w.prune_sel()
            self._doc_changed()

    def redo(self):
        if self.doc.redo():
            self.canvas_w.prune_sel()
            self._doc_changed()

    def _sel_roots(self):
        return sc.roots(self.doc, self.canvas_w.sel)

    def delete(self):
        ids = [o["id"] for o in self._sel_roots() if not self.doc.effective_locked(o)]
        if ids:
            self._edit(lambda: self.doc.remove(ids))

    def duplicate(self):
        ids = [o["id"] for o in self._sel_roots()]
        if not ids:
            return
        out = []
        self._edit(lambda: out.extend(self.doc.duplicate(ids)))
        self.canvas_w.set_sel([o["id"] for o in out])

    def group(self):
        ids = [o["id"] for o in self._sel_roots()]
        res = []

        def do():
            g = self.doc.group(ids)
            if g:
                res.append(g)
        if len(ids) < 2:
            self._hint("Select two or more objects to group them.")
            return
        # grouping is refused for frames or objects in different frames: check before the checkpoint
        objs = [self.doc.get(i) for i in ids]
        if any(o["type"] == "frame" for o in objs) or len({o["parent"] for o in objs}) != 1:
            self._hint("Frames cannot be grouped, and objects must be in the same frame.")
            return
        self._edit(do)
        if res:
            self.canvas_w.set_sel([res[0]["id"]])
            self._hint("Grouped. Ungroup with the Ungroup button.")

    def ungroup(self):
        groups = [o for o in self.canvas_w.selected() if o["type"] == "group"]
        if not groups:
            self._hint("Select a group to ungroup it.")
            return
        kids = []
        self._edit(lambda: [kids.extend(self.doc.ungroup(g["id"])) for g in groups])
        self.canvas_w.set_sel([k["id"] for k in kids])

    def _order(self, step=None, edge=None):
        for o in self._sel_roots():
            oid = o["id"]
            if edge is None:
                self._edit(lambda oid=oid: self.doc.move_order(oid, step))
            else:
                self._edit(lambda oid=oid: self.doc.to_edge(oid, edge == "front"))

    # ------------------------------------------------------------ files and dialogs
    def _folder(self):
        return app_data.subdir(FOLDER)

    def new_doc(self):
        self._guard(self._reset)

    def _reset(self):
        self._set_doc(sc.Document(), None)
        self.canvas_w.fit()

    def _set_doc(self, doc, path, view=None):
        self.doc = doc
        self.canvas_w.doc = doc
        self.canvas_w.sel = set()
        self.canvas_w._tex.clear()
        self.canvas_w._grids.clear()
        self.canvas_w._imgs.clear()
        self.path, self.dirty = path, False
        if view:
            self.canvas_w.view.from_list(view)
            self.canvas_w.view.h = self.canvas_w.height
            self.canvas_w._fitted = True
            self._view_changed()
        else:
            self.canvas_w.fit()
        self._refresh_all()

    def _leave(self):
        if self.manager:
            self.manager.current = "dashboard"

    def _popup(self, title, content, wfrac=0.9, height=None, **kw):
        p = Popup(title=title, content=content, size_hint=(None, None if height else 0.9), **kw)
        p.width = min(Window.width * wfrac, dp(560))
        if height:
            p.height = min(height, Window.height * 0.95)
        p.bind(on_open=lambda *a: setattr(self, "_popups", self._popups + 1),
               on_dismiss=lambda *a: setattr(self, "_popups", max(0, self._popups - 1)))
        return p

    def _guard(self, then):
        if not self.dirty:
            then()
            return
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        lay.add_widget(Label(text="This workspace has unsaved changes."))
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

    def _chooser_popup(self, title, save, cb, default_name="", exts=(EXT,), start=None):
        lay = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))
        fc = FileChooserListView(path=start or self._folder(),
                                 filters=[f"*{e}" for e in exts] + [f"*{e.upper()}" for e in exts])
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

        if save:
            fc.bind(selection=lambda w, sel: sel and setattr(name, "text", os.path.basename(sel[0])))
        ok.bind(on_release=go)
        cancel.bind(on_release=lambda *a: pop.dismiss())
        pop.open()

    def open_dialog(self):
        self._guard(lambda: self._chooser_popup("Open workspace", False, self.load))

    def load(self, path):
        note = ""
        try:
            doc, view, _ = sc.load_package(path)
        except (OSError, ValueError) as e:
            try:
                doc, view, _ = sc.load_package(path + ".bak")
                note = " (the file was damaged, so the previous copy was opened)"
            except (OSError, ValueError):
                self._hint(f"Could not open: {e}")
                return
        self._set_doc(doc, path, view)
        self._hint(f"Opened {os.path.basename(path)}: {len(doc.objects)} objects{note}.")

    def save(self):
        if not self.path:
            self.save_as_dialog()
            return
        self._write(self.path)

    def save_as_dialog(self, then=None):
        default = os.path.basename(self.path) if self.path else \
            (self.doc.settings["title"].strip() or "workspace") + EXT
        self._chooser_popup("Save workspace", True,
                            lambda p: (self._write(p), then and then()), default)

    def _write(self, path):
        if not path.lower().endswith(EXT):
            path += EXT
        try:
            sc.save_package(self.doc, path, view=self.canvas_w.view.to_list(),
                            thumbnail=sc.render_preview(self.doc))
        except OSError as e:
            self._hint(f"Could not save: {e}")
            return
        self.path, self.dirty = path, False
        sc.clear_recovery(self._folder())
        self._refresh_all()
        self._hint(f"Saved {path}")

    def _autosave(self):
        self._autosave_ev = None
        if self.dirty:
            sc.autosave(self.doc, self._folder(), self.canvas_w.view.to_list())

    def _offer_recovery(self):
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        lay.add_widget(Label(text="Srboli Studio found work that was not saved.\nRestore it?"))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        pop = self._popup("Recover unsaved work", lay, 0.9, dp(180))

        def restore(*a):
            pop.dismiss()
            try:
                doc, view, _ = sc.load_package(sc.recovery_path(self._folder()))
            except (OSError, ValueError):
                self._hint("The recovery copy could not be read.")
                sc.clear_recovery(self._folder())
                return
            self._set_doc(doc, None, view)
            self.dirty = True
            self._refresh_all()
            self._hint("Recovered. Use Save to keep it.")

        def discard(*a):
            pop.dismiss()
            sc.clear_recovery(self._folder())
        for text, fn in (("Restore", restore), ("Discard", discard)):
            b = Button(text=text)
            b.bind(on_release=fn)
            row.add_widget(b)
        lay.add_widget(row)
        pop.open()

    # ------------------------------------------------------------ text editing and colours
    def edit_text(self, o):
        ti = TextInput(text=o["text"], multiline=True, font_size=sp(15))
        hint = _label("Markdown: # heading, - list, > quote, **bold**, *italic*", 11, theme.MUTED)
        ok = Button(text="Apply", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        for w in (hint, ti, ok):
            lay.add_widget(w)
        pop = self._popup("Edit text", lay, 0.9, dp(380))

        def go(*a):
            pop.dismiss()
            if ti.text == o["text"] or self.doc.get(o["id"]) is None:
                return

            def do():
                o["text"] = ti.text
                refit_text(o)
            self._edit(do)

        ok.bind(on_release=go)
        pop.open()
        Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0.2)

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

    # ------------------------------------------------------------ panel
    def refresh_panel(self):
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == self.tab else (0.25, 0.25, 0.25, 1)
        self.panel_body.clear_widgets()
        self._fields = {}
        {"props": self._props, "layers": self._layers, "doc": self._docpanel}[self.tab]()

    def _row(self, label, widget, h=34):
        r = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))
        lb = Label(text=label, font_size=sp(12), color=theme.MUTED, size_hint_x=None,
                   width=dp(86), halign="left", valign="middle")
        lb.bind(size=lambda w, s: setattr(w, "text_size", s))
        r.add_widget(lb)
        r.add_widget(widget)
        self.panel_body.add_widget(r)
        return r

    def _btn(self, text, fn, h=34, **kw):
        b = Button(text=text, font_size=sp(12), size_hint_y=None, height=dp(h), **kw)
        b.bind(on_release=lambda *a: fn())
        return b

    def _btn_row(self, items, h=34):
        r = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(3))
        for text, fn in items:
            r.add_widget(self._btn(text, fn, h))
        self.panel_body.add_widget(r)
        return r

    def _num_input(self, key, value, commit):
        ti = TextInput(text=value, multiline=False, font_size=sp(13), write_tab=False,
                       size_hint_y=None, height=dp(32), input_filter=None)
        state = {"v": value}

        def fire(*a):
            if ti.text != state["v"]:
                state["v"] = ti.text
                commit(ti.text)
        ti.bind(on_text_validate=fire, focus=lambda w, f: (not f) and fire())
        ti._state = state
        self._fields[key] = ti
        return ti

    def _text_input(self, key, value, commit):
        return self._num_input(key, value, commit)

    def _geom_text(self, o, key):
        return sc.fmt(o[key], 2 if key != "rot" else 1)

    def _apply_geom(self, o, key, text):
        try:
            val = float(text.replace(",", "."))
        except ValueError:
            self._hint("That is not a number.")
            self._sync_values(force=True)
            return
        if abs(val - o[key]) < 1e-9:
            return
        self.doc.checkpoint()
        if not sc.set_geom(self.doc, o, key, val):
            self.doc._undo.pop()
            self._hint("That value is not allowed for this object.")
            self._sync_values(force=True)
            return
        if o["type"] == "text" and key == "w":
            refit_text(o)
        self._doc_changed()

    def _sync_values(self, force=False):
        sel = self.canvas_w.selected()
        if len(sel) != 1:
            return
        o = sel[0]
        for key, ti in self._fields.items():
            if key in ("x", "y", "w", "h", "rot") and (force or not ti.focus):
                txt = self._geom_text(o, key)
                ti.text = txt
                ti._state["v"] = txt

    def _props(self):
        sel = self.canvas_w.selected()
        body = self.panel_body
        if not sel:
            body.add_widget(_label("Nothing selected.", 13, theme.MUTED))
            body.add_widget(_label("Pick a tool on the left, then click or drag on the canvas. "
                                   "Everything you place is an independent object.", 11, theme.MUTED, h=dp(70)))
            return
        if len(sel) > 1:
            self._multi_props(sel)
            return
        o = sel[0]
        t = o["type"]
        body.add_widget(_label(f"[b]{t.capitalize()}[/b]", 13))
        name = TextInput(text=o["name"], multiline=False, font_size=sp(13), size_hint_y=None,
                         height=dp(32))
        name.bind(on_text_validate=lambda w: self._set(o, "name", w.text),
                  focus=lambda w, f: (not f) and w.text != o["name"] and self._set(o, "name", w.text))
        self._row("Name", name)
        grid = GridLayout(cols=2, spacing=dp(3), size_hint_y=None, height=dp(3 * 36))
        for key, label in (("x", "X"), ("y", "Y"), ("w", "Width"), ("h", "Height"), ("rot", "Turn °")):
            cell = BoxLayout(spacing=dp(2), size_hint_y=None, height=dp(34))
            cell.add_widget(Label(text=label, font_size=sp(11), color=theme.MUTED, size_hint_x=None,
                                  width=dp(44)))
            cell.add_widget(self._num_input(key, self._geom_text(o, key),
                                            lambda txt, k=key: self._apply_geom(o, k, txt)))
            grid.add_widget(cell)
        body.add_widget(grid)
        grid.height = dp(36) * math.ceil(len(grid.children) / 2)
        self._btn_row([("Visible" if o["visible"] else "Hidden", lambda: self._toggle(o, "visible")),
                       ("Locked" if o["locked"] else "Unlocked", lambda: self._toggle(o, "locked"))])
        op = self._num_input("opacity", str(int(round(o["opacity"] * 100))),
                             lambda txt: self._set_opacity(o, txt))
        self._row("Opacity %", op)
        self._btn_row([("To back", lambda: self._order(edge="back")),
                       ("Backward", lambda: self._order(step=-1)),
                       ("Forward", lambda: self._order(step=1)),
                       ("To front", lambda: self._order(edge="front"))])
        if t == "text":
            self._text_props(o)
        elif t == "shape":
            self._shape_props(o)
        elif t == "frame":
            self._frame_props(o)
        elif t == "table":
            self._table_props(o)
        elif t == "chart":
            self._chart_props(o)
        elif t == "image":
            self._image_props(o)
        elif t == "group":
            n = len(self.doc.descendants(o["id"]))
            body.add_widget(_label(f"Holds {n} object(s). Moving, resizing or turning the group "
                                   "changes all of them.", 11, theme.MUTED, h=dp(46)))
            body.add_widget(self._btn("Ungroup", self.ungroup))

    def _color_row(self, label, o, key, allow_none=False):
        b = Button(text=o[key] or "none", font_size=sp(12), size_hint_y=None, height=dp(32),
                   background_normal="", background_color=_rgb(o[key]) if o[key] else (0.25, 0.25, 0.25, 1))
        if o[key]:
            lum = sum(_rgb(o[key])[:3]) / 3
            b.color = (0, 0, 0, 1) if lum > 0.55 else (1, 1, 1, 1)
        b.bind(on_release=lambda *a: self.pick_color(label, allow_none,
                                                     lambda c: self._set(o, key, c)))
        self._row(label, b, 32)

    def _set(self, o, key, val):
        if o.get(key) == val or self.doc.get(o["id"]) is None:
            return

        def do():
            o[key] = val
            if o["type"] == "text" and key in ("size", "bold", "italic", "mode", "pad"):
                refit_text(o)
        self._edit(do)

    def _toggle(self, o, key):
        self._set(o, key, not o[key])

    def _set_opacity(self, o, text):
        try:
            v = max(0.0, min(100.0, float(text.replace(",", ".")))) / 100
        except ValueError:
            return
        self._set(o, "opacity", v)

    def _num_prop(self, label, o, key, lo, hi, fmt_digits=1):
        def commit(txt):
            try:
                v = max(lo, min(hi, float(txt.replace(",", "."))))
            except ValueError:
                self._hint("That is not a number.")
                return
            self._set(o, key, v)
        self._row(label, self._num_input("p_" + key, sc.fmt(o[key], fmt_digits), commit))

    def _text_props(self, o):
        self._btn_row([("Edit text...", lambda: self.edit_text(o))])
        self._num_prop("Font size", o, "size", 4, 400)
        self._num_prop("Padding", o, "pad", 0, 200)
        self._color_row("Text colour", o, "color")
        self._color_row("Background", o, "fill", True)
        self._btn_row([("Bold: " + ("on" if o["bold"] else "off"), lambda: self._toggle(o, "bold")),
                       ("Italic: " + ("on" if o["italic"] else "off"), lambda: self._toggle(o, "italic"))])
        al = Spinner(text=o["align"], values=("left", "center", "right"), size_hint_y=None,
                     height=dp(32), font_size=sp(12))
        al.bind(text=lambda w, v: self._set(o, "align", v))
        self._row("Align", al, 32)
        md = Spinner(text=o["mode"], values=("markdown", "plain"), size_hint_y=None, height=dp(32),
                     font_size=sp(12))
        md.bind(text=lambda w, v: self._set(o, "mode", v))
        self._row("Text mode", md, 32)
        self._btn_row([("Auto height: " + ("on" if o["autofit"] else "off"),
                        lambda: (self._set(o, "autofit", not o["autofit"]), refit_text(o),
                                 self._doc_changed()))])

    def _shape_props(self, o):
        sp_ = Spinner(text=o["shape"], values=sc.SHAPES, size_hint_y=None, height=dp(32),
                      font_size=sp(12))
        sp_.bind(text=lambda w, v: self._set(o, "shape", v))
        self._row("Shape", sp_, 32)
        line = o["shape"] in ("line", "arrow")
        if not line:
            self._color_row("Fill", o, "fill", True)
        self._color_row("Line colour", o, "stroke")
        self._num_prop("Line width", o, "width", 0, 200)
        if o["shape"] == "rounded":
            self._num_prop("Corner radius", o, "radius", 0, 2000)

    def _frame_props(self, o):
        preset = Spinner(text=o["preset"], values=tuple(sc.FRAME_PRESETS), size_hint_y=None,
                         height=dp(32), font_size=sp(12))

        def pick(w, v):
            if v == o["preset"] or v not in sc.FRAME_PRESETS:
                return

            def do():
                o["preset"] = v
                if v != "Custom":
                    o["w"], o["h"] = map(float, sc.FRAME_PRESETS[v])
            self._edit(do)
        preset.bind(text=pick)
        self._row("Size preset", preset, 32)
        self._color_row("Page colour", o, "bg")
        self._color_row("Border", o, "border")
        n = len(self.doc.children(o["id"]))
        self.panel_body.add_widget(_label(f"{n} object(s) inside. Moving the frame moves them too.",
                                          11, theme.MUTED, h=dp(36)))

    def _multi_props(self, sel):
        roots = sc.roots(self.doc, self.canvas_w.sel)
        self.panel_body.add_widget(_label(f"[b]{len(sel)} objects selected[/b]", 13))

        def align(how):
            def do():
                for o, dx, dy in sc.align(roots, how):
                    sc.translate_tree(self.doc, o, dx, dy)
            self._edit(do)

        def dist(axis):
            def do():
                for o, dx, dy in sc.distribute(roots, axis):
                    sc.translate_tree(self.doc, o, dx, dy)
            self._edit(do)
        self.panel_body.add_widget(_label("Align", 12, theme.MUTED))
        self._btn_row([("Left", lambda: align("left")), ("Centre", lambda: align("hcenter")),
                       ("Right", lambda: align("right"))])
        self._btn_row([("Top", lambda: align("top")), ("Middle", lambda: align("vcenter")),
                       ("Bottom", lambda: align("bottom"))])
        self.panel_body.add_widget(_label("Spread evenly (3 or more)", 12, theme.MUTED))
        self._btn_row([("Horizontally", lambda: dist("h")), ("Vertically", lambda: dist("v"))])
        self._btn_row([("Group", self.group), ("Duplicate", self.duplicate), ("Delete", self.delete)])

    # ----- layers
    def _layers(self):
        body = self.panel_body
        if not self.doc.objects:
            body.add_widget(_label("No objects yet.", 12, theme.MUTED))
            return

        def depth(o):
            return len(self.doc.ancestors(o))

        # front-most first; a frame's contents are listed under it
        top = [o for o in self.doc.objects if o["parent"] is None]
        order = []

        def add(o):
            order.append(o)
            kids = [k for k in self.doc.objects if k["parent"] == o["id"]]
            for k in reversed(kids):
                add(k)
        for o in reversed([x for x in top if x["type"] != "frame"]):
            add(o)
        for o in reversed([x for x in top if x["type"] == "frame"]):
            add(o)
        for o in order:
            row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(2))
            row.add_widget(Label(size_hint_x=None, width=dp(12) * depth(o)))
            eye = Button(text="Shown" if o["visible"] else "Hidden", font_size=sp(10), size_hint_x=None,
                         width=dp(46))
            eye.bind(on_release=lambda *a, o=o: self._toggle(o, "visible"))
            lock = Button(text="Locked" if o["locked"] else "Free", font_size=sp(10), size_hint_x=None,
                          width=dp(46))
            lock.bind(on_release=lambda *a, o=o: self._toggle(o, "locked"))
            sel = o["id"] in self.canvas_w.sel
            nm = Button(text=f"{o['type'][:1].upper()}  {o['name']}", font_size=sp(12), halign="left",
                        background_normal="",
                        background_color=theme.ACCENT if sel else (0.22, 0.22, 0.22, 1))
            nm.bind(size=lambda w, s: setattr(w, "text_size", (s[0] - dp(8), None)))
            nm.bind(on_release=lambda *a, o=o: self.canvas_w.set_sel([o["id"]]))
            for w in (nm, eye, lock):
                row.add_widget(w)
            body.add_widget(row)

    # ----- document
    def _docpanel(self):
        s = self.doc.settings
        body = self.panel_body
        title = TextInput(text=s["title"], multiline=False, font_size=sp(13), size_hint_y=None,
                          height=dp(32))

        def set_title(*a):
            if title.text.strip() and title.text != s["title"]:
                self._edit(lambda: s.__setitem__("title", title.text.strip()[:100]))
        title.bind(on_text_validate=set_title, focus=lambda w, f: (not f) and set_title())
        self._row("Title", title)
        self._btn_row([("Grid: " + ("on" if s["grid"] else "off"), lambda: self._setting("grid", not s["grid"])),
                       ("Snap grid: " + ("on" if s["snap_grid"] else "off"),
                        lambda: self._setting("snap_grid", not s["snap_grid"]))])
        self._btn_row([("Snap to objects: " + ("on" if s["snap_objects"] else "off"),
                        lambda: self._setting("snap_objects", not s["snap_objects"]))])

        def gsize(txt):
            try:
                v = float(txt.replace(",", "."))
            except ValueError:
                return
            if 2 <= v <= 2000:
                self._setting("grid_size", v)
        self._row("Grid size", self._num_input("grid", sc.fmt(s["grid_size"]), gsize))
        bg = Button(text=s["background"], size_hint_y=None, height=dp(32), background_normal="",
                    background_color=_rgb(s["background"]), font_size=sp(12))
        bg.bind(on_release=lambda *a: self.pick_color("Canvas colour", False,
                                                      lambda c: self._setting("background", c)))
        self._row("Canvas colour", bg, 32)
        nf = sum(1 for o in self.doc.objects if o["type"] == "frame")
        self.panel_body.add_widget(_label(
            f"{len(self.doc.objects)} objects, {nf} frame(s)\n"
            f"File: {os.path.basename(self.path) if self.path else 'not saved yet'}", 11, theme.MUTED, h=dp(40)))

    def _setting(self, key, val):
        if self.doc.settings.get(key) == val:
            return
        self._edit(lambda: self.doc.settings.__setitem__(key, val))

    # ------------------------------------------------------------ tables, charts, pictures
    def add_image_dialog(self):
        self._chooser_popup("Add a picture", False, self.add_image, exts=sd.IMAGE_EXT,
                            start=os.path.expanduser("~"))

    def add_image(self, path):
        try:
            if os.path.getsize(path) > sd.MAX_ASSET:
                raise ValueError("The picture is larger than 20 MB.")
            with open(path, "rb") as f:
                data = f.read()
            o = sc.add_image(self.doc, os.path.basename(path), data)
        except (OSError, ValueError) as e:
            self._hint(f"Could not add the picture: {e}")
            return
        cx, cy = self.canvas_w.view.to_world(self.canvas_w.width / 2, self.canvas_w.height / 2)
        o["x"], o["y"] = cx - o["w"] / 2, cy - o["h"] / 2

        def do():
            self.doc.add(o)
            sc.assign_parent(self.doc, o)
        self._edit(do)
        self.canvas_w._imgs.pop(o["asset"], None)
        self.canvas_w.set_sel([o["id"]])
        self._hint(f"Added {o['asset']}.")

    def _image_props(self, o):
        size = sd.image_size(self.doc.assets.get(o["asset"], b""))
        info = f"{o['asset']}" + (f"  ({size[0]} x {size[1]} px)" if size else "  (picture missing)")
        self.panel_body.add_widget(_label(escape_markup(info), 11, theme.MUTED, h=dp(36)))

        def ratio():
            if size:
                self._edit(lambda: o.__setitem__("h", max(sc.MIN_SIZE, o["w"] * size[1] / size[0])))
        self._btn_row([("Original proportions", ratio)])
        self._btn_row([("Replace picture...", lambda: self._chooser_popup(
            "Replace picture", False, lambda p: self._replace_image(o, p), exts=sd.IMAGE_EXT,
            start=os.path.expanduser("~")))])

    def _replace_image(self, o, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
            new = sc.add_image(self.doc, os.path.basename(path), data)
        except (OSError, ValueError) as e:
            self._hint(f"Could not use the picture: {e}")
            return
        self._edit(lambda: o.__setitem__("asset", new["asset"]))

    # ----- tables
    def edit_table(self, o):
        cells = o["cells"]
        rows, cols = len(cells), len(cells[0])
        if rows * cols > 700:
            self._hint("This table is large: use Paste data... to replace it, or edit a column in a spreadsheet.")
            return
        cw, ch = dp(96), dp(34)
        grid = GridLayout(cols=cols + 1, size_hint=(None, None), spacing=dp(2),
                          height=(rows + 1) * (ch + dp(2)))
        grid.add_widget(Label(size_hint=(None, None), size=(dp(30), ch)))
        for c in range(cols):
            grid.add_widget(Label(text=sd.col_name(c), size_hint=(None, None), size=(cw, ch),
                                  color=theme.MUTED))
        inputs = {}
        for r in range(rows):
            grid.add_widget(Label(text=str(r + 1), size_hint=(None, None), size=(dp(30), ch),
                                  color=theme.MUTED))
            for c in range(cols):
                ti = TextInput(text=cells[r][c], multiline=False, size_hint=(None, None),
                               size=(cw, ch), font_size=sp(13), write_tab=False)
                inputs[(r, c)] = ti
                grid.add_widget(ti)
        grid.width = dp(30) + cols * (cw + dp(2)) + dp(4)
        sv = ScrollView(do_scroll_x=True, do_scroll_y=True, bar_width=dp(6))
        sv.add_widget(grid)
        ok = Button(text="Apply", size_hint_y=None, height=dp(44))
        cancel = Button(text="Cancel", size_hint_y=None, height=dp(44))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(ok)
        row.add_widget(cancel)
        lay = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(4))
        lay.add_widget(_label("Text starting with = is a formula: =SUM(B2:B4), =B2*C2", 11, theme.MUTED))
        lay.add_widget(sv)
        lay.add_widget(row)
        pop = self._popup("Edit table", lay, 0.97, Window.height * 0.9)

        def go(*a):
            pop.dismiss()
            new = {k: ti.text for k, ti in inputs.items()}
            if all(cells[r][c] == v for (r, c), v in new.items()):
                return

            def do():
                for (r, c), v in new.items():
                    sd.set_cell(o, r, c, v)
            self._edit(do)
        ok.bind(on_release=go)
        cancel.bind(on_release=lambda *a: pop.dismiss())
        pop.open()

    def paste_dialog(self, o, title="Paste table data", apply=None):
        ti = TextInput(text="", multiline=True, font_size=sp(13), hint_text="Paste rows here")
        msg = _label("Tab, comma or semicolon separated, or a Markdown table.", 11, theme.MUTED)
        ok = Button(text="Replace with this data", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        for w in (msg, ti, ok):
            lay.add_widget(w)
        pop = self._popup(title, lay, 0.9, dp(420))

        def go(*a):
            try:
                cells = sd.parse_table_text(ti.text)
            except ValueError as e:
                msg.text = f"[color=ff6666]{escape_markup(str(e))}[/color]"
                return
            pop.dismiss()
            (apply or self._apply_cells)(o, cells)
        ok.bind(on_release=go)
        pop.open()
        Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0.2)

    def _apply_cells(self, o, cells):
        def do():
            rows_before = len(o["cells"])
            o["cells"] = cells
            o["h"] = max(sc.MIN_SIZE, o["h"] / rows_before * len(cells))
            o["w"] = max(sc.MIN_SIZE, 100.0 * len(cells[0]) if o["w"] < 40 else o["w"])
            o["fcol"], o["ftext"] = -1, ""
        self._edit(do)

    def export_csv(self, o):
        def write(path):
            if not path.lower().endswith(".csv"):
                path += ".csv"
            try:
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(sd.to_csv(o["cells"]))
            except OSError as e:
                self._hint(f"Could not save: {e}")
                return
            self._hint(f"Saved {path}")
        self._chooser_popup("Export table as CSV", True, write, (o["name"] or "table") + ".csv", exts=(".csv",))

    def import_csv(self, o):
        def read(path):
            try:
                if os.path.getsize(path) > 5_000_000:
                    raise ValueError("The file is too large.")
                with open(path, encoding="utf-8-sig") as f:
                    cells = sd.parse_table_text(f.read())
            except (OSError, ValueError, UnicodeDecodeError) as e:
                self._hint(f"Could not read the CSV: {e}")
                return
            self._apply_cells(o, cells)
        self._chooser_popup("Import a CSV file", False, read, exts=(".csv", ".tsv", ".txt"),
                            start=os.path.expanduser("~"))

    def _col_row_inputs(self, o):
        """Row number and column letter used by the row / column buttons."""
        st = self.__dict__.setdefault("_tsel", {"row": "2", "col": "A"})
        self._row("Row #", self._num_input("t_row", st["row"], lambda t: st.__setitem__("row", t)))
        self._row("Column", self._num_input("t_col", st["col"], lambda t: st.__setitem__("col", t.upper())))
        return st

    def _table_do(self, o, st, what):
        def row():
            r = int(float(self._fields["t_row"].text)) - 1
            if not 0 <= r < len(o["cells"]):
                raise ValueError("That row does not exist.")
            return r

        def col():
            c = sd.parse_col(self._fields["t_col"].text)
            if c >= len(o["cells"][0]):
                raise ValueError("That column does not exist.")
            return c
        try:
            if what == "row+":
                r = row()
                self._edit(lambda: sd.add_row(o, r))
            elif what == "row-":
                r = row()
                if len(o["cells"]) <= 1:
                    raise ValueError("A table needs at least one row.")
                self._edit(lambda: sd.delete_row(o, r))
            elif what == "col+":
                c = col()
                self._edit(lambda: sd.add_col(o, c))
            elif what == "col-":
                c = col()
                if len(o["cells"][0]) <= 1:
                    raise ValueError("A table needs at least one column.")
                self._edit(lambda: sd.delete_col(o, c))
            elif what in ("asc", "desc"):
                c = col()
                self._edit(lambda: sd.sort_rows(o, c, what == "desc"))
        except ValueError as e:
            self._hint(str(e) if "column" in str(e).lower() or "row" in str(e).lower() else "Enter a number for the row.")

    def _table_props(self, o):
        nr, nc = len(o["cells"]), len(o["cells"][0])
        self.panel_body.add_widget(_label(f"{nr} rows x {nc} columns. Double-click the table to edit it.",
                                          11, theme.MUTED, h=dp(34)))
        self._btn_row([("Edit cells...", lambda: self.edit_table(o)),
                       ("Paste data...", lambda: self.paste_dialog(o))])
        self._btn_row([("Import CSV...", lambda: self.import_csv(o)),
                       ("Export CSV...", lambda: self.export_csv(o))])
        st = self._col_row_inputs(o)
        self._btn_row([("Insert row below", lambda: self._table_do(o, st, "row+")),
                       ("Delete row", lambda: self._table_do(o, st, "row-"))])
        self._btn_row([("Insert col right", lambda: self._table_do(o, st, "col+")),
                       ("Delete column", lambda: self._table_do(o, st, "col-"))])
        self._btn_row([("Sort column A-Z", lambda: self._table_do(o, st, "asc")),
                       ("Sort Z-A", lambda: self._table_do(o, st, "desc"))])

        def set_filter(txt):
            try:
                c = sd.parse_col(self._fields["t_col"].text)
            except ValueError as e:
                self._hint(str(e))
                return
            if txt != o["ftext"] or c != o["fcol"]:
                def do():
                    o["fcol"], o["ftext"] = (c, txt) if txt.strip() else (-1, "")
                self._edit(do)
        self._row("Show rows with", self._num_input("t_filter", o["ftext"], set_filter))
        self.panel_body.add_widget(_label("(looks in the Column above; empty shows all rows)", 10, theme.MUTED))
        self._btn_row([("Header row: " + ("on" if o["header"] else "off"), lambda: self._toggle(o, "header"))])
        self._num_prop("Font size", o, "size", 4, 200)
        self._color_row("Header fill", o, "hdr_bg")
        self._color_row("Header text", o, "hdr_fg")
        self._color_row("Cell fill", o, "cell_bg")
        self._color_row("Cell text", o, "cell_fg")
        self._color_row("Grid lines", o, "grid")
        users = [c for c in self.doc.objects if c["type"] == "chart" and c.get("source") == o["id"]]
        if users:
            self.panel_body.add_widget(_label(f"Feeds {len(users)} chart(s).", 11, theme.MUTED))
        self._btn_row([("Make a chart from this", lambda: self._chart_from(o))])

    def _chart_from(self, t):
        ch = sc.make("chart", x=t["x"] + t["w"] + 40, y=t["y"], source=t["id"],
                     value_cols=[1] if len(t["cells"][0]) > 1 else [0])
        ch["data"] = sd.chart_data(ch, t)

        def do():
            self.doc.add(ch)
            sc.assign_parent(self.doc, ch)
        self._edit(do)
        self.canvas_w.set_sel([ch["id"]])

    # ----- charts
    def _chart_props(self, o):
        kind = Spinner(text=o["kind"], values=sd.CHART_KINDS, size_hint_y=None, height=dp(32),
                       font_size=sp(12))
        kind.bind(text=lambda w, v: self._set(o, "kind", v))
        self._row("Type", kind, 32)
        tables = [t for t in self.doc.objects if t["type"] == "table"]
        names = {f"{t['name']} #{t['id']}": t["id"] for t in tables}
        cur = next((k for k, v in names.items() if v == o["source"]), "(own data)")
        src = Spinner(text=cur, values=["(own data)"] + list(names), size_hint_y=None, height=dp(32),
                      font_size=sp(12))

        def pick(w, v):
            new = names.get(v)
            if new == o["source"]:
                return

            def do():
                o["source"] = new
            self._edit(do)
        src.bind(text=pick)
        self._row("Data from", src, 32)
        title = TextInput(text=o["title"], multiline=False, font_size=sp(13), size_hint_y=None, height=dp(32))
        title.bind(on_text_validate=lambda w: self._set(o, "title", w.text),
                   focus=lambda w, f: (not f) and w.text != o["title"] and self._set(o, "title", w.text))
        self._row("Title", title)
        if o["source"] is not None and self.doc.get(o["source"]):
            def lab(txt):
                try:
                    c = sd.parse_col(txt)
                except ValueError as e:
                    self._hint(str(e))
                    return
                self._set(o, "label_col", c)

            def vals(txt):
                try:
                    cs = [sd.parse_col(p) for p in txt.replace(" ", "").split(",") if p]
                except ValueError as e:
                    self._hint(str(e))
                    return
                if cs and cs != o["value_cols"]:
                    self._set(o, "value_cols", cs[:sd.MAX_SERIES])
            self._row("Labels from", self._num_input("c_lab", sd.col_name(o["label_col"]), lab))
            self._row("Values from", self._num_input("c_vals", ",".join(sd.col_name(c) for c in o["value_cols"]), vals))
            self.panel_body.add_widget(_label("Columns use the table's letters, e.g. B,C", 10, theme.MUTED))
        else:
            self._btn_row([("Edit data...", lambda: self.paste_dialog(
                o, "Chart data (first column = labels)", self._apply_chart_cells))])
        self._btn_row([("Legend: " + ("on" if o["legend"] else "off"), lambda: self._toggle(o, "legend"))])
        self._color_row("Background", o, "bg")
        self._color_row("Text colour", o, "fg")

    def _apply_chart_cells(self, o, cells):
        header = cells[0]
        body = cells[1:] or cells
        labels = [r[0] for r in body]
        ncol = len(header)
        series = [[sd.num(r[c]) or 0.0 for r in body] for c in range(1, ncol)]
        names = [header[c] or f"Series {c}" for c in range(1, ncol)]
        if not series:
            self._hint("Add at least two columns: labels, then values.")
            return
        data = sd.clean_chart_data({"labels": labels, "names": names, "series": series})
        self._edit(lambda: (o.__setitem__("data", data), o.__setitem__("source", None)))

    # ------------------------------------------------------------ presentation and slide export
    def present(self):
        slides = se.slides(self.doc)
        if not slides:
            self._hint("Draw a frame first: every frame is a slide, in the order shown in Layers.")
            return
        show = SlideShow(self.doc, slides, se.start_index(self.doc, self.canvas_w.sel))
        self._popups += 1                    # keys belong to the slide show until it closes
        show.bind(on_dismiss=lambda *a: setattr(self, "_popups", max(0, self._popups - 1)))
        self._show = show
        show.open()

    def export_dialog(self):
        slides = se.slides(self.doc)
        if not slides:
            self._hint("Nothing to export: draw a frame first (each frame is a slide).")
            return
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        fmt = Spinner(text="PNG pictures", values=["PNG pictures", "PDF document"], size_hint_y=None,
                      height=dp(40))
        which = Spinner(text="All slides", values=["All slides", "Selected slide"], size_hint_y=None,
                        height=dp(40))
        scale = Spinner(text="1x", values=["1x", "2x", "3x"], size_hint_y=None, height=dp(40))
        out = _label(f"Saved in: {os.path.join(self._folder(), 'exports')}", 10, theme.MUTED, h=dp(34))
        go = Button(text="Export", size_hint_y=None, height=dp(44))
        for w in (fmt, which, scale, out, go):
            lay.add_widget(w)
        pop = self._popup("Export slides", lay, 0.9, dp(330))

        def run(*a):
            pop.dismiss()
            chosen = slides
            if which.text == "Selected slide":
                i = se.start_index(self.doc, self.canvas_w.sel)
                chosen = [slides[i]]
            self.export_slides(chosen, "pdf" if fmt.text.startswith("PDF") else "png",
                               float(scale.text[0]))
        go.bind(on_release=run)
        pop.open()

    def export_slides(self, frames, kind="png", scale=1.0):
        """Write the slides as PNG files (or one PDF) under <studio folder>/exports/<title>/."""
        import shutil
        import tempfile
        folder = os.path.join(self._folder(), "exports", se.file_stem(self.doc.settings["title"]))
        try:
            os.makedirs(folder, exist_ok=True)
            work = tempfile.mkdtemp() if kind == "pdf" else folder
            paths = []
            for n, fr in enumerate(frames, 1):
                p = os.path.join(work, f"slide-{n:02d}.png")
                render_slide_png(self.doc, fr, p, scale)
                paths.append(p)
            if kind == "pdf":
                target = se.images_to_pdf(paths, os.path.join(folder, se.file_stem(self.doc.settings["title"]) + ".pdf"))
                shutil.rmtree(work, ignore_errors=True)
            else:
                target = folder
        except (OSError, ValueError, ImportError) as e:
            self._hint(f"Could not export: {e}")
            return None
        self._hint(f"Exported {len(frames)} slide(s) to {target}")
        return target
