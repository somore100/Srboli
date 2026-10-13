# core/tap_guard.py - ignore the ghost second press of a single physical tap.
#
# Recordings from the phone show a tapped file in the picker highlighting and
# un-highlighting, folders opening twice, toggles that don't stay toggled: the
# signature of one tap reaching a widget TWICE a few milliseconds apart (the
# finger touch and the mouse event SDL synthesises from it; see
# core/touch_dedupe.py for the full story).
#
# touch_dedupe removes the duplicate at the input level, but it is opt-in
# because an earlier version was suspected of freezing the app. This guard is
# the conservative sibling: it lives inside ButtonBehavior (every Button,
# ToggleButton, Spinner, ...) and simply refuses a second press of the SAME
# widget within TAP_WINDOW seconds. It only ever ignores something, so it can
# make a legitimate 8-taps-per-second mash on one button a little less
# sensitive, but it cannot swallow the first tap or freeze anything.
#
# Android only: on desktop a fast double-click is a real gesture.

import time

TAP_WINDOW = 0.15          # seconds; a human can't repeat a tap faster
_installed = False


def install():
    global _installed
    if _installed:
        return
    from kivy.uix.behaviors.button import ButtonBehavior
    orig_down = ButtonBehavior.on_touch_down

    def on_touch_down(self, touch):
        try:
            if getattr(touch, "is_mouse_scrolling", False):
                return orig_down(self, touch)
            now = time.monotonic()
            if (now - getattr(self, "_tg_last", 0.0) < TAP_WINDOW
                    and self.collide_point(*touch.pos)):
                return True                     # ghost: swallow it
        except Exception:
            return orig_down(self, touch)
        handled = orig_down(self, touch)
        if handled:
            self._tg_last = now
        return handled

    ButtonBehavior.on_touch_down = on_touch_down
    _installed = True
