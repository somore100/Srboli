# core/tap_slop.py - a finger that travels is not tapping.
#
# Kivy's ScrollView hands a touch to the button under it when the finger has
# not moved far enough within scroll_timeout. If the finger then keeps
# dragging (a slow scroll), the button still counted the lift as a click as
# long as it ended on a button. Here every ButtonBehavior remembers the
# touch moved further than SLOP, and swallows the release: no click.
import math

from kivy.metrics import dp


def moved(touch, slop):
    """True once the touch is more than `slop` pixels from where a button
    first received it (installed buttons record that spot)."""
    from kivy.core.window import Window
    origin = touch.ud.get("_slop_o")
    if origin is None:
        return False
    return math.hypot((touch.sx - origin[0]) * Window.width,
                      (touch.sy - origin[1]) * Window.height) > slop


def install(slop=None):
    from kivy.uix.behaviors.button import ButtonBehavior
    from kivy.uix.behaviors.togglebutton import ToggleButtonBehavior
    if getattr(ButtonBehavior, "_slop_installed", False):
        return
    limit = slop if slop is not None else dp(10)
    orig_down = ButtonBehavior.on_touch_down
    orig_move, orig_up = ButtonBehavior.on_touch_move, ButtonBehavior.on_touch_up

    def on_touch_down(self, touch):
        r = orig_down(self, touch)
        if self in touch.ud:
            touch.ud.setdefault("_slop_o", (touch.sx, touch.sy))
        return r

    def on_touch_move(self, touch):
        if touch.grab_current is self and self in touch.ud and moved(touch, limit):
            touch.ud.setdefault("_slop", set()).add(id(self))
            if not isinstance(self, ToggleButtonBehavior):
                self.state = "normal"
        return orig_move(self, touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self and id(self) in touch.ud.get("_slop", ()):
            touch.ungrab(self)
            return True                 # dragged: not a click
        return orig_up(self, touch)

    ButtonBehavior.on_touch_down = on_touch_down
    ButtonBehavior.on_touch_move = on_touch_move
    ButtonBehavior.on_touch_up = on_touch_up
    ButtonBehavior._slop_installed = True
