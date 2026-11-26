# screens/overlay_sandbox_screen.py - a simulated phone screen for trying Srboli's floating tools:
# a master bubble with a radial menu, a calculator bubble, a recorder bubble (simulated) and the
# click/drag macro tool. The real system-wide overlays need an Android service and the overlay
# permission; everything here runs inside the app, so it works unsigned and on desktop too.
import math

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

import app_data
from core import calc_core
from core import macro_core as mc
from core import theme

FOLDER = "macros"
LONG_PRESS_MS = 400
PERMISSIONS_HELP = (
    "[b]Why this matters[/b]\n"
    "This sandbox needs no permission. The real floating bubble, the macro tool and the screen "
    "recorder will need Android's \"Display over other apps\", and the macro tool also needs "
    "Accessibility (that is what lets it tap and drag for you).\n\n"
    "[b]If Android says the setting is restricted[/b] (apps installed from a file, not a store):\n"
    "1. Try to switch the permission on once, so Android notes the attempt.\n"
    "2. Open Settings > Apps > Srboli.\n"
    "3. Tap the three dots (top right) and choose [b]Allow restricted settings[/b].\n"
    "4. Confirm with your fingerprint or PIN, then go back and switch the permission on.\n\n"
    "[b]Display over other apps:[/b] Settings > Apps > Srboli > Display over other apps "
    "(sometimes under Special access).\n"
    "[b]Accessibility:[/b] Settings > Accessibility > Installed apps > Srboli.\n\n"
    "Menus differ a little between phone brands. You can switch either permission off again "
    "at any time in the same place.")
BLUE = (0.25, 0.55, 1.0)
GREEN = (0.2, 0.8, 0.4)
ORANGE = (1.0, 0.55, 0.15)
RED = (0.9, 0.25, 0.25)
CALC_KEYS = [["C", "<", "%", "/"], ["sqrt", "x2", "1/x", "*"], ["7", "8", "9", "-"],
             ["4", "5", "6", "+"], ["+/-", "0", ".", "="]]
SHOW = {"/": "÷", "*": "×", "-": "−", "<": "Del", "sqrt": "√", "x2": "x²"}
SPEEDS = ["0.5x", "1x", "2x", "3x"]


def _lab(text, size=12, color=(1, 1, 1, 1), **kw):
    lb = Label(text=text, font_size=sp(size), color=color, **kw)
    return lb


def _hit(center, r, touch):
    return (touch.x - center[0]) ** 2 + (touch.y - center[1]) ** 2 <= r * r


class Fx(Widget):
    """Ripples and drag trails; never takes touches."""

    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False

    def ripple(self, x, y, hold_ms=0, color=ORANGE):
        """A tap ring; for a long press it stays solid under the finger for the whole hold."""
        r, d = dp(10), 0.5
        with self.canvas:
            c = Color(*color, 0.8)
            e = Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))
        big = dp(30)
        a = Animation(size=(2 * big, 2 * big), pos=(x - big, y - big), d=d)
        fade = Animation(a=0, d=d)
        if hold_ms > 0:
            fade = Animation(a=0.8, d=hold_ms / 1000.0) + fade      # held: no fading until released
        fade.start(c)
        a.bind(on_complete=lambda *_: None)
        fade.bind(on_complete=lambda *_: self._drop(c, e))
        a.start(e)

    def trail(self, x, y, x2, y2, dur):
        """The finger: a dot that travels from start to end over the drag time, with its path."""
        d = max(0.15, dur)
        r = dp(11)
        with self.canvas:
            c = Color(*ORANGE, 0.35)
            ln = Line(points=[x, y, x2, y2], width=dp(3))
            c2 = Color(*ORANGE, 0.9)
            dot = Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))
        move = Animation(pos=(x2 - r, y2 - r), d=d)
        fade = Animation(a=0.35, d=d) + Animation(a=0, d=0.3)
        fade.bind(on_complete=lambda *_: self._drop(c, ln, c2, dot))
        move.start(dot)
        fade.start(c)

    def _drop(self, *items):
        for i in items:
            try:
                self.canvas.remove(i)
            except ValueError:
                pass


class Targets(Widget):
    """The fake apps behind the overlays: six tap tiles and a slider chip to drag."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.counts = [0] * 6
        self.holds = [0] * 6
        self._anim = None
        self._drag = None
        self._grab_dx = 0
        self.flash = -1
        self.chip_f = 0.1
        self.grab_chip = False
        self.labels = [_lab("", 15) for _ in range(6)]
        self.status = _lab("Tap the tiles or drag the chip", 11, theme.MUTED)
        for lb in self.labels + [self.status]:
            self.add_widget(lb)
        self.bind(pos=self.redraw, size=self.redraw)

    def tile_rects(self):
        pad, gap = dp(10), dp(8)
        w = (self.width - 2 * pad - 2 * gap) / 3
        h = min(dp(90), (self.height * 0.5 - gap) / 2)
        top = self.top - dp(10) - h
        return [(self.x + pad + c * (w + gap), top - r * (h + gap), w, h)
                for r in range(2) for c in range(3)]

    def track(self):
        t = self.tile_rects()[-1]
        return (self.x + dp(24), t[1] - dp(70), self.width - dp(48), dp(14))

    def chip_rect(self):
        x, y, w, h = self.track()
        cw = dp(54)
        return (x + self.chip_f * (w - cw), y - dp(8), cw, h + dp(16))

    def redraw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(0.10, 0.13, 0.20, 1)
            Rectangle(pos=self.pos, size=self.size)
            for i, (x, y, w, h) in enumerate(self.tile_rects()):
                Color(*(ORANGE if i == self.flash else (0.22, 0.30, 0.45)), 1)
                RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
                self.labels[i].text = (f"{chr(65 + i)}\n{self.counts[i]}"
                                       + (f"  (held {self.holds[i]})" if self.holds[i] else ""))
                self.labels[i].size = (w, h)
                self.labels[i].pos = (x, y)
            x, y, w, h = self.track()
            Color(0.25, 0.28, 0.35, 1)
            RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(7)])
            cx, cy, cw, ch = self.chip_rect()
            Color(*GREEN, 1)
            RoundedRectangle(pos=(cx, cy), size=(cw, ch), radius=[dp(8)])
        self.status.size = (self.width, dp(24))
        self.status.pos = (self.x, self.y + dp(70))

    def reset(self):
        self.finish_drag(go=False)
        self.counts, self.holds, self.flash, self.chip_f = [0] * 6, [0] * 6, -1, 0.1
        self.status.text = "Tap the tiles or drag the chip"
        self.redraw()

    def _tile_at(self, x, y):
        for i, (tx, ty, w, h) in enumerate(self.tile_rects()):
            if tx <= x <= tx + w and ty <= y <= ty + h:
                return i
        return None

    def _on_chip(self, x, y):
        cx, cy, w, h = self.chip_rect()
        return cx <= x <= cx + w and cy <= y <= cy + h

    def tap(self, x, y, hold_ms=0):
        i = self._tile_at(x, y)
        if i is not None:
            self.flash = i
            if hold_ms >= LONG_PRESS_MS:
                self.holds[i] += 1
                self.status.text = f"Tile {chr(65 + i)} held for {int(hold_ms)} ms"
            else:
                self.counts[i] += 1
                self.status.text = f"Tile {chr(65 + i)} tapped ({self.counts[i]})"
            Clock.schedule_once(self._unflash, 0.2)
        else:
            self.status.text = "Tapped empty space"
        self.redraw()
        return i

    def _unflash(self, dt):
        self.flash = -1
        self.redraw()

    def drag(self, x, y, x2, y2, dur_ms=0):
        """True when the drag started on the chip. The chip then follows the finger from the
        start to the end over dur_ms, like a real swipe (not a jump)."""
        self.finish_drag(go=False)
        if not self._on_chip(x, y):
            self.status.text = "Dragged on empty space"
            return False
        self._grab_dx = self.chip_rect()[0] + self.chip_rect()[2] / 2 - x
        self._drag = (x, x2, 0.0, max(1.0, float(dur_ms)) / 1000.0)
        if dur_ms <= 0:
            self.finish_drag()
        else:
            self._anim = Clock.schedule_interval(self._step, 0)
        return True

    def _step(self, dt):
        x, x2, t, dur = self._drag
        t += dt
        self._drag = (x, x2, t, dur)
        p = min(1.0, t / dur)
        self.set_chip(x + (x2 - x) * p + self._grab_dx - self._chip_half())
        if p >= 1.0:
            self.finish_drag(go=False)
            return False

    def _chip_half(self):
        return self.chip_rect()[2] / 2

    def finish_drag(self, go=True):
        """Stop an animated drag; with go=True jump to where it was heading."""
        if self._anim is not None:
            self._anim.cancel()
            self._anim = None
        if go and self._drag:
            self.set_chip(self._drag[1] + self._grab_dx - self._chip_half())
        self._drag = None

    def set_chip(self, x):
        """Put the chip's left edge at screen x (clamped to the track)."""
        tx, ty, w, h = self.track()
        self.chip_f = max(0.0, min(1.0, (x - tx) / max(1, w - dp(54))))
        self.status.text = f"Chip moved to {int(self.chip_f * 100)}%"
        self.redraw()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if self._on_chip(*touch.pos):
            self.grab_chip = True
            self.finish_drag(go=False)
            self._grab_dx = 0
        else:
            self.tap(*touch.pos)
        return True

    def on_touch_move(self, touch):
        if self.grab_chip:
            self.set_chip(touch.x - self._chip_half())
            return True
        return False

    def on_touch_up(self, touch):
        was, self.grab_chip = self.grab_chip, False
        return was


class Chip(Widget):
    """A round button used by the radial menu and the dismiss target."""

    def __init__(self, text, color, cb=None, radius=dp(24), **kw):
        super().__init__(**kw)
        self.r, self.cb, self.color, self.hot = radius, cb, color, False
        self.size = (2 * radius, 2 * radius)
        self.size_hint = (None, None)
        self.lab = _lab(text, 11, bold=True)
        self.add_widget(self.lab)
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.color, 0.95 if not self.hot else 1)
            Ellipse(pos=self.pos, size=self.size)
        self.lab.size, self.lab.pos = self.size, self.pos

    def on_touch_down(self, touch):
        if self.cb and _hit(self.center, self.r, touch):
            self.cb()
            return True
        return False


class Bubble(Widget):
    """A floating dot: tap it, drag it, snap to a side, or drop it on the X to dismiss it."""

    def __init__(self, sb, name, text, color, on_tap, fx=0.92, fy=0.7, radius=dp(26), **kw):
        super().__init__(**kw)
        self.sb, self.name, self.on_tap, self.color = sb, name, on_tap, color
        self.r, self.fx, self.fy = radius, fx, fy
        self.size_hint, self.size = (None, None), (2 * radius, 2 * radius)
        self.lab = _lab(text, 11, bold=True)
        self.add_widget(self.lab)
        self._down = None
        self.moved = False
        self.bind(pos=self.redraw, size=self.redraw)
        self.place()

    def set_text(self, text):
        self.lab.text = text

    def place(self):
        sb = self.sb
        x = sb.x + min(max(self.fx, 0), 1) * sb.width
        y = sb.y + min(max(self.fy, 0), 1) * sb.height
        x = min(max(x, sb.x + self.r), sb.right - self.r)
        y = min(max(y, sb.y + self.r), sb.top - self.r)
        self.center = (x, y)

    def redraw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 0.3)
            Ellipse(pos=(self.x + dp(2), self.y - dp(2)), size=self.size)
            Color(*self.color, 1)
            Ellipse(pos=self.pos, size=self.size)
        self.lab.size, self.lab.pos = self.size, self.pos

    def on_touch_down(self, touch):
        if not _hit(self.center, self.r, touch):
            return False
        touch.grab(self)
        self._down, self.moved = touch.pos, False
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if not self.moved and math.hypot(touch.x - self._down[0], touch.y - self._down[1]) > dp(8):
            self.moved = True
            self.sb.close_menu()
            self.sb.show_x(True)
        if self.moved:
            self.fx = (touch.x - self.sb.x) / max(1, self.sb.width)
            self.fy = (touch.y - self.sb.y) / max(1, self.sb.height)
            self.place()
            self.sb.x_hover(self.center)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if self.moved:
            over = self.sb.x_hover(self.center)
            self.sb.show_x(False)
            if over:
                self.sb.dismiss_bubble(self.name)
            else:
                self.fx = 0.05 if self.fx < 0.5 else 0.95
                self.place()
        else:
            self.on_tap()
        return True


class XTarget(Chip):
    pass


class CalcPanel(BoxLayout):
    """The calculator overlay: a small panel that can be dragged by its title and closed."""

    def __init__(self, sb, **kw):
        super().__init__(orientation="vertical", size_hint=(None, None), spacing=dp(3),
                         padding=dp(6), **kw)
        self.sb, self.calc = sb, calc_core.Calc()
        self.size = (dp(250), dp(360))
        head = BoxLayout(size_hint_y=None, height=dp(30))
        self.title = _lab("Calculator", 12, bold=True, halign="left")
        self.title.bind(size=lambda w, s: setattr(w, "text_size", s))
        head.add_widget(self.title)
        close = Button(text="X", size_hint_x=None, width=dp(34))
        close.bind(on_release=lambda *_: sb.close_calc())
        head.add_widget(close)
        self.add_widget(head)
        self.expr = _lab("", 11, theme.MUTED, size_hint_y=None, height=dp(18), halign="right")
        self.expr.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.disp = _lab("0", 26, size_hint_y=None, height=dp(48), halign="right")
        self.disp.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self.expr)
        self.add_widget(self.disp)
        grid = GridLayout(cols=4, spacing=dp(3))
        for row in CALC_KEYS:
            for k in row:
                b = Button(text=SHOW.get(k, k), font_size=sp(15))
                b.bind(on_release=lambda w, k=k: self.press(k))
                grid.add_widget(b)
        self.add_widget(grid)
        self._drag = None
        self.bind(pos=self.redraw, size=self.redraw)
        self.refresh()

    def redraw(self, *a):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.1, 0.11, 0.14, 0.97)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])

    def press(self, k):
        c = self.calc
        if k == "C":
            c.clear()
        elif k == "<":
            c.back()
        elif k == "%":
            c.percent()
        elif k == "sqrt":
            c.sqrt()
        elif k == "x2":
            c.square()
        elif k == "1/x":
            c.inverse()
        elif k == "+/-":
            c.negate()
        elif k == "=":
            c.equals()
        elif k in "+-*/":
            c.op(k)
        else:
            c.digit(k)
        self.refresh()

    def refresh(self):
        shown = self.calc.expr
        for a, b in (("*", "×"), ("/", "÷"), ("-", "−")):
            shown = shown.replace(a, b)
        self.expr.text = shown
        self.disp.text = self.calc.entry

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if touch.y > self.top - dp(36) and touch.x < self.right - dp(44):
            touch.grab(self)
            self._drag = (touch.x - self.x, touch.y - self.y)
            return True
        super().on_touch_down(touch)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self and self._drag:
            sb = self.sb
            self.x = min(max(touch.x - self._drag[0], sb.x), sb.right - self.width)
            self.y = min(max(touch.y - self._drag[1], sb.y), sb.top - self.height)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self._drag = None
            return True
        return super().on_touch_up(touch)


class Marker(Widget):
    """A numbered crosshair the macro will tap (or start/end a drag at)."""

    def __init__(self, ov, idx, kind, **kw):
        super().__init__(**kw)
        self.ov, self.idx, self.kind = ov, idx, kind
        self.r = dp(23)
        self.size_hint, self.size = (None, None), (2 * self.r, 2 * self.r)
        self.lab = _lab(str(idx + 1), 13, bold=True)
        self.add_widget(self.lab)
        self._down, self.moved = None, False
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *a):
        col = GREEN if self.ov.is_active(self.idx) else BLUE
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*col, 0.35)
            Ellipse(pos=self.pos, size=self.size)
            Color(*col, 1)
            Line(circle=(self.x + self.r, self.y + self.r, self.r), width=dp(2))
            cx, cy = self.x + self.r, self.y + self.r
            Line(points=[cx - self.r * 1.25, cy, cx - self.r * 0.55, cy], width=dp(1.5))
            Line(points=[cx + self.r * 0.55, cy, cx + self.r * 1.25, cy], width=dp(1.5))
        self.lab.size, self.lab.pos = self.size, self.pos

    def on_touch_down(self, touch):
        if self.ov.running or not _hit(self.center, self.r, touch):
            return False
        touch.grab(self)
        self._down, self.moved = touch.pos, False
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if not self.moved and math.hypot(touch.x - self._down[0], touch.y - self._down[1]) > dp(6):
            self.moved = True
        if self.moved:
            self.center = (touch.x, touch.y)
            self.ov.marker_moved(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if not self.moved:
            self.ov.edit(self.idx)
        return True


class MacroOverlay(Widget):
    """The macro tool: toolbar on the right, markers on the screen, settings you can minimise."""

    def __init__(self, sb, macro=None, **kw):
        super().__init__(**kw)
        self.sb = sb
        self.macro = macro or mc.Macro("My macro")
        self.running = self.hidden = False
        self.active_idx = None            # the action being performed right now (lights up)
        self._flash_ev = None
        self.settings_open = False
        self.popup = None
        self._handles = []
        self.markers = []
        self.pos, self.size = sb.pos, sb.size
        sb.bind(pos=self._sync, size=self._sync)

        self.toolbar = BoxLayout(orientation="vertical", size_hint=(None, None),
                                 size=(dp(64), dp(8 * 31 + 7 * 3 + 10)), spacing=dp(3), padding=dp(4))
        self.btn = {}
        for key, text, fn in (("run", "Run", self.toggle_run), ("click", "+ Click", self.add_click),
                              ("drag", "+ Drag", self.add_drag), ("undo", "- Last", self.remove_last),
                              ("save", "Save", self.save), ("eye", "Hide", self.toggle_hidden),
                              ("set", "Settings", self.toggle_settings), ("quit", "Quit", self.quit)):
            b = Button(text=text, font_size=sp(10.5))
            b.bind(on_release=lambda w, fn=fn: fn())
            self.btn[key] = b
            self.toolbar.add_widget(b)
        self.toolbar.bind(pos=self._bg, size=self._bg)
        self.add_widget(self.toolbar)

        self.panel = BoxLayout(orientation="vertical", size_hint=(None, None),
                               size=(dp(190), dp(172)), spacing=dp(3), padding=dp(5))
        top = BoxLayout(size_hint_y=None, height=dp(26))
        top.add_widget(_lab("Macro settings", 11, bold=True))
        mini = Button(text="Minimise", font_size=sp(10), size_hint_x=None, width=dp(64))
        mini.bind(on_release=lambda *_: self.toggle_settings())
        top.add_widget(mini)
        self.panel.add_widget(top)
        self.name_in = TextInput(text=self.macro.name, multiline=False, size_hint_y=None, height=dp(28), font_size=sp(12))
        self.loops_in = TextInput(text=str(self.macro.loops), multiline=False, input_filter="int",
                                  size_hint_y=None, height=dp(28), font_size=sp(12))
        self.speed_sp = Spinner(text="1x", values=SPEEDS, size_hint_y=None, height=dp(28), font_size=sp(12))
        self.name_in.bind(text=lambda w, v: setattr(self.macro, "name", v[:60] or "Macro"))
        self.loops_in.bind(text=lambda w, v: self.macro.set_loops(v))
        self.speed_sp.bind(text=lambda w, v: self.macro.set_speed(float(v[:-1])))
        for caption, w in (("Name", self.name_in), ("Repeat (0 = until stopped)", self.loops_in),
                           ("Speed", self.speed_sp)):
            self.panel.add_widget(_lab(caption, 9, theme.MUTED, size_hint_y=None, height=dp(12), halign="left"))
            self.panel.add_widget(w)
        opn = Button(text="Open saved...", size_hint_y=None, height=dp(28), font_size=sp(11))
        opn.bind(on_release=lambda *_: self.open_saved())
        self.panel.add_widget(opn)
        self.panel.bind(pos=self._bg, size=self._bg)
        self._layout()
        self.rebuild()

    # -- layout ------------------------------------------------------------------------------
    def _sync(self, *a):
        self.pos, self.size = self.sb.pos, self.sb.size
        self._layout()
        self.place_markers()

    def _layout(self):
        self.toolbar.pos = (self.right - self.toolbar.width - dp(6), self.center_y - self.toolbar.height / 2)
        self.panel.pos = (self.toolbar.x - self.panel.width - dp(6), self.center_y - self.panel.height / 2)
        if self.settings_open and self.panel.parent is None:
            self.add_widget(self.panel)
        elif not self.settings_open and self.panel.parent is not None:
            self.remove_widget(self.panel)

    def _bg(self, w, *a):
        w.canvas.before.clear()
        with w.canvas.before:
            Color(0.1, 0.11, 0.14, 0.93)
            RoundedRectangle(pos=w.pos, size=w.size, radius=[dp(12)])

    def center_of(self, x, y):
        return (self.sb.x + x * self.sb.width, self.sb.y + y * self.sb.height)

    def frac_of(self, cx, cy):
        return ((cx - self.sb.x) / max(1, self.sb.width), (cy - self.sb.y) / max(1, self.sb.height))

    # -- markers -----------------------------------------------------------------------------
    def rebuild(self):
        for m in self.markers:
            self.remove_widget(m)
        self.markers = []
        for i, a in enumerate(self.macro.actions):
            self.markers.append(Marker(self, i, "start" if a["kind"] == "drag" else "click"))
            if a["kind"] == "drag":
                self.markers.append(Marker(self, i, "end"))
        for m in self.markers:
            m.opacity = 0 if self.hidden else 1
            self.add_widget(m)
        self.place_markers()

    def place_markers(self):
        for m in self.markers:
            a = self.macro.actions[m.idx]
            m.center = self.center_of(a["x2"], a["y2"]) if m.kind == "end" else self.center_of(a["x"], a["y"])
        self.draw_bars()

    def marker_moved(self, m):
        fx, fy = self.frac_of(*m.center)
        self.macro.update(m.idx, **({"x2": fx, "y2": fy} if m.kind == "end" else {"x": fx, "y": fy}))
        self.draw_bars()

    def draw_bars(self):
        self.canvas.before.clear()
        if self.hidden:
            return
        with self.canvas.before:
            for i, a in enumerate(self.macro.actions):
                if a["kind"] != "drag":
                    continue
                col = GREEN if self.is_active(i) else BLUE
                x, y = self.center_of(a["x"], a["y"])
                x2, y2 = self.center_of(a["x2"], a["y2"])
                Color(*col, 0.55)
                Line(points=[x, y, x2, y2], width=dp(4))
                L = math.hypot(x2 - x, y2 - y)
                if L < dp(70):
                    continue
                ux, uy = (x2 - x) / L, (y2 - y) / L
                s = dp(5)
                Color(1, 1, 1, 0.9)
                d = dp(34)
                while d < L - dp(30):
                    px, py = x + ux * d, y + uy * d
                    Line(points=[px - ux * s - uy * s, py - uy * s + ux * s, px + ux * s * 0.6, py + uy * s * 0.6,
                                 px - ux * s + uy * s, py - uy * s - ux * s], width=dp(1.5))
                    d += dp(34)

    def is_active(self, i):
        return self.running and self.active_idx == i

    def _recolor(self):
        for m in self.markers:
            m.redraw()
        self.draw_bars()
        self.btn["run"].text = "Stop" if self.running else "Run"

    # -- toolbar actions ---------------------------------------------------------------------
    def _slot(self, kind):
        n = len(self.macro.actions)
        return 0.3 + 0.1 * (n % 5), 0.35 + 0.08 * (n % 4)

    def add_click(self):
        if self.running:
            return None
        x, y = self._slot("click")
        i = self.macro.add_click(x, y)
        if i is None:
            self.sb.say("Action limit reached")
        self.rebuild()
        return i

    def add_drag(self):
        if self.running:
            return None
        x, y = self._slot("drag")
        i = self.macro.add_drag(x, y, min(0.95, x + 0.3), y)
        if i is None:
            self.sb.say("Action limit reached")
        self.rebuild()
        return i

    def remove_last(self):
        if not self.running:
            self.macro.remove_last()
            self.rebuild()

    def toggle_hidden(self):
        self.hidden = not self.hidden
        self.btn["eye"].text = "Show" if self.hidden else "Hide"
        for m in self.markers:
            m.opacity = 0 if self.hidden else 1
        self.draw_bars()

    def toggle_settings(self):
        self.settings_open = not self.settings_open
        self._layout()

    def save(self):
        try:
            path = mc.save(self.macro, self.sb.folder_fn())
        except OSError as e:
            self.sb.say(f"Could not save: {e}")
            return None
        self.sb.say(f"Saved {path.rsplit('/', 1)[-1]}")
        return path

    def open_saved(self):
        files = mc.list_saved(self.sb.folder_fn())
        box = BoxLayout(orientation="vertical", spacing=dp(4))
        if not files:
            box.add_widget(_lab("No saved macros yet.", 12))
        for f in files[:12]:
            b = Button(text=f[:-len(".macro.json")], size_hint_y=None, height=dp(38))
            b.bind(on_release=lambda w, f=f: self.load_file(f))
            box.add_widget(b)
        self._popup("Saved macros", box, dp(300), dp(60 + 42 * max(1, min(len(files), 12))))

    def load_file(self, fname):
        import os
        self.macro = mc.load(os.path.join(self.sb.folder_fn(), fname))
        self.name_in.text = self.macro.name
        self.loops_in.text = str(self.macro.loops)
        self.speed_sp.text = f"{self.macro.speed:g}x" if f"{self.macro.speed:g}x" in SPEEDS else "1x"
        self.macro.set_speed(float(self.speed_sp.text[:-1]))
        self.rebuild()
        if self.popup:
            self.popup.dismiss()
        self.sb.say(f"Opened {self.macro.name}")

    def quit(self):
        self.stop()
        self.sb.close_macro()

    # -- edit popup --------------------------------------------------------------------------
    def _popup(self, title, content, w, h):
        if self.popup:
            self.popup.dismiss()
        self.popup = Popup(title=title, content=content, size_hint=(None, None), size=(w, h))
        self.popup.open()
        return self.popup

    def edit(self, i):
        if self.running or not 0 <= i < len(self.macro.actions):
            return
        a = self.macro.actions[i]
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(4))
        self._fields = {}

        def row(key, caption, ms):
            val, unit = mc.from_ms(ms)
            r = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
            r.add_widget(_lab(caption, 12, halign="left"))
            t = TextInput(text=str(val), multiline=False, input_filter="int", size_hint_x=None, width=dp(80))
            s = Spinner(text="seconds" if unit == "s" else "ms", values=("ms", "seconds"),
                        size_hint_x=None, width=dp(90))
            r.add_widget(t)
            r.add_widget(s)
            box.add_widget(r)
            self._fields[key] = (t, s)

        row("interval", "Interval until next action", a["interval_ms"])
        if a["kind"] == "drag":
            row("duration", "Drag takes", a["duration_ms"])
        else:
            row("duration", "Press and hold for (0 = tap)", a["hold_ms"])
        btns = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        cancel = Button(text="Cancel")
        done = Button(text="Done")
        cancel.bind(on_release=lambda *_: self.popup.dismiss())
        done.bind(on_release=lambda *_: self._done_edit(i))
        btns.add_widget(cancel)
        btns.add_widget(done)
        rm = Button(text="Remove Action", size_hint_y=None, height=dp(42), background_color=(0.85, 0.3, 0.3, 1))
        rm.bind(on_release=lambda *_: self.remove_action(i))
        box.add_widget(btns)
        box.add_widget(rm)
        self._popup(f"Edit Action {i + 1}", box, dp(340), dp(238))

    def _done_edit(self, i):
        f = self._fields
        self.apply_edit(i, f["interval"][0].text, f["interval"][1].text,
                        f["duration"][0].text if "duration" in f else None,
                        f["duration"][1].text if "duration" in f else None)
        if self.popup:
            self.popup.dismiss()

    def apply_edit(self, i, interval, unit, duration=None, dunit=None):
        kw = {"interval_ms": mc.to_ms(interval, "s" if unit.startswith("s") else "ms")}
        if duration is not None and 0 <= i < len(self.macro.actions):
            ms = mc.to_ms(duration, "s" if dunit.startswith("s") else "ms")
            if self.macro.actions[i]["kind"] == "drag":
                kw["duration_ms"] = max(50, ms)
            else:
                kw["hold_ms"] = ms
        return self.macro.update(i, **kw)

    def remove_action(self, i):
        self.macro.remove(i)
        if self.popup:
            self.popup.dismiss()
        self.rebuild()

    # -- playback ----------------------------------------------------------------------------
    def toggle_run(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        if not self.macro.actions:
            self.sb.say("Add a click or drag first")
            return
        self.running = True
        self._recolor()
        self._schedule_pass()

    def _schedule_pass(self):
        evs = mc.plan(self.macro, self.sb.width, self.sb.height)
        for e in evs:
            self._handles.append(Clock.schedule_once(lambda dt, e=e: self.fire(e), e[0] / 1000.0))
        last = evs[-1]
        end = (last[0] + last[6] + self.macro.actions[last[7]]["interval_ms"] / self.macro.speed) / 1000.0
        self._handles.append(Clock.schedule_once(self._pass_done, max(end, 0.05)))

    def fire(self, ev):
        if not self.running:
            return
        t, kind, x, y, x2, y2, dur, i = ev
        ox, oy = self.sb.x, self.sb.y
        self.active_idx = i                          # only this action's markers light up
        self._recolor()
        if self._flash_ev:
            self._flash_ev.cancel()
        self._flash_ev = Clock.schedule_once(self._unlight, max(0.3, dur / 1000.0))
        if kind == "drag":
            self.sb.inject_drag(ox + x, oy + y, ox + x2, oy + y2, dur)
        else:
            self.sb.inject_click(ox + x, oy + y, dur)

    def _unlight(self, dt):
        self.active_idx = None
        self._flash_ev = None
        if self.running:
            self._recolor()

    def _pass_done(self, dt):
        self._handles = []
        if self.running and self.macro.loops == 0:
            self._schedule_pass()
        else:
            self.stop()

    def stop(self):
        for h in self._handles:
            h.cancel()
        self._handles = []
        if self._flash_ev:
            self._flash_ev.cancel()
            self._flash_ev = None
        self.active_idx = None
        self.sb.targets.finish_drag(go=False)
        if self.running:
            self.running = False
            self._recolor()


class Sandbox(Widget):
    """The simulated screen plus every floating tool that can sit on it."""

    def __init__(self, folder_fn=None, **kw):
        super().__init__(**kw)
        self.folder_fn = folder_fn or (lambda: app_data.subdir(FOLDER))
        self.bubbles, self.menu_items = {}, []
        self.calc = self.macro = self.xt = self.popup = self.help_popup = None
        self.rec = None
        self._rec_ev = None
        self.targets = Targets()
        self.fx = Fx()
        self.add_widget(self.targets)
        self.add_widget(self.fx)
        self.toast = _lab("", 12, size_hint=(None, None))
        self._toast_ev = None
        self.bind(pos=self._sync, size=self._sync)
        self.show_bubble("master")

    def _sync(self, *a):
        for w in (self.targets, self.fx):
            w.pos, w.size = self.pos, self.size
        for b in self.bubbles.values():
            b.place()
        self.toast.size, self.toast.pos = (self.width, dp(28)), (self.x, self.y + dp(36))
        self.close_menu()

    def _layer(self, w):
        # above the fake apps and the ripples, below the bubbles
        self.add_widget(w, index=max(0, len(self.children) - 2))

    def say(self, text):
        if self.toast.parent is None:
            self.add_widget(self.toast)
            self.toast.size, self.toast.pos = (self.width, dp(28)), (self.x, self.y + dp(36))
        self.toast.text = text
        if self._toast_ev:
            self._toast_ev.cancel()
        self._toast_ev = Clock.schedule_once(lambda dt: setattr(self.toast, "text", ""), 2.5)

    # -- input injection (what the macro does instead of a real Android gesture) -----------------
    def inject_click(self, x, y, hold_ms=0):
        self.fx.ripple(x, y, hold_ms)
        return self.targets.tap(x, y, hold_ms)

    def inject_drag(self, x, y, x2, y2, dur_ms=500):
        self.fx.trail(x, y, x2, y2, dur_ms / 1000.0)
        return self.targets.drag(x, y, x2, y2, dur_ms)

    def permissions_help(self):
        """How to switch on what the real (not sandbox) floating tools will need."""
        lab = Label(text=PERMISSIONS_HELP, font_size=sp(12), halign="left", valign="top",
                    size_hint_y=None, markup=True)
        lab.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                 texture_size=lambda w, v: setattr(w, "height", v[1] + dp(10)))
        sv = ScrollView()
        sv.add_widget(lab)
        box = BoxLayout(orientation="vertical", spacing=dp(6))
        box.add_widget(sv)
        ok = Button(text="Close", size_hint_y=None, height=dp(40))
        box.add_widget(ok)
        pop = Popup(title="Allowing floating tools on your phone", content=box, size_hint=(0.94, 0.85))
        ok.bind(on_release=lambda *_: pop.dismiss())
        pop.open()
        self.help_popup = pop
        return pop

    def reset(self):
        self.close_menu()
        self.close_macro()
        self.close_calc()
        self.targets.reset()

    # -- bubbles -------------------------------------------------------------------------------
    def show_bubble(self, name):
        if name in self.bubbles:
            return self.bubbles[name]
        # on the left edge by default, away from the macro toolbar on the right
        spec = {"master": ("Tools", BLUE, self.toggle_menu, 0.06, 0.86),
                "calc": ("=", ORANGE, self.toggle_calc, 0.06, 0.70),
                "rec": ("Rec", RED, self.rec_tap, 0.06, 0.54)}[name]
        b = Bubble(self, name, spec[0], spec[1], spec[2], fx=spec[3], fy=spec[4])
        self.bubbles[name] = b
        self.add_widget(b)
        return b

    def dismiss_bubble(self, name):
        b = self.bubbles.pop(name, None)
        if b is not None:
            self.remove_widget(b)
        self.close_menu()
        if name == "rec":
            self.stop_recording(quiet=True)

    def toggle_bubble(self, name):
        if name in self.bubbles:
            self.dismiss_bubble(name)
        else:
            self.show_bubble(name)

    def show_x(self, on):
        if on and self.xt is None:
            self.xt = XTarget("X", (0.55, 0.15, 0.15), radius=dp(30))
            self.xt.center = (self.center_x, self.y + dp(70))
            self.add_widget(self.xt)
        elif not on and self.xt is not None:
            self.remove_widget(self.xt)
            self.xt = None

    def x_hover(self, center):
        if self.xt is None:
            return False
        hot = math.hypot(center[0] - self.xt.center_x, center[1] - self.xt.center_y) < dp(60)
        if hot != self.xt.hot:
            self.xt.hot = hot
            self.xt.redraw()
        return hot

    # -- radial menu ---------------------------------------------------------------------------
    def toggle_menu(self):
        if self.menu_items:
            self.close_menu()
            return
        m = self.bubbles.get("master")
        if m is None:
            return
        items = [("Calc", ORANGE, self.toggle_calc), ("Macro", GREEN, self.toggle_macro),
                 ("Rec", RED, lambda: self.show_bubble("rec"))]
        right = m.center_x > self.center_x
        base = math.pi if right else 0.0
        for k, (text, col, fn) in enumerate(items):
            ang = base + (k - 1) * 0.75
            chip = Chip(text, col, cb=lambda fn=fn: (self.close_menu(), fn()), radius=dp(26))
            chip.center = (min(max(m.center_x + math.cos(ang) * dp(78), self.x + dp(26)), self.right - dp(26)),
                           min(max(m.center_y + math.sin(ang) * dp(78), self.y + dp(26)), self.top - dp(26)))
            self.menu_items.append(chip)
            self.add_widget(chip)

    def close_menu(self):
        for c in self.menu_items:
            self.remove_widget(c)
        self.menu_items = []

    def on_touch_down(self, touch):
        if self.menu_items and not any(_hit(c.center, c.r, touch) for c in self.menu_items):
            m = self.bubbles.get("master")
            if not (m and _hit(m.center, m.r, touch)):
                self.close_menu()
        return super().on_touch_down(touch)

    # -- calculator ----------------------------------------------------------------------------
    def toggle_calc(self):
        self.close_calc() if self.calc else self.open_calc()

    def open_calc(self):
        if self.calc is None:
            self.calc = CalcPanel(self)
            self.calc.pos = (self.center_x - self.calc.width / 2, self.center_y - self.calc.height / 2)
            self._layer(self.calc)
        return self.calc

    def close_calc(self):
        if self.calc is not None:
            self.remove_widget(self.calc)
            self.calc = None

    # -- macro ---------------------------------------------------------------------------------
    def toggle_macro(self):
        self.close_macro() if self.macro else self.open_macro()

    def open_macro(self):
        if self.macro is None:
            self.macro = MacroOverlay(self)
            self._layer(self.macro)
        return self.macro

    def close_macro(self):
        if self.macro is not None:
            self.macro.stop()
            self.remove_widget(self.macro)
            self.macro = None

    # -- simulated recorder ----------------------------------------------------------------------
    def rec_tap(self):
        if self.rec is not None:
            self.stop_recording()
            return
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(4))
        opts = {}
        for key, text, on in (("device", "Device audio", True), ("mic", "Microphone", False),
                              ("mute", "Mute", False)):
            t = ToggleButton(text=text, state="down" if on else "normal", size_hint_y=None, height=dp(38))
            opts[key] = t
            box.add_widget(t)
        res = Spinner(text="1080p", values=("720p", "1080p", "Native"), size_hint_y=None, height=dp(38))
        box.add_widget(res)
        box.add_widget(_lab("Simulated: nothing is captured here. Real recording needs the Android service.",
                            10, theme.MUTED, size_hint_y=None, height=dp(44), text_size=(dp(280), None)))
        go = Button(text="Start", size_hint_y=None, height=dp(42))
        go.bind(on_release=lambda *_: self.start_recording())
        box.add_widget(go)
        if self.popup:
            self.popup.dismiss()
        self.popup = Popup(title="Recording Setup", content=box, size_hint=(None, None), size=(dp(320), dp(380)))
        self.popup.open()

    def start_recording(self):
        if self.popup:
            self.popup.dismiss()
        self.rec = 0
        self._tick_rec(0)
        self._rec_ev = Clock.schedule_interval(self._tick_rec, 1)

    def _tick_rec(self, dt):
        if self.rec is None:
            return
        if dt:
            self.rec += 1
        b = self.bubbles.get("rec")
        if b:
            b.set_text(f"{self.rec // 60:02d}:{self.rec % 60:02d}")

    def stop_recording(self, quiet=False):
        if self._rec_ev:
            self._rec_ev.cancel()
            self._rec_ev = None
        secs, self.rec = self.rec, None
        b = self.bubbles.get("rec")
        if b:
            b.set_text("Rec")
        if secs is not None and not quiet:
            self.say(f"Simulated recording stopped after {secs}s (nothing was captured)")


class OverlaySandboxScreen(Screen):
    title = "Overlay Sandbox"

    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", spacing=dp(3), padding=dp(4))
        bar = ScrollView(size_hint_y=None, height=dp(44), do_scroll_y=False)
        row = BoxLayout(size_hint_x=None, spacing=dp(4))
        self.sb = Sandbox(folder_fn=self._folder)
        self.btns = {}
        for key, text, fn in (("back", "Back", self._leave),
                              ("master", "Master", lambda: self.sb.toggle_bubble("master")),
                              ("calc", "Calc dot", lambda: self.sb.toggle_bubble("calc")),
                              ("rec", "Rec dot", lambda: self.sb.toggle_bubble("rec")),
                              ("macro", "Macro", lambda: self.sb.toggle_macro()),
                              ("panel", "Calculator", lambda: self.sb.toggle_calc()),
                              ("help", "Permissions", lambda: self.sb.permissions_help()),
                              ("reset", "Reset", lambda: self.sb.reset())):
            b = Button(text=text, size_hint_x=None, width=dp(92))
            b.bind(on_release=lambda w, fn=fn: fn())
            self.btns[key] = b
            row.add_widget(b)
        row.width = dp(96) * len(self.btns)
        bar.add_widget(row)
        root.add_widget(bar)
        root.add_widget(self.sb)
        hint = _lab("A practice screen for the floating tools. Drag a dot to move it, or onto the X to dismiss it.",
                    10, theme.MUTED, size_hint_y=None, height=dp(18), halign="left")
        hint.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(hint)
        self.add_widget(root)

    def _folder(self):
        return app_data.subdir(FOLDER)

    def _leave(self):
        if self.manager:
            self.manager.current = "dashboard"
