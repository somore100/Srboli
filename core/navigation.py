# core/navigation.py - moving between screens without a frozen, dead-looking UI.
#
# * open_screen: a screen that still has to be built shows a small "Loading..."
#   screen first, and is built on the next frame, so the tap that opened it
#   visibly did something (users used to tap again, and that second tap landed
#   on the new screen).
# * GuardedScreenManager ignores touches for a moment after every switch.
# * install_keys: Ctrl+K = search, Esc / Android back = go back.
import os
import time

from kivy.clock import Clock
from kivy.metrics import sp
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import Screen, ScreenManager

GRACE = 0.2          # seconds of ignored touches after a screen switch
LOADING = "_loading"


class GuardedScreenManager(ScreenManager):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._switched = 0.0
        self.bind(current=self._stamp)

    def _stamp(self, *a):
        self._switched = time.monotonic()

    def on_touch_down(self, touch):
        if time.monotonic() - self._switched < GRACE:
            return True
        return super().on_touch_down(touch)


LOADING_STYLE = "none"     # "none" (default: nothing shown) | "text" | "logo"  (Settings; set by main.py)


def _loading_screen(style="logo"):
    """What shows while a tool is built: the logo and "Loading..." on the
    theme's own background (a white or bright screen flashed against the dark
    app), or just text."""
    from core import theme
    scr = Screen(name=LOADING)
    with scr.canvas.before:
        Color(*theme.BG)
        bg = Rectangle(pos=scr.pos, size=scr.size)
    scr.bind(pos=lambda w, v: setattr(bg, "pos", v),
             size=lambda w, v: setattr(bg, "size", v))
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "loading.png")
    box = BoxLayout(orientation="vertical", padding=sp(40), spacing=sp(12))
    if style == "logo" and os.path.isfile(path):
        box.add_widget(Image(source=path, fit_mode="contain"))
        box.add_widget(Label(text="Loading...", font_size=sp(18),
                             color=theme.MUTED, size_hint_y=None, height=sp(30)))
    else:
        box.add_widget(Label(text="Loading...", font_size=sp(18),
                             color=theme.MUTED))
    scr.add_widget(box)
    return scr


def open_screen(sm, route, ensure, after=None, delay=0.05):
    """Show `route`, building it first if needed. ensure(route) -> bool builds
    it; after(route) runs once it is on screen."""
    if sm.has_screen(route):
        sm.current = route
        if after:
            after(route)
        return
    back = sm.current
    if LOADING_STYLE != "none":              # "none": stay put until it is built
        if not sm.has_screen(LOADING):
            sm.add_widget(_loading_screen(LOADING_STYLE))
        sm.current = LOADING

    def finish(dt):
        try:
            ok = ensure(route)
        except Exception as e:
            print(f"opening {route} failed: {e}")
            ok = False
        sm.current = route if ok and sm.has_screen(route) else back
        if ok and after:
            after(route)

    Clock.schedule_once(finish, delay)


def _modal_open(Window):
    return any(isinstance(w, ModalView) for w in Window.children)


def install_keys(Window, sm, focus_search, on_back_at_home=None):
    """Ctrl+K: dashboard + search box. Esc or Android back: leave the current
    tool for the dashboard (on the dashboard itself back may quit, Android)."""
    def on_keyboard(win, key, scancode, codepoint, modifiers):
        if _modal_open(win):
            return False                      # a popup handles its own Esc
        if key == 107 and "ctrl" in modifiers:            # Ctrl+K
            if sm.current != "dashboard":
                sm.current = "dashboard"
            Clock.schedule_once(lambda dt: focus_search(), 0.05)
            return True
        if key == 27:                                      # Esc / back
            if sm.current not in ("dashboard", LOADING):
                sm.current = "dashboard"
                return True
            if sm.current == "dashboard" and on_back_at_home:
                return bool(on_back_at_home())
        return False

    Window.bind(on_keyboard=on_keyboard)
    return on_keyboard
