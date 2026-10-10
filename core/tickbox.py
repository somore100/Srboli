# core/tickbox.py - a big, labelled on/off button with a CheckBox-style
# `.active` property.
#
# Why not kivy's CheckBox: it is a tiny 24dp square with no label, and on the
# phone the Randomizer's boxes could not be toggled at all. A tap that arrives
# twice (touch + synthesized mouse event) toggles a CheckBox on and straight
# back off. TickBox ignores a second toggle within 0.2 s, so one physical tap
# = exactly one change, and the whole label is the tap target.
#
# Text is plain ASCII ("[x]" / "[ ]") because Kivy's default font lacks the
# tick/box glyphs.

import time

from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.button import Button

_ON = (0.18, 0.5, 0.25, 1)
_OFF = (0.22, 0.22, 0.22, 1)


class TickBox(Button):
    active = BooleanProperty(False)
    label = StringProperty("")          # not `text`: that one we render

    def __init__(self, label="", active=False, **kw):
        kw.setdefault("size_hint_x", None)
        kw.setdefault("width", dp(84))
        kw.setdefault("font_size", 13)
        super().__init__(**kw)
        self._last_toggle = 0.0
        self.label = label
        self.active = active
        self.bind(active=self._refresh, label=self._refresh)
        self._refresh()

    def _refresh(self, *a):
        self.text = f"{'[x]' if self.active else '[ ]'} {self.label}"
        self.background_normal = ""
        self.background_down = ""
        self.background_color = _ON if self.active else _OFF

    def on_release(self):
        now = time.monotonic()
        if now - self._last_toggle < 0.2:
            return                       # duplicate event for the same tap
        self._last_toggle = now
        self.active = not self.active
