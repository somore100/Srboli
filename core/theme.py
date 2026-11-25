# core/theme.py - colours, spacing and one flat look for every widget.
#
# theme.install() (called from main.py before any screen is built) sets the
# window colour and loads global KV rules: every Button / TextInput / Popup in
# the app gets the flat look without touching the screens. A colour a screen
# passes in Python (background_color=...) still wins over the rule's value.
# Themes are presets of the colour tokens below. The chosen one (Settings ->
# "theme") is applied once at startup by install(), before any screen is
# built, so a change needs a restart.
import os

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

# ── custom colours ───────────────────────────────────────────────────────────
# Five colours the user picks ("#rrggbb"); the muted text colour is mixed from text and
# background, danger / success stay as they are.
CUSTOM_FIELDS = [("BG", "Background"), ("SURFACE", "Panels"), ("SURFACE2", "Buttons"),
                 ("TEXT", "Text"), ("ACCENT", "Accent")]


def parse_hex(text):
    """'#rgb' / '#rrggbb' (the # is optional) -> (r, g, b, 1) floats, or None."""
    t = str(text or "").strip().lstrip("#")
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) != 6:
        return None
    try:
        v = [int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return None
    return (v[0], v[1], v[2], 1)


def to_hex(rgba):
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in rgba[:3])


def mix(a, b, t):
    """Colour a moved fraction t of the way to colour b."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3)) + (1,)


def _lum(c):
    def f(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    """WCAG contrast ratio, 1 (none) to 21."""
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def clean_custom(d):
    """Only valid colours, stored as lowercase '#rrggbb'."""
    out = {}
    for key, _label in CUSTOM_FIELDS:
        c = parse_hex((d or {}).get(key)) if isinstance(d, dict) else None
        if c:
            out[key] = to_hex(c)
    return out


def custom_preset(hexes):
    base = PRESETS["dark"]
    hexes = clean_custom(hexes)
    p = dict(base)
    for key, _label in CUSTOM_FIELDS:
        if key in hexes:
            p[key] = parse_hex(hexes[key])
    p["MUTED"] = mix(p["TEXT"], p["BG"], 0.4)
    p["label"] = "Custom colours"
    return p


def set_custom(hexes):
    PRESETS["custom"] = custom_preset(hexes)

# Rounded buttons: a white rounded-rectangle picture, tinted by each button's
# background_color (so screens that pass their own colour stay rounded).
ROUND_PNG = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "round.png")
BTN_IMG = ""            # set by apply_shape()
BTN_BORDER = (0, 0, 0, 0)
BTN_RADIUS = 0
POPUP_IMG = "atlas://data/images/defaulttheme/modalview-background"
POPUP_BORDER = (16, 16, 16, 16)
POPUP_TINT = (1, 1, 1, 1)
rounded = True


def apply_shape(on):
    """Rounded (True) or flat square (False) buttons."""
    global BTN_IMG, BTN_BORDER, BTN_RADIUS, POPUP_IMG, POPUP_BORDER, rounded
    rounded = bool(on) and os.path.isfile(ROUND_PNG)
    BTN_IMG = ROUND_PNG if rounded else ""
    BTN_BORDER = (18, 18, 18, 18) if rounded else (0, 0, 0, 0)
    BTN_RADIUS = dp(10) if rounded else 0
    POPUP_IMG = ROUND_PNG if rounded else "atlas://data/images/defaulttheme/modalview-background"
    POPUP_BORDER = (18, 18, 18, 18) if rounded else (16, 16, 16, 16)
    return rounded


def saved_rounded():
    try:
        from screens.settings_screen import _raw_settings
        return bool(_raw_settings().get("rounded", True))
    except Exception:
        return True


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


def saved_custom():
    try:
        from screens.settings_screen import _raw_settings
        return clean_custom(_raw_settings().get("custom_colors"))
    except Exception:
        return {}


def saved_name():
    try:
        from screens.settings_screen import _raw_settings
        return _raw_settings().get("theme", DEFAULT_THEME)
    except Exception:
        return DEFAULT_THEME


PAD   = {"xs": dp(4), "s": dp(8), "m": dp(12), "l": dp(16), "xl": dp(24)}
FONT  = {"small": sp(12), "body": sp(14), "title": sp(18), "h1": sp(26)}
MAX_CONTENT_W = dp(1500)     # wide windows get more tile columns, not empty margins

KV = """
#:import T core.theme
<Label>:
    color: T.TEXT

<Button>:
    background_normal: T.BTN_IMG
    background_down: T.BTN_IMG
    background_disabled_normal: T.BTN_IMG
    border: T.BTN_BORDER
    background_color: T.SURFACE2
    color: T.TEXT
    canvas.after:
        Color:
            rgba: (1, 1, 1, 0.10 if self.state == 'down' else 0)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [T.BTN_RADIUS]

<TextInput>:
    background_normal: T.BTN_IMG
    background_active: T.BTN_IMG
    border: T.BTN_BORDER
    background_color: T.SURFACE
    foreground_color: T.TEXT
    hint_text_color: T.MUTED
    cursor_color: T.ACCENT
    padding: [T.PAD['m'], T.PAD['s']]

<Popup>:
    background: T.POPUP_IMG
    border: T.POPUP_BORDER
    background_color: T.SURFACE if T.rounded else (1, 1, 1, 1)
    separator_color: T.ACCENT
    title_size: T.FONT['title']
"""

_installed = False


def install():
    global _installed
    if _installed:
        return
    set_custom(saved_custom())
    apply(saved_name())
    apply_shape(saved_rounded())
    from kivy.core.window import Window
    Window.clearcolor = BG
    Builder.load_string(KV)
    _installed = True


PRESETS["custom"] = custom_preset({})
