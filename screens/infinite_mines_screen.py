# screens/infinite_mines_screen.py - Infinite Mines (a raw demo of the idea).
# An endless minesweeper map you pan around. The rules live in
# core/infinite_mines_core.py; this file only draws the visible cells and turns
# touches into actions: tap = the chosen mode (Dig / Flag / Repair), long-press
# = the other one of Dig/Flag, drag = pan, pinch or wheel = zoom.
import math
import os
import random
import time

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
from kivy.graphics import (Color, Ellipse, InstructionGroup, Line, Rectangle,
                           ScissorPop, ScissorPush, Triangle)
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

import app_data
from core import infinite_mines_core as im
from core import theme
from core.jsonio import read_json, write_json_atomic
from screens.scaffold import ToolScreen

HIDDEN_C = (0.27, 0.30, 0.35, 1)
OPEN_C = (0.09, 0.10, 0.12, 1)
GRID_C = (0.15, 0.17, 0.20, 1)
SECTOR_C = (0.34, 0.38, 0.48, 1)
SCORCH_C = (0.42, 0.25, 0.12, 1)
ASH_C = (0.82, 0.82, 0.80, 1)
CRATER_C = (0.0, 0.0, 0.0, 1)
CRATER_IN = (0.14, 0.14, 0.15, 1)
FLAG_C = (0.92, 0.30, 0.35, 1)
DEFUSED_C = (0.35, 0.85, 0.50, 1)       # a flag on a mine that has been paid
HINT_C = (1.0, 0.85, 0.2, 1)
BURST_RED = (0.95, 0.25, 0.35)
BURST_BLUE = (0.45, 0.70, 1.0)
BURST_GREEN = (0.40, 0.90, 0.55)
BURST_FIRE = (1.0, 0.60, 0.20)
NUM_C = {1: (0.45, 0.70, 1.0, 1), 2: (0.40, 0.85, 0.50, 1), 3: (1.0, 0.45, 0.45, 1),
         4: (0.70, 0.55, 1.0, 1), 5: (1.0, 0.65, 0.30, 1), 6: (0.35, 0.90, 0.90, 1),
         7: (0.90, 0.90, 0.90, 1), 8: (0.60, 0.60, 0.60, 1)}
MIN_ZOOM, MAX_ZOOM = 0.45, 2.6
LONG_PRESS = 0.38                       # the same hold as the normal Minesweeper
GHOST_WINDOW = 0.6
HELP = ("Tap to dig, hold to flag. Brown = scorched: dig next to it and it heals "
        "one layer at a time; dig the pale cells to carry on inwards (flags "
        "don't heal). Flags on mines pay bonus points when their sector is "
        f"solved. A hint costs {im.HINT_COST} pts.")


def save_path():
    return os.path.join(app_data.subdir("infinite_mines"), "world.json")


class MapView(Widget):
    """The endless map. cx, cy is the world point in the middle of the widget."""

    def __init__(self, world, on_outcome, **kw):
        super().__init__(**kw)
        self.world, self.on_outcome = world, on_outcome
        self.mode, self.zoom = "dig", 1.0
        self.cx = self.cy = 0.5
        self.view_cb = None
        self._touches, self._pinch = {}, None
        self._tex, self._tex_size = {}, 0
        self._redraw = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self._redraw, size=self._redraw)
        # effects live in their own group above the map, redrawn by a timer
        # that only runs while something is animating
        self._fxg = InstructionGroup()
        self.canvas.after.add(self._fxg)
        self._parts, self._flashes, self._texts = [], [], []
        self.hint_cell = None
        self._fx_ev = None
        self._fx_last = 0.0
        self._ftex = {}

    @property
    def cs(self):
        return dp(34) * self.zoom

    @property
    def slop(self):
        return dp(10)

    # ---- coordinates
    def cell_at(self, px, py):
        cs = self.cs
        return (math.floor(self.cx + (px - self.center_x) / cs),
                math.floor(self.cy + (py - self.center_y) / cs))

    def pos_of(self, x, y):
        """Screen position of the middle of cell x, y."""
        cs = self.cs
        return (self.center_x + (x + 0.5 - self.cx) * cs,
                self.center_y + (y + 0.5 - self.cy) * cs)

    def zoom_by(self, factor, anchor=None):
        ax, ay = anchor if anchor else self.center
        wx = self.cx + (ax - self.center_x) / self.cs
        wy = self.cy + (ay - self.center_y) / self.cs
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        self.cx = wx - (ax - self.center_x) / self.cs
        self.cy = wy - (ay - self.center_y) / self.cs
        self._redraw()

    def go_home(self):
        self.cx = self.cy = 0.5
        self._redraw()

    # ---- drawing
    def _digit(self, n):
        size = max(8, int(self.cs * 0.55))
        if size != self._tex_size or len(self._tex) > 40:
            self._tex, self._tex_size = {}, size
        tex = self._tex.get(n)
        if tex is None:
            lab = CoreLabel(text=str(n), font_size=size, bold=True)
            lab.refresh()
            tex = self._tex[n] = lab.texture
        return tex

    def redraw(self, *a):
        self.canvas.clear()
        w, h = self.size
        if w < 2 or h < 2:
            return
        cs, world = self.cs, self.world
        x0, x1 = math.floor(self.cx - w / 2 / cs), math.floor(self.cx + w / 2 / cs)
        y0, y1 = math.floor(self.cy - h / 2 / cs), math.floor(self.cy + h / 2 / cs)
        ox = self.center_x - self.cx * cs
        oy = self.center_y - self.cy * cs
        with self.canvas:
            ScissorPush(x=int(self.x), y=int(self.y), width=int(w), height=int(h))
            Color(*HIDDEN_C)
            Rectangle(pos=self.pos, size=self.size)
            for y in range(y0, y1 + 1):
                py = oy + y * cs
                for x in range(x0, x1 + 1):
                    v = world.view(x, y)
                    if v == im.HIDDEN:
                        continue
                    px = ox + x * cs
                    if isinstance(v, int):
                        Color(*OPEN_C)
                        Rectangle(pos=(px, py), size=(cs, cs))
                        if v:
                            tex = self._digit(v)
                            Color(*NUM_C[v])
                            Rectangle(texture=tex, size=tex.size,
                                      pos=(px + (cs - tex.width) / 2,
                                           py + (cs - tex.height) / 2))
                    elif v == im.FLAG:
                        Color(*(DEFUSED_C if (x, y) in world.defused else FLAG_C))
                        Triangle(points=[px + cs * .38, py + cs * .48, px + cs * .38,
                                         py + cs * .86, px + cs * .82, py + cs * .67])
                        Rectangle(pos=(px + cs * .33, py + cs * .14), size=(cs * .07, cs * .72))
                    elif v == im.CRATER:
                        Color(*CRATER_C)
                        Rectangle(pos=(px, py), size=(cs, cs))
                        Color(*CRATER_IN)
                        Ellipse(pos=(px + cs * .2, py + cs * .2), size=(cs * .6, cs * .6))
                    elif v == im.SCORCH:
                        Color(*SCORCH_C)
                        Rectangle(pos=(px, py), size=(cs, cs))
                    elif v == im.ASH:
                        Color(*ASH_C)
                        Rectangle(pos=(px, py), size=(cs, cs))
            for x in range(x0, x1 + 2):
                Color(*(SECTOR_C if x % im.CHUNK == 0 else GRID_C))
                Line(points=[ox + x * cs, self.y, ox + x * cs, self.top],
                     width=1.6 if x % im.CHUNK == 0 else 1)
            for y in range(y0, y1 + 2):
                Color(*(SECTOR_C if y % im.CHUNK == 0 else GRID_C))
                Line(points=[self.x, oy + y * cs, self.right, oy + y * cs],
                     width=1.6 if y % im.CHUNK == 0 else 1)
            ScissorPop()
        if self.view_cb:
            self.view_cb()

    # ---- actions
    def act(self, pos, mode):
        x, y = self.cell_at(*pos)
        w = self.world
        self.hint_cell = None
        out = (w.dig(x, y) if mode == "dig" else
               w.toggle_flag(x, y) if mode == "flag" else w.repair(x, y))
        self.on_outcome(out)
        self._celebrate(out, x, y)
        self._redraw()
        return out

    # ---- rewards: dots that fly out of the cell, flashes, floating points
    def _celebrate(self, out, x, y):
        k = out.kind
        if k == "dug" and out.revealed:
            self.burst(x + .5, y + .5, BURST_BLUE, min(14, 4 + out.revealed // 4),
                       speed=1.6 + min(out.revealed, 60) / 30)
        elif k == "chord" and out.revealed:
            self.burst(x + .5, y + .5, BURST_BLUE, 10, speed=2.2)
        elif k == "flag":
            self.burst(x + .5, y + .5, BURST_RED, 7, speed=1.3, life=.45)
            if out.defused:
                self.burst(x + .5, y + .5, BURST_GREEN, 10, speed=2.0)
                self.float_text(x + .5, y + .5, "+1 defused", BURST_GREEN)
        elif k == "blast" and out.blast:
            bx, by = out.blast
            self.burst(bx + .5, by + .5, BURST_FIRE, 38, speed=4.0 + out.radius,
                       life=.8, size=.2)
            self.burst(bx + .5, by + .5, BURST_RED, 16, speed=2.5, life=.7)
            self.float_text(bx + .5, by + .5, "BOOM!", BURST_FIRE)
        elif k == "repair":
            self.burst(x + .5, y + .5, (0.9, 0.9, 0.9), 14, speed=2.0)
        for (cx, cy), pts in out.sectors:
            mx, my = (cx + .5) * im.CHUNK, (cy + .5) * im.CHUNK
            self._flashes.append([cx * im.CHUNK, cy * im.CHUNK, im.CHUNK,
                                  time.monotonic(), 1.0, BURST_GREEN])
            self.burst(mx, my, BURST_GREEN, 36, speed=5.0, life=.9, size=.2)
            self.float_text(mx, my, f"+{pts}", (1, 1, 1))
        self._fx_start()

    def burst(self, wx, wy, color, n, speed=2.0, life=.6, size=.14):
        now = time.monotonic()
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            v = speed * random.uniform(.35, 1.0)
            self._parts.append([wx, wy, math.cos(a) * v, math.sin(a) * v, now,
                                life * random.uniform(.7, 1.1), color,
                                size * random.uniform(.7, 1.3)])
        if len(self._parts) > 260:
            del self._parts[:len(self._parts) - 260]

    def float_text(self, wx, wy, text, color):
        self._texts.append([wx, wy, text, time.monotonic(), 1.3, color])

    def show_hint(self, cell):
        """Pulse a gold frame on a cell, and bring it into view."""
        self.hint_cell = cell
        x, y = cell
        w, h = self.size
        cs = self.cs
        if (abs(x + .5 - self.cx) > w / 2 / cs - 1.2
                or abs(y + .5 - self.cy) > h / 2 / cs - 1.2):
            self.cx, self.cy = x + .5, y + .5
        self._redraw()
        self._fx_start()

    def stop_fx(self):
        if self._fx_ev is not None:
            self._fx_ev.cancel()
            self._fx_ev = None
        self._parts, self._flashes, self._texts = [], [], []
        self.hint_cell = None
        self._fxg.clear()

    def _fx_start(self):
        if self._fx_ev is None:
            self._fx_last = time.monotonic()
            self._fx_ev = Clock.schedule_interval(self._fx_tick, 1 / 30.)

    def _ftext(self, text):
        t = self._ftex.get(text)
        if t is None:
            if len(self._ftex) > 30:
                self._ftex.clear()
            lab = CoreLabel(text=text, font_size=int(sp(20)), bold=True)
            lab.refresh()
            t = self._ftex[text] = lab.texture
        return t

    def _fx_tick(self, dt):
        now = time.monotonic()
        step, self._fx_last = now - self._fx_last, now
        self._parts = [p for p in self._parts if now - p[4] < p[5]]
        self._flashes = [f for f in self._flashes if now - f[3] < f[4]]
        self._texts = [t for t in self._texts if now - t[3] < t[4]]
        g = self._fxg
        g.clear()
        if not (self._parts or self._flashes or self._texts or self.hint_cell):
            self._fx_ev.cancel()
            self._fx_ev = None
            return
        cs = self.cs
        ox, oy = self.center_x - self.cx * cs, self.center_y - self.cy * cs
        g.add(ScissorPush(x=int(self.x), y=int(self.y), width=int(self.width),
                          height=int(self.height)))
        for f in self._flashes:
            a = 1 - (now - f[3]) / f[4]
            g.add(Color(f[5][0], f[5][1], f[5][2], .35 * a))
            g.add(Rectangle(pos=(ox + f[0] * cs, oy + f[1] * cs),
                            size=(f[2] * cs, f[2] * cs)))
            g.add(Color(f[5][0], f[5][1], f[5][2], a))
            g.add(Line(rectangle=(ox + f[0] * cs, oy + f[1] * cs, f[2] * cs, f[2] * cs),
                       width=dp(2.5)))
        for p in self._parts:
            p[0] += p[2] * step
            p[1] += p[3] * step
            p[2] *= .93
            p[3] *= .93
            t = (now - p[4]) / p[5]
            r = p[7] * cs * (1 - .5 * t)
            g.add(Color(p[6][0], p[6][1], p[6][2], 1 - t))
            g.add(Ellipse(pos=(ox + p[0] * cs - r, oy + p[1] * cs - r), size=(2 * r, 2 * r)))
        for tx in self._texts:
            t = (now - tx[3]) / tx[4]
            tex = self._ftext(tx[2])
            g.add(Color(tx[5][0], tx[5][1], tx[5][2], 1 - t * t))
            g.add(Rectangle(texture=tex, size=tex.size,
                            pos=(ox + tx[0] * cs - tex.width / 2,
                                 oy + (tx[1] + t * 1.5) * cs)))
        if self.hint_cell:
            hx, hy = self.hint_cell
            pulse = .5 + .5 * math.sin(now * 7)
            px, py = ox + hx * cs, oy + hy * cs
            g.add(Color(HINT_C[0], HINT_C[1], HINT_C[2], .18 + .25 * pulse))
            g.add(Rectangle(pos=(px, py), size=(cs, cs)))
            g.add(Color(*HINT_C))
            g.add(Line(rectangle=(px + 2, py + 2, cs - 4, cs - 4), width=dp(2 + 1.5 * pulse)))
        g.add(ScissorPop())

    # ---- touch: tap, long-press, drag to pan, pinch / wheel to zoom
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if touch.is_mouse_scrolling:
            self.zoom_by(1.15 if touch.button == "scrollup" else 1 / 1.15, touch.pos)
            return True
        if self._is_ghost(touch):
            return True
        touch.grab(self)
        self._touches[touch.uid] = touch
        touch.ud.update(o=touch.pos, moved=False, long=False, t0=time.monotonic())
        if len(self._touches) > 1:
            for t in self._touches.values():
                t.ud["moved"] = True
                self._cancel(t)
            self._pinch = self._span()
        else:
            touch.ud["lp"] = Clock.schedule_once(lambda dt, t=touch: self._long(t), LONG_PRESS)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        ud = touch.ud
        if len(self._touches) >= 2:
            d = self._span()
            if self._pinch and d > 0:
                mid = self._mid()
                self.zoom_by(d / self._pinch, mid)
            self._pinch = d
            return True
        if not ud["moved"] and math.hypot(touch.x - ud["o"][0], touch.y - ud["o"][1]) > self.slop:
            ud["moved"] = True
            self._cancel(touch)
        if ud["moved"]:
            self.cx -= touch.dx / self.cs
            self.cy -= touch.dy / self.cs
            self._redraw()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self._touches.pop(touch.uid, None)
        self._cancel(touch)
        ud = touch.ud
        if not self._touches and not ud["moved"] and not ud["long"]:
            self.act(touch.pos, self.mode)
        if len(self._touches) < 2:
            self._pinch = None
        return True

    def _long(self, touch):
        if self.mode == "repair":
            return                      # repair is a paid action: never by accident
        if touch.uid in self._touches and not touch.ud["moved"]:
            touch.ud["long"] = True
            self.act(touch.pos, "flag" if self.mode == "dig" else "dig")

    def _is_ghost(self, touch):
        """Android delivers one finger twice: as a finger touch and as the
        mouse event made from it, at the same spot. Treated as two fingers
        that looked like a pinch: no tap, no pan, no long-press. A second touch
        from the OTHER input device, on top of a live one, is that duplicate.
        (A real second finger comes from the same device, or lands further
        away.)"""
        now = time.monotonic()
        for t in self._touches.values():
            if (getattr(t, "device", "") != getattr(touch, "device", "")
                    and now - t.ud.get("t0", 0) < GHOST_WINDOW
                    and math.hypot(t.x - touch.x, t.y - touch.y) < dp(12)):
                return True
        return False

    @staticmethod
    def _cancel(touch):
        ev = touch.ud.pop("lp", None)
        if ev is not None:
            ev.cancel()

    def _span(self):
        ts = list(self._touches.values())[:2]
        return math.hypot(ts[0].x - ts[1].x, ts[0].y - ts[1].y) if len(ts) == 2 else 0

    def _mid(self):
        ts = list(self._touches.values())[:2]
        return (sum(t.x for t in ts) / len(ts), sum(t.y for t in ts) / len(ts))


class InfiniteMinesScreen(ToolScreen):
    title = "Infinite Mines"

    def __init__(self, **kw):
        super().__init__(**kw)
        self._save_ev = self._arm_ev = None
        self.world = self._load()
        root = self.body

        self.status = Label(font_size=sp(12), color=theme.MUTED, halign="left", valign="middle",
                            size_hint_y=None, height=dp(36))
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.status)

        self.map = MapView(self.world, self._outcome)
        self.map.view_cb = self._status
        root.add_widget(self.map)

        self.msg = Label(text=HELP, font_size=sp(12), color=theme.MUTED, halign="left",
                         valign="middle", size_hint_y=None, height=dp(62))
        self.msg.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.msg)

        modes = BoxLayout(size_hint_y=None, height=dp(44), spacing=theme.PAD["s"])
        self.mode_btns = {}
        for key, text in (("dig", "Dig"), ("flag", "Flag"),
                          ("repair", f"Repair ({im.REPAIR_COST})")):
            b = ToggleButton(text=text, group="imode", font_size=sp(13),
                             allow_no_selection=False, state="down" if key == "dig" else "normal")
            b.bind(on_release=lambda inst, k=key: self._set_mode(k))
            self.mode_btns[key] = b
            modes.add_widget(b)
        self.hint_btn = Button(text=f"Hint ({im.HINT_COST})", font_size=sp(13),
                               background_color=(0.55, 0.45, 0.1, 1))
        self.hint_btn.bind(on_release=lambda *a: self._hint())
        modes.add_widget(self.hint_btn)
        root.add_widget(modes)

        tools = BoxLayout(size_hint_y=None, height=dp(40), spacing=theme.PAD["s"])
        for text, fn in (("-", lambda *a: self.map.zoom_by(1 / 1.3)),
                         ("+", lambda *a: self.map.zoom_by(1.3)),
                         ("Home", lambda *a: self.map.go_home())):
            b = Button(text=text, font_size=sp(14))
            b.bind(on_release=fn)
            tools.add_widget(b)
        self.new_btn = Button(text="New world", font_size=sp(13))
        self.new_btn.bind(on_release=lambda *a: self._new_press())
        tools.add_widget(self.new_btn)
        root.add_widget(tools)
        Clock.schedule_once(lambda dt: self._status(), 0)

    # ---- state
    def _load(self):
        w = im.World.from_dict(read_json(save_path(), None))
        if w is None:
            w = im.World()
            w.start()
        return w

    def _save(self, *a):
        if self._save_ev is not None:
            self._save_ev.cancel()
            self._save_ev = None
        try:
            write_json_atomic(save_path(), self.world.to_dict(), indent=None)
        except OSError as e:
            print(f"Infinite Mines: could not save: {e}")

    def _later_save(self):
        # One save at most 2 s after the first unsaved action. Restarting the
        # timer on every action would starve it during continuous play.
        if self._save_ev is None:
            self._save_ev = Clock.schedule_once(self._save, 2.0)

    def on_leave(self, *a):
        self.map.stop_fx()
        self._save()

    def _hint(self):
        m = self.map
        reach = int(max(m.width, m.height) / m.cs / 2) + 4
        out = self.world.hint(m.cx, m.cy, reach)
        self._outcome(out)
        if out.kind == "hint":
            m.show_hint(out.target)

    def _set_mode(self, key):
        self.map.mode = key

    # ---- feedback
    def _status(self, *a):
        w = self.world
        self.status.text = (f"Points {w.points}  -  Sectors {len(w.solved)}  -  Craters {len(w.craters)}\n"
                            f"Dug {w.dug}  -  at ({math.floor(self.map.cx)}, {math.floor(self.map.cy)})")

    def _outcome(self, out):
        k, parts = out.kind, []
        if k == "blast":
            parts.append(f"BOOM! Crater, radius {out.radius}. {out.erased} cells lost. "
                         f"The ring around the brown area is opened for you: "
                         f"hidden cells left in it are mines. Solve from there.")
        elif k == "hint":
            what = {"dig": "Safe: dig the gold cell.",
                    "flag": "A mine: flag the gold cell.",
                    "unflag": "That flag is wrong: remove it."}[out.action]
            parts.append(f"{what} (-{im.HINT_COST} pts)")
        elif k == "nohint":
            parts.append("No certain move near here (nothing charged). Move the "
                         "map, or the next step needs a guess.")
        elif k == "poor_hint":
            parts.append(f"A hint costs {im.HINT_COST} points. Solve sectors to earn them.")
        elif k == im.SCORCH:
            parts.append(f"Scorched: dig the cells next to it to heal it, or Repair ({im.REPAIR_COST} pts).")
        elif k == im.CRATER:
            parts.append("That is a crater: permanent.")
        elif k == "flagged":
            parts.append("Remove the flag first.")
        elif k == "poor":
            parts.append(f"Repair costs {im.REPAIR_COST} points. Solve sectors to earn them.")
        elif k == "repair":
            parts.append(f"Repaired {out.healed} cells.")
        elif k == "noop":
            parts.append("Nothing to open: the flags around that number don't match it.")
        for _, pts in out.sectors:
            parts.append(f"Sector solved! +{pts} points"
                         + (f" ({out.defused} defused)." if out.defused else "."))
        if k == "flag" and out.defused and not out.sectors:
            parts.append("Defused! +1 point.")
        if out.healed and k != "repair":
            parts.append(f"{out.healed} scorched cells healed.")
        if k in ("dug", "chord") and not parts:
            parts.append(HELP)
        if parts:
            self.msg.text = "  ".join(parts)
        self._status()
        if k not in (im.SCORCH, im.CRATER, "flagged", "poor", "noop", "revealed",
                     "nohint", "poor_hint"):
            self._later_save()

    def _new_press(self):
        if self._arm_ev is None:
            self.new_btn.text = "Sure? Tap again"
            self._arm_ev = Clock.schedule_once(self._disarm, 3.0)
            return
        self._disarm()
        self.world = im.World()
        self.world.start()
        self.map.world = self.world
        self.map.stop_fx()
        self.map.go_home()
        self.msg.text = "A new world. " + HELP
        self._status()
        self._save()

    def _disarm(self, *a):
        if self._arm_ev is not None:
            self._arm_ev.cancel()
            self._arm_ev = None
        self.new_btn.text = "New world"
