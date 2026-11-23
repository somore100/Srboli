# core/color_core.py - colour maths and the saved palette for the Colour Picker. Pure Python
# (Pillow only for grabbing the screen / reading a picture).
import os
import re

import app_data
from core.jsonio import read_json, write_json_atomic

MAX_PALETTE = 24


def parse_color(text):
    """'#1a2b3c', '1a2b3c', '#abc', 'rgb(1, 2, 3)' or '1,2,3' -> (r, g, b) or None."""
    t = (text or "").strip().lower()
    m = re.fullmatch(r"#?([0-9a-f]{6})", t)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"#?([0-9a-f]{3})", t)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.fullmatch(r"(?:rgb\()?\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*\)?", t)
    if m:
        rgb = tuple(int(x) for x in m.groups())
        if all(0 <= v <= 255 for v in rgb):
            return rgb
    return None


def to_hex(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


def rgb_to_hsl(rgb):
    """(h 0-360, s 0-100, l 0-100), rounded."""
    r, g, b = (v / 255 for v in rgb)
    hi, lo = max(r, g, b), min(r, g, b)
    l = (hi + lo) / 2
    d = hi - lo
    if d == 0:
        h = s = 0.0
    else:
        s = d / (1 - abs(2 * l - 1))
        if hi == r:
            h = ((g - b) / d) % 6
        elif hi == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h *= 60
    return round(h) % 360, round(s * 100), round(l * 100)


def hsl_to_rgb(h, s, l):
    s, l = s / 100, l / 100
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h % 360 // 60)]
    return tuple(round((v + m) * 255) for v in (r, g, b))


def _lin(v):
    v /= 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio, 1 to 21."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_on(rgb):
    """Black or white, whichever reads better on this colour."""
    return (0, 0, 0) if contrast(rgb, (0, 0, 0)) >= contrast(rgb, (255, 255, 255)) else (255, 255, 255)


def formats(rgb):
    h, s, l = rgb_to_hsl(rgb)
    return {"HEX": to_hex(rgb),
            "RGB": "rgb(%d, %d, %d)" % tuple(rgb),
            "HSL": "hsl(%d, %d%%, %d%%)" % (h, s, l)}


# ---------- picking ----------
def pixel(img, x, y):
    """(r, g, b) of one pixel of a PIL image, clamped to the picture."""
    x = max(0, min(img.width - 1, int(x)))
    y = max(0, min(img.height - 1, int(y)))
    return tuple(img.convert("RGB").getpixel((x, y)))


def grab_screen():
    """(PIL image, error). Works on Windows, macOS and X11; not on Wayland or Android."""
    try:
        from PIL import ImageGrab
        return ImageGrab.grab().convert("RGB"), ""
    except Exception as e:
        return None, ("Could not capture the screen here (" + str(e).split("\n")[0][:80] +
                      "). Wayland and Android do not allow it: use a picture instead.")


def open_picture(path):
    try:
        from PIL import Image
        return Image.open(path).convert("RGB"), ""
    except Exception as e:
        return None, f"Could not open that picture: {e}"


# ---------- palette ----------
def _path():
    return os.path.join(app_data.subdir("config"), "color_palette.json")


def load_palette():
    out = []
    for t in read_json(_path(), {}).get("colors", []):
        c = parse_color(t if isinstance(t, str) else "")
        if c:
            out.append(to_hex(c))
    return out[:MAX_PALETTE]


def save_palette(colors):
    try:
        write_json_atomic(_path(), {"colors": list(colors)[:MAX_PALETTE]})
    except Exception:
        pass


def add_to_palette(colors, rgb):
    """New list: the colour first, no duplicate, capped."""
    h = to_hex(rgb)
    return ([h] + [c for c in colors if c != h])[:MAX_PALETTE]
