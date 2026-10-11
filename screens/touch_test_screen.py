# screens/touch_test_screen.py
#
# Shows exactly what the app receives when you tap. Built to settle the
# Android "needs two taps / taps do nothing" question with evidence from the
# phone itself instead of guesses:
#
#   * every touch that reaches the pad is drawn as a dot, coloured by which
#     input provider produced it (green = sdl/finger, red = mouse, blue =
#     anything else) and listed with its position;
#   * "touches per tap" tells you whether one finger tap arrives once (good)
#     or twice (the duplicate-tap bug: a green dot AND a red dot);
#   * a switch turns the duplicate-tap filter on/off (applies after a restart;
#     it switches itself back off if taps stop working with it on).
#
# Needs no adb: tap the pad, take a screenshot, send it.

import time

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.graphics import Color, Ellipse, Rectangle
from kivy.metrics import dp
from kivy.clock import Clock

import core.touch_dedupe as td

DEV_COLORS = {
    "sdl": (0.2, 0.9, 0.3, 0.85),     # finger
    "mouse": (0.95, 0.25, 0.25, 0.85),
}
OTHER = (0.3, 0.5, 1.0, 0.85)
GROUP_GAP = 0.25        # touches closer together than this = same tap


class _Pad(Widget):
    def __init__(self, owner, **kw):
        super().__init__(**kw)
        self._owner = owner
        self.dots = []                      # (x, y, color)
        self.bind(pos=self._redraw, size=self._redraw)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._owner.record(touch)
        self.dots.append((touch.x, touch.y,
                          DEV_COLORS.get(touch.device, OTHER)))
        self.dots = self.dots[-24:]
        self._redraw()
        return True

    def _redraw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(0.1, 0.1, 0.12, 1)
            Rectangle(pos=self.pos, size=self.size)
            r = dp(14)
            for x, y, col in self.dots:
                Color(*col)
                Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))


class TouchTestScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._events = []        # (monotonic, device, x, y)
        self._taps = 0
        self._touches = 0
        self._by_dev = {}

        root = BoxLayout(orientation="vertical", padding=dp(6),
                         spacing=dp(6))
        self._help = Label(
            text=("Tap the dark pad with ONE finger, one tap at a time.\n"
                  "1 dot per tap = good.  A green AND a red dot per tap = "
                  "duplicate-tap bug."),
            font_size=12, size_hint_y=None, height=dp(48), halign="left",
            valign="middle")
        self._help.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        root.add_widget(self._help)

        self._summary = Label(text="", font_size=13, size_hint_y=None,
                              height=dp(44), halign="left", valign="middle",
                              color=(0.7, 0.9, 1, 1))
        self._summary.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        root.add_widget(self._summary)

        self._pad = _Pad(self)
        root.add_widget(self._pad)

        self._log = Label(text="", font_size=11, size_hint_y=None,
                          height=dp(96), halign="left", valign="top")
        self._log.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        root.add_widget(self._log)

        self._filter_lbl = Label(text="", font_size=12, size_hint_y=None,
                                 height=dp(34), halign="left",
                                 valign="middle")
        self._filter_lbl.bind(
            size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        root.add_widget(self._filter_lbl)

        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        clear = Button(text="Clear", font_size=13)
        clear.bind(on_release=lambda *a: self._clear())
        self._filter_btn = Button(text="", font_size=12)
        self._filter_btn.bind(on_release=lambda *a: self._toggle_filter())
        row.add_widget(clear)
        row.add_widget(self._filter_btn)
        root.add_widget(row)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(
            self.manager, "current", "dashboard"))
        root.add_widget(back)
        self.add_widget(root)

        self._refresh_filter_ui()
        self._refresh_summary()

    # ── recording ─────────────────────────────────────────────────────────
    def record(self, touch):
        now = time.monotonic()
        # new tap if nothing arrived in the last GROUP_GAP seconds
        if not self._events or now - self._events[-1][0] > GROUP_GAP:
            self._taps += 1
        self._events.append((now, touch.device, touch.x, touch.y))
        self._events = self._events[-40:]
        self._touches += 1
        self._by_dev[touch.device] = self._by_dev.get(touch.device, 0) + 1
        self._refresh_summary()
        t0 = self._events[0][0]
        lines = [f"{e[1]:6s} ({e[2]:.0f}, {e[3]:.0f})  +{(e[0] - t0) * 1000:.0f} ms"
                 for e in self._events[-6:]]
        self._log.text = "\n".join(lines)

    def _clear(self):
        self._events, self._taps, self._touches, self._by_dev = [], 0, 0, {}
        self._pad.dots = []
        self._pad._redraw()
        self._log.text = ""
        self._refresh_summary()

    def _refresh_summary(self):
        per = (self._touches / self._taps) if self._taps else 0
        devs = ", ".join(f"{k}: {v}" for k, v in sorted(self._by_dev.items())) \
            or "-"
        verdict = ""
        if self._taps >= 3:
            verdict = ("   -> DUPLICATE TAPS" if per > 1.4 else
                       "   -> looks fine")
        self._summary.text = (f"taps: {self._taps}   touches: {self._touches}"
                              f"   per tap: {per:.1f}{verdict}\n"
                              f"by provider: {devs}")

    # ── duplicate-tap filter switch ───────────────────────────────────────
    def _refresh_filter_ui(self):
        cfg = td.load_cfg()
        active_now = td._deduper is not None and not td._deduper.disabled
        self._filter_btn.text = ("Filter: ON (tap to turn off)"
                                 if cfg["enabled"] else
                                 "Filter: OFF (tap to turn on)")
        self._filter_lbl.text = (
            f"Filter active this session: {'yes' if active_now else 'no'}"
            f"   ghost taps removed: {td.stats()}\n"
            "Changes apply after you close and reopen the app.")

    def _toggle_filter(self):
        cfg = td.load_cfg()
        td.set_enabled(not cfg["enabled"])
        self._refresh_filter_ui()

    def on_enter(self, *a):
        self._refresh_filter_ui()
        self._ev = Clock.schedule_interval(
            lambda dt: self._refresh_filter_ui(), 1.0)

    def on_leave(self, *a):
        ev = getattr(self, "_ev", None)
        if ev:
            ev.cancel()
            self._ev = None
