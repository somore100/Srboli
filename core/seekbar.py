# core/seekbar.py - a thick, finger-friendly progress/seek bar.
#
# Kivy's Slider is a thin line with a small knob you have to hit exactly, and
# it keeps firing while you drag. SeekBar fixes the things that were annoying
# in the Music Player:
#   - the WHOLE widget is the touch target; touching anywhere jumps there and
#     dragging keeps following the finger (the knob can be off-target)
#   - a filled bar shows progress, with faint tick marks (every 10 s ... 10 min,
#     whichever keeps about 12 or fewer) so a long track reads as a timeline
#   - events: on_scrub(value) while the finger moves, on_seek(value) once on
#     release. Playback code seeks on release only, so dragging is smooth and
#     the audio isn't restarted a hundred times
#   - while scrubbing, `scrubbing` is True: the player must not overwrite
#     `value` from its timer then

from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty
from kivy.uix.widget import Widget

TICK_STEPS = (10, 30, 60, 120, 300, 600, 1800, 3600)


def tick_step(total, max_ticks=12):
    """Smallest 'nice' step (seconds) that gives at most max_ticks ticks."""
    for s in TICK_STEPS:
        if total / s <= max_ticks:
            return s
    return TICK_STEPS[-1]


class SeekBar(Widget):
    value = NumericProperty(0)
    max = NumericProperty(1)
    scrubbing = BooleanProperty(False)
    accent = ListProperty([0.25, 0.70, 0.95, 1])
    show_ticks = BooleanProperty(True)

    __events__ = ("on_scrub", "on_seek")

    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(44))
        super().__init__(**kw)
        self._pad = dp(14)            # room at each end for the knob
        self.bind(pos=self._draw, size=self._draw, value=self._draw,
                  max=self._draw, scrubbing=self._draw, accent=self._draw,
                  show_ticks=self._draw)
        self._draw()

    # ── geometry ──────────────────────────────────────────────────────────
    def _span(self):
        return max(1.0, self.width - 2 * self._pad)

    def fraction(self):
        return 0.0 if self.max <= 0 else max(0.0, min(1.0, self.value / self.max))

    def value_at(self, x):
        f = (x - self.x - self._pad) / self._span()
        return max(0.0, min(1.0, f)) * self.max

    def _draw(self, *a):
        self.canvas.clear()
        th = dp(10)                                   # track thickness
        cy = self.center_y
        x0 = self.x + self._pad
        span = self._span()
        fx = x0 + span * self.fraction()
        with self.canvas:
            Color(0.28, 0.28, 0.32, 1)
            RoundedRectangle(pos=(x0, cy - th / 2), size=(span, th),
                             radius=[th / 2])
            if fx > x0:
                Color(*self.accent)
                RoundedRectangle(pos=(x0, cy - th / 2), size=(fx - x0, th),
                                 radius=[th / 2])
            if self.show_ticks and self.max > 0:
                Color(1, 1, 1, 0.22)
                step = tick_step(self.max)
                t = step
                while t < self.max:
                    tx = x0 + span * t / self.max
                    Line(points=[tx, cy + th / 2 + dp(2), tx, cy + th / 2 + dp(7)],
                         width=1)
                    t += step
            r = dp(11) if self.scrubbing else dp(8)   # knob grows while held
            Color(1, 1, 1, 1)
            Ellipse(pos=(fx - r, cy - r), size=(2 * r, 2 * r))
            Color(*self.accent)
            Ellipse(pos=(fx - r + dp(3), cy - r + dp(3)),
                    size=(2 * r - dp(6), 2 * r - dp(6)))

    # ── touch ─────────────────────────────────────────────────────────────
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or self.max <= 0:
            return False
        touch.grab(self)
        self.scrubbing = True
        self.value = self.value_at(touch.x)
        self.dispatch("on_scrub", self.value)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        self.value = self.value_at(touch.x)
        self.dispatch("on_scrub", self.value)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        self.value = self.value_at(touch.x)
        self.scrubbing = False
        self.dispatch("on_seek", self.value)
        return True

    def on_scrub(self, value):
        pass

    def on_seek(self, value):
        pass
