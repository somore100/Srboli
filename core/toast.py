# core/toast.py - a small message at the bottom of the window that fades away.
# Safe to call from any thread; at most one is shown per THROTTLE seconds.
import time

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.label import Label

THROTTLE = 2.0
_last = [0.0]


def toast(text, seconds=3.0):
    now = time.monotonic()
    if now - _last[0] < THROTTLE:
        return
    _last[0] = now
    Clock.schedule_once(lambda dt: _show(str(text), seconds))


def _show(text, seconds):
    lbl = Label(text=text, font_size=sp(12), size_hint=(None, None),
                padding=(dp(12), dp(8)), halign="center")
    lbl.texture_update()
    lbl.size = (min(lbl.texture_size[0] + dp(24), Window.width - dp(24)),
                lbl.texture_size[1] + dp(16))
    lbl.pos = ((Window.width - lbl.width) / 2, dp(24))
    with lbl.canvas.before:
        Color(0.1, 0.1, 0.12, 0.92)
        box = RoundedRectangle(pos=lbl.pos, size=lbl.size, radius=[dp(8)])
    lbl.bind(pos=lambda w, v: setattr(box, "pos", v))
    Window.add_widget(lbl)
    Clock.schedule_once(lambda dt: Window.remove_widget(lbl), seconds)
