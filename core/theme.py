# core/theme.py - colours, spacing and one flat look for every widget.
#
# theme.install() (called from main.py before any screen is built) sets the
# window colour and loads global KV rules: every Button / TextInput / Popup in
# the app gets the flat look without touching the screens. A colour a screen
# passes in Python (background_color=...) still wins over the rule's value.
# Themes are presets of the colour tokens below. The chosen one (Settings ->
# "theme") is applied once at startup by install(), before any screen is
# built, so a change needs a restart.
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

PRESETS = {
    "dark": {"label": "Dark (default)", "BG": BG, "SURFACE": SURFACE,
             "SURFACE2": SURFACE2, "TEXT": TEXT, "MUTED": MUTED,
             "ACCENT": ACCENT, "DANGER": DANGER, "SUCCESS": SUCCESS},
    "blue": {"label": "Blue", "BG": (0.05, 0.09, 0.16, 1),
             "SURFACE": (0.09, 0.15, 0.26, 1), "SURFACE2": (0.14, 0.23, 0.38, 1),
             "TEXT": (0.92, 0.95, 1.0, 1), "MUTED": (0.60, 0.69, 0.83, 1),
             "ACCENT": (0.35, 0.72, 1.0, 1), "DANGER": DANGER, "SUCCESS": SUCCESS},
    "light": {"label": "Yellow & white", "BG": (0.99, 0.97, 0.88, 1),
              "SURFACE": (1.0, 1.0, 1.0, 1), "SURFACE2": (0.96, 0.88, 0.55, 1),
              "TEXT": (0.13, 0.12, 0.10, 1), "MUTED": (0.42, 0.40, 0.33, 1),
              "ACCENT": (0.80, 0.55, 0.0, 1), "DANGER": (0.78, 0.20, 0.20, 1),
              "SUCCESS": (0.20, 0.55, 0.30, 1)},
}
DEFAULT_THEME = "dark"
current = DEFAULT_THEME


def apply(name):
    """Switch the colour tokens to preset `name` (unknown -> default)."""
    global current
    if name not in PRESETS:
        name = DEFAULT_THEME
    g = globals()
    for key, value in PRESETS[name].items():
        if key != "label":
            g[key] = value
    current = name
    return name


def saved_name():
    try:
        from screens.settings_screen import _raw_settings
        return _raw_settings().get("theme", DEFAULT_THEME)
    except Exception:
        return DEFAULT_THEME


PAD   = {"xs": dp(4), "s": dp(8), "m": dp(12), "l": dp(16), "xl": dp(24)}
FONT  = {"small": sp(12), "body": sp(14), "title": sp(18), "h1": sp(26)}
MAX_CONTENT_W = dp(900)

KV = """
#:import T core.theme
<Label>:
    color: T.TEXT

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
    apply(saved_name())
    from kivy.core.window import Window
    Window.clearcolor = BG
    Builder.load_string(KV)
    _installed = True
