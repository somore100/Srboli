# core/keyboard_inset.py - keep the on-screen keyboard from covering a text box.
#
# Kivy's SDL2 Android build reports keyboard_height as 0 and, with the default
# softinput_mode, leaves the window alone - so a box in the bottom row of a screen
# (the "Your answer" box in Learn, "Your next step" in Math Steps) sits behind the
# keyboard: you type blind and the text only shows once Check hides the keyboard.
# KeyboardLift asks Android how tall the keyboard is and pads the screen's bottom by
# that much while one of its boxes has focus. Off Android it does nothing.
from kivy.clock import Clock
from kivy.utils import platform

POLL = 0.15


def ime_height_px():
    """Height of the on-screen keyboard in pixels (0 when hidden, unknown or off Android)."""
    if platform != "android":
        return 0
    try:
        from jnius import autoclass
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        decor = act.getWindow().getDecorView()
        if autoclass("android.os.Build$VERSION").SDK_INT >= 30:
            insets = decor.getRootWindowInsets()
            kinds = autoclass("android.view.WindowInsets$Type")
            if insets is None:
                return 0
            ime = insets.getInsets(kinds.ime()).bottom
            nav = insets.getInsets(kinds.navigationBars()).bottom
            return max(0, ime - nav)
        rect = autoclass("android.graphics.Rect")()
        decor.getWindowVisibleDisplayFrame(rect)
        return max(0, decor.getRootView().getHeight() - rect.bottom
                   - KeyboardLift.nav_guess)
    except Exception:
        return 0


class KeyboardLift:
    """Pad `root`'s bottom by the keyboard height while a watched TextInput is focused."""
    nav_guess = 0

    def __init__(self, root, height_fn=ime_height_px):
        self.root = root
        self.height_fn = height_fn
        self.base = list(root.padding)
        self._inputs = []
        self._ev = None

    def watch(self, *inputs):
        for ti in inputs:
            self._inputs.append(ti)
            ti.bind(focus=self._on_focus)

    def _on_focus(self, *a):
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, POLL)
        self._tick(0)

    def _focused(self):
        return any(t.focus for t in self._inputs)

    def _tick(self, dt):
        h = self.height_fn() if self._focused() or self.root.padding[3] > self.base[3] else 0
        want = self.base[:3] + [self.base[3] + h]
        if list(self.root.padding) != want:
            self.root.padding = want
        if not self._focused() and h == 0:
            if self._ev is not None:
                self._ev.cancel()
                self._ev = None
            return False
        return True
