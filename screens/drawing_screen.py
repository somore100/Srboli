# screens/drawing_screen.py - Drawing: a simple sketchpad. Brush, eraser, line, rectangle,
# oval, colours, size, undo/redo, background, save as PNG. Logic: core/drawing_core.py.
import time

from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import app_data
from core import color_core
from core import drawing_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)
TOOL_LABELS = {"brush": "Brush", "eraser": "Eraser", "line": "Line", "rect": "Box", "oval": "Oval"}


class DrawCanvas(Widget):
    """Shows a Drawing and turns touches into strokes."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.drawing = core.Drawing()
        self.tool = "brush"
        self.color = (0, 0, 0)
        self.brush = 6
        self.filled = False
        self.on_change = lambda: None
        self._touch = None
        self.bind(pos=self.redraw, size=self.redraw)

    # coordinates: widget (y up) <-> picture (y down from the top)
    def to_pic(self, x, y):
        return (x - self.x, self.height - (y - self.y))

    def to_widget(self, px, py):
        return (self.x + px, self.y + self.height - py)

    def redraw(self, *a):
        self.drawing.size = (max(1, int(self.width)), max(1, int(self.height)))
        self.canvas.clear()
        with self.canvas:
            Color(*(v / 255 for v in self.drawing.bg), 1)
            Rectangle(pos=self.pos, size=self.size)
            for s in self.drawing.visible():
                self._paint(s)
            if self.drawing.live:
                self._paint(self.drawing.live)

    def _paint(self, s):
        col = self.drawing.bg if s["color"] is None else s["color"]
        Color(*(v / 255 for v in col), 1)
        w = s["width"]
        pts = s["points"]
        wp = [c for p in pts for c in self.to_widget(*p)]
        t = s["tool"]
        if t in ("brush", "eraser", "line"):
            if len(pts) > 1:
                Line(points=wp, width=w, cap="round", joint="round")
            x, y = wp[0], wp[1]
            Ellipse(pos=(x - w / 2, y - w / 2), size=(w, w))
            if len(pts) > 1:
                Ellipse(pos=(wp[-2] - w / 2, wp[-1] - w / 2), size=(w, w))
        elif len(pts) > 1:
            (x0, y0), (x1, y1) = pts
            x, y = min(x0, x1), min(y0, y1)
            bw, bh = abs(x1 - x0), abs(y1 - y0)
            wx, wy = self.to_widget(x, y + bh)       # lower-left in widget space
            if s["filled"]:
                (Rectangle if t == "rect" else Ellipse)(pos=(wx, wy), size=(bw, bh))
            elif t == "rect":
                Line(rectangle=(wx, wy, bw, bh), width=w, joint="miter")
            else:
                Line(ellipse=(wx, wy, bw, bh), width=w)

    # ----- touches -----
    def on_touch_down(self, touch):
        if self._touch is not None or not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        self._touch = touch
        touch.grab(self)
        self.drawing.begin(self.tool, self.color, self.brush, self.filled,
                           self.to_pic(*touch.pos))
        self.redraw()
        return True

    def on_touch_move(self, touch):
        if touch is self._touch:
            self.drawing.move(self.to_pic(*touch.pos))
            self.redraw()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch is self._touch:
            touch.ungrab(self)
            self._touch = None
            self.drawing.end()
            self.redraw()
            self.on_change()
            return True
        return super().on_touch_up(touch)


class DrawingScreen(ToolScreen):
    title = "Drawing"

    def __init__(self, **kw):
        super().__init__(**kw)
        tools = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(3))
        self.tool_btns = {}
        for t in core.TOOLS:
            b = Button(text=TOOL_LABELS[t], font_size=sp(12))
            b.bind(on_release=lambda *a, k=t: self.set_tool(k))
            tools.add_widget(b)
            self.tool_btns[t] = b
        self.fill_btn = Button(text="Fill: off", font_size=sp(12))
        self.fill_btn.bind(on_release=lambda *a: self.toggle_fill())
        tools.add_widget(self.fill_btn)
        self.body.add_widget(tools)

        cols = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(3))
        self.swatches = []
        for h in core.PALETTE:
            b = Button(text="", background_normal="",
                       background_color=(*(v / 255 for v in core.hex_rgb(h)), 1))
            b.bind(on_release=lambda *a, c=h: self.set_color(core.hex_rgb(c)))
            cols.add_widget(b)
            self.swatches.append(b)
        more = Button(text="...", size_hint_x=None, width=dp(40), font_size=sp(14))
        more.bind(on_release=lambda *a: self.custom_color())
        cols.add_widget(more)
        self.body.add_widget(cols)

        size_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self.size_label = Label(text="", font_size=sp(12), size_hint_x=None, width=dp(70))
        self.size_slider = Slider(min=core.MIN_WIDTH, max=40, step=1, value=6)
        self.size_slider.bind(value=lambda *a: self._sync_size())
        self.bg_sp = Spinner(text="White", values=list(core.BACKGROUNDS), font_size=sp(12),
                             size_hint_x=None, width=dp(90))
        self.bg_sp.bind(text=lambda *a: self.set_bg(self.bg_sp.text))
        size_row.add_widget(self.size_label)
        size_row.add_widget(self.size_slider)
        size_row.add_widget(self.bg_sp)
        self.body.add_widget(size_row)

        self.canvas_w = DrawCanvas()
        self.canvas_w.on_change = self._changed
        self.body.add_widget(self.canvas_w)

        act = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(3))
        self.undo_btn = Button(text="Undo", font_size=sp(13))
        self.redo_btn = Button(text="Redo", font_size=sp(13))
        clear = Button(text="Clear", font_size=sp(13))
        save = Button(text="Save PNG", font_size=sp(13))
        self.undo_btn.bind(on_release=lambda *a: self.undo())
        self.redo_btn.bind(on_release=lambda *a: self.redo())
        clear.bind(on_release=lambda *a: self.clear())
        save.bind(on_release=lambda *a: self.save())
        for b in (self.undo_btn, self.redo_btn, clear, save):
            act.add_widget(b)
        self.body.add_widget(act)
        self.status = Label(text="", font_size=sp(11), color=theme.MUTED, size_hint_y=None,
                            height=dp(30), halign="center", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.status)
        self.set_tool("brush")
        self._sync_size()
        self._sync_buttons()

    # ----- tools -----
    def set_tool(self, t):
        self.canvas_w.tool = t
        for k, b in self.tool_btns.items():
            b.background_color = theme.ACCENT if k == t else OFF

    def toggle_fill(self):
        self.canvas_w.filled = not self.canvas_w.filled
        self.fill_btn.text = "Fill: on" if self.canvas_w.filled else "Fill: off"

    def set_color(self, rgb):
        self.canvas_w.color = tuple(rgb)
        if self.canvas_w.tool == "eraser":
            self.set_tool("brush")

    def custom_color(self):
        inp = TextInput(text="#", multiline=False, size_hint_y=None, height=dp(40),
                        font_size=sp(16))
        ok = Button(text="Use this colour", size_hint_y=None, height=dp(44))
        msg = Label(text="Type #RRGGBB or rgb(1, 2, 3)", size_hint_y=None, height=dp(24),
                    font_size=sp(11), color=theme.MUTED)
        lay = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        for w in (msg, inp, ok):
            lay.add_widget(w)
        pop = Popup(title="Custom colour", content=lay, size_hint=(0.85, None), height=dp(220))

        def use(*a):
            c = color_core.parse_color(inp.text)
            if c:
                pop.dismiss()
                self.set_color(c)
            else:
                msg.text = "Not a colour."

        ok.bind(on_release=use)
        pop.open()

    def _sync_size(self):
        self.canvas_w.brush = int(self.size_slider.value)
        self.size_label.text = f"Size {int(self.size_slider.value)}"

    def set_bg(self, name):
        self.canvas_w.drawing.set_background(core.BACKGROUNDS[name])
        self.canvas_w.redraw()

    # ----- history -----
    def undo(self):
        self.canvas_w.drawing.undo()
        self.canvas_w.redraw()
        self._sync_buttons()

    def redo(self):
        self.canvas_w.drawing.redo()
        self.canvas_w.redraw()
        self._sync_buttons()

    def clear(self):
        if not self.canvas_w.drawing.is_empty():
            self.canvas_w.drawing.clear()
            self.canvas_w.redraw()
            self.status.text = "Cleared. Undo brings it back."
            self._sync_buttons()

    def _changed(self):
        self._sync_buttons()

    def _sync_buttons(self):
        d = self.canvas_w.drawing
        self.undo_btn.disabled = not d.strokes
        self.redo_btn.disabled = not d.redo_list

    def save(self):
        d = self.canvas_w.drawing
        if d.is_empty():
            self.status.text = "Nothing drawn yet."
            return
        try:
            import os
            path = d.save(os.path.join(app_data.subdir("drawings"),
                                       time.strftime("drawing-%Y%m%d-%H%M%S.png")))
            self.status.text = f"Saved: {path}"
            self.status.color = theme.SUCCESS
        except Exception as e:
            self.status.text = f"Could not save: {e}"
            self.status.color = theme.DANGER
