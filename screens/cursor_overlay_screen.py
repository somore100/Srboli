# screens/cursor_overlay_screen.py - Cursor Overlay: a ring / dot / crosshair / square /
# arrow that follows the mouse pointer on screen (for presentations and recordings), with
# your colour, size, thickness and see-through level, and a flash while a button is held.
# Windows for now: the overlay is its own process (core/cursor_app.py, `Srboli --cursor`).
# Settings are saved and a running overlay picks changes up within a moment.
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, Triangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from core import color_core
from core import cursor_core as core
from core import drawing_core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)


def _row(h=38):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))


class Preview(Widget):
    """Shows the chosen shape on a mid-grey background, the way the overlay will draw it."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cfg = core.clean({})
        self.bind(pos=self.redraw, size=self.redraw)

    def set_cfg(self, cfg):
        self.cfg = cfg
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        cfg = self.cfg
        n = core.canvas_size(cfg)
        k = min(self.width, self.height) / (n * 1.4) if n else 1
        ox = self.x + (self.width - n * k) / 2
        oy = self.y + (self.height + n * k) / 2          # top of the shape box (y down -> up)
        rgb = tuple(int(cfg["color"][i:i + 2], 16) / 255 for i in (1, 3, 5))
        with self.canvas:
            Color(0.32, 0.34, 0.38, 1)
            Rectangle(pos=self.pos, size=self.size)
            Color(*rgb, cfg["opacity"])
            w = max(1, cfg["thickness"] * k)
            for it in core.shape_items(cfg):
                kind = it[0]
                if kind in ("oval", "rect"):
                    _, x0, y0, x1, y1, filled = it
                    bx, by, bw, bh = ox + x0 * k, oy - y1 * k, (x1 - x0) * k, (y1 - y0) * k
                    if filled:
                        (Ellipse if kind == "oval" else Rectangle)(pos=(bx, by), size=(bw, bh))
                    elif kind == "oval":
                        Line(ellipse=(bx, by, bw, bh), width=w)
                    else:
                        Line(rectangle=(bx, by, bw, bh), width=w)
                elif kind == "line":
                    Line(points=[ox + it[1] * k, oy - it[2] * k, ox + it[3] * k, oy - it[4] * k],
                         width=w, cap="round")
                else:
                    pts = [(ox + x * k, oy - y * k) for x, y in it[1]]
                    self._fan(pts)

    @staticmethod
    def _fan(pts):
        # the arrow outline is concave: draw it as triangles from the tip, which is enough here
        # for a preview (the real overlay fills the exact polygon)
        a = pts[0]
        for b, c in zip(pts[1:], pts[2:]):
            Triangle(points=[*a, *b, *c])


class CursorOverlayScreen(ToolScreen):
    title = "Cursor Overlay"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.cfg = core.load()
        self._loading = False
        self.info = Label(text="", font_size=sp(12), color=theme.MUTED, size_hint_y=None,
                          height=dp(44), halign="left", valign="middle")
        self.info.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.info)
        self.preview = Preview()
        self.body.add_widget(self.preview)

        row = _row(46)
        self.run_btn = Button(text="Start overlay", font_size=sp(14))
        self.run_btn.bind(on_release=lambda *a: self.toggle_run())
        self.show_btn = Button(text="Hide", font_size=sp(14), size_hint_x=0.4)
        self.show_btn.bind(on_release=lambda *a: self.toggle_visible())
        row.add_widget(self.run_btn)
        row.add_widget(self.show_btn)
        self.body.add_widget(row)

        row = _row()
        self.shape_sp = Spinner(text=core.SHAPES[self.cfg["shape"]], values=list(core.SHAPES.values()),
                                font_size=sp(13))
        self.shape_sp.bind(text=lambda *a: self._changed())
        self.flash_btn = Button(font_size=sp(12))
        self.flash_btn.bind(on_release=lambda *a: self.toggle_flash())
        row.add_widget(self.shape_sp)
        row.add_widget(self.flash_btn)
        self.body.add_widget(row)

        row = _row(36)
        for h in drawing_core.PALETTE:
            b = Button(text="", background_normal="",
                       background_color=(*(v / 255 for v in drawing_core.hex_rgb(h)), 1))
            b.bind(on_release=lambda *a, c=h: self.set_color(c))
            row.add_widget(b)
        self.body.add_widget(row)
        self.hex_in = TextInput(text=self.cfg["color"], multiline=False, size_hint_y=None,
                                height=dp(38), font_size=sp(14), hint_text="#RRGGBB")
        self.hex_in.bind(on_text_validate=lambda *a: self._hex())
        self.body.add_widget(self.hex_in)

        self.sliders = {}
        for key, label, lo, hi, step in (("size", "Size", 16, 200, 1), ("thickness", "Thickness", 1, 16, 1),
                                         ("opacity", "See-through", 20, 100, 1)):
            r = _row(34)
            lb = Label(text=label, size_hint_x=None, width=dp(92), font_size=sp(12))
            sl = Slider(min=lo, max=hi, step=step,
                        value=self.cfg[key] if key != "opacity" else self.cfg[key] * 100)
            sl.bind(value=lambda *a: self._changed())
            r.add_widget(lb)
            r.add_widget(sl)
            self.sliders[key] = sl
            self.body.add_widget(r)
        self.status = Label(text="", font_size=sp(11), color=theme.MUTED, size_hint_y=None,
                            height=dp(28))
        self.body.add_widget(self.status)
        self._sync()
        Clock.schedule_interval(lambda dt: self._poll(), 1.5)

    # ----- settings -----
    def _read(self):
        shape = next((k for k, v in core.SHAPES.items() if v == self.shape_sp.text), "ring")
        cfg = dict(self.cfg)
        cfg.update(shape=shape, size=int(self.sliders["size"].value),
                   thickness=int(self.sliders["thickness"].value),
                   opacity=self.sliders["opacity"].value / 100)
        return core.clean(cfg)

    def _changed(self):
        if self._loading:
            return
        self.cfg = self._read()
        self._save()
        self._sync()

    def set_color(self, h):
        self.cfg["color"] = h
        self.hex_in.text = h
        self._changed()

    def _hex(self):
        c = color_core.parse_color(self.hex_in.text)
        if c:
            self.set_color(color_core.to_hex(c))
        else:
            self.status.text = "Not a colour. Try #RRGGBB."

    def toggle_flash(self):
        self.cfg["click_flash"] = not self.cfg["click_flash"]
        self._changed()

    def toggle_visible(self):
        self.cfg["visible"] = not self.cfg["visible"]
        self._changed()

    def _save(self):
        try:
            core.save(self.cfg)
        except Exception as e:
            self.status.text = f"Could not save: {e}"

    # ----- running -----
    def toggle_run(self):
        if core.is_running():
            core.stop()
            self.status.text = "Stopping..."
        else:
            ok, msg = core.start()
            self.status.text = msg
        Clock.schedule_once(lambda dt: self._poll(), 1.5)

    def _poll(self):
        running = core.is_running()
        self.run_btn.text = "Stop overlay" if running else "Start overlay"
        self.run_btn.background_color = theme.DANGER if running else theme.ACCENT
        if running and self.status.text in ("Stopping...", "Started."):
            self.status.text = ""

    def _sync(self):
        self.preview.set_cfg(self.cfg)
        self.flash_btn.text = "Flash on click: " + ("on" if self.cfg["click_flash"] else "off")
        self.flash_btn.background_color = theme.ACCENT if self.cfg["click_flash"] else OFF
        self.show_btn.text = "Hide" if self.cfg["visible"] else "Show"
        if not core.supported():
            self.info.text = ("The overlay itself works on Windows for now (Linux desktops can't "
                              "give a window that clicks pass through, Wayland also hides the "
                              "pointer position). You can still try the look here.")
            self.run_btn.disabled = True
        else:
            self.info.text = ("A marker that follows your mouse pointer, on top of everything. "
                              "Changes apply to a running overlay within a moment.")
            self.run_btn.disabled = False

    def on_pre_enter(self, *a):
        self._poll()
