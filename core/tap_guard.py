# core/tap_guard.py - ignore the ghost second press of a single physical tap.
#
# Recordings from the phone show a tapped file in the picker highlighting and
# un-highlighting, folders opening twice, toggles that don't stay toggled: the
# signature of one tap reaching a widget TWICE (the finger touch and the mouse
# event SDL synthesises from it; see core/touch_dedupe.py for the full story).
#
# touch_dedupe removes the duplicate at the input level, but it is opt-in
# because an earlier version was suspected of freezing the app. This guard is
# the conservative sibling: it lives inside ButtonBehavior (every Button,
# ToggleButton, Spinner, ...) and refuses the second press of the SAME widget.
# It only ever ignores something, so it cannot swallow the first tap.
#
# Two kinds of repeat:
#  * same input device, < TAP_WINDOW: a human can't repeat a tap that fast.
#  * the OTHER input device, < GHOST_WINDOW: that is the ghost. The longer
#    window matters because a ScrollView holds the real finger touch back for
#    scroll_timeout (350 ms in main.py) while the ghost goes straight through,
#    so the two presses can be 100-400 ms apart - too far for TAP_WINDOW.
#    Real taps all come from one device, so this never blocks fast tapping.
#
# Android only: on desktop a fast double-click is a real gesture.

import time

TAP_WINDOW = 0.15          # seconds, same device
GHOST_WINDOW = 0.6         # seconds, different device
_installed = False


def is_ghost(elapsed, device, last_device):
    """Is a press `elapsed` seconds after another one a ghost of it?"""
    if elapsed < TAP_WINDOW:
        return True
    return elapsed < GHOST_WINDOW and device != last_device


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
            dev = getattr(touch, "device", "")
            last = getattr(self, "_tg_last", None)
            if (last is not None and self.collide_point(*touch.pos)
                    and is_ghost(now - last[0], dev, last[1])):
                return True                     # ghost: swallow it
        except Exception:
            return orig_down(self, touch)
        handled = orig_down(self, touch)
        if handled:
            self._tg_last = (now, dev)
        return handled

    ButtonBehavior.on_touch_down = on_touch_down
    _installed = True
