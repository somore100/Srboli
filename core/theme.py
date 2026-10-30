# core/theme.py - colours, spacing and one flat look for every widget.
#
# theme.install() (called from main.py before any screen is built) sets the
# window colour and loads global KV rules: every Button / TextInput / Popup in
# the app gets the flat look without touching the screens. A colour a screen
# passes in Python (background_color=...) still wins over the rule's value.
# Dark theme only for now; to add a light one later, turn the tokens into
# ColorProperty values on an EventDispatcher so the KV bindings update live.
from kivy.lang import Builder
from kivy.metrics import dp, sp

BG       = (0.08, 0.09, 0.11, 1)
SURFACE  = (0.13, 0.14, 0.17, 1)
SURFACE2 = (0.19, 0.20, 0.24, 1)
TEXT     = (0.93, 0.94, 0.96, 1)
MUTED    = (0.62, 0.65, 0.71, 1)
ACCENT   = (0.30, 0.62, 0.95, 1)
DANGER   = (0.80, 0.28, 0.28, 1)
SUCCESS  = (0.28, 0.66, 0.42, 1)

PAD   = {"xs": dp(4), "s": dp(8), "m": dp(12), "l": dp(16), "xl": dp(24)}
FONT  = {"small": sp(12), "body": sp(14), "title": sp(18), "h1": sp(26)}
MAX_CONTENT_W = dp(900)

KV = """
#:import T core.theme
<Button>:
    background_normal: ''
    background_down: ''
    background_disabled_normal: ''
    background_color: T.SURFACE2
    color: T.TEXT
    canvas.after:
        Color:
            rgba: (1, 1, 1, 0.10 if self.state == 'down' else 0)
        Rectangle:
            pos: self.pos
            size: self.size

<TextInput>:
    background_normal: ''
    background_active: ''
    background_color: T.SURFACE
    foreground_color: T.TEXT
    hint_text_color: T.MUTED
    cursor_color: T.ACCENT
    padding: [T.PAD['m'], T.PAD['s']]

<Popup>:
    separator_color: T.ACCENT
    title_size: T.FONT['title']
"""

_installed = False


def install():
    global _installed
    if _installed:
        return
    from kivy.core.window import Window
    Window.clearcolor = BG
    Builder.load_string(KV)
    _installed = True
