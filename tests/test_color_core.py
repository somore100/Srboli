# tests/test_color_core.py - python3 tests/test_color_core.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import color_core as c

assert c.parse_color("#1A2b3C") == (26, 43, 60) and c.parse_color("abc") == (170, 187, 204)
assert c.parse_color("rgb(1, 2, 3)") == (1, 2, 3) and c.parse_color("255 0 10") == (255, 0, 10)
assert c.parse_color("300,0,0") is None and c.parse_color("nope") is None and c.parse_color(None) is None
assert c.to_hex((255, 0, 10)) == "#FF000A"
assert c.rgb_to_hsl((255, 0, 0)) == (0, 100, 50) and c.rgb_to_hsl((0, 0, 255)) == (240, 100, 50)
assert c.rgb_to_hsl((128, 128, 128)) == (0, 0, 50)
for rgb in [(255, 0, 0), (12, 200, 99), (40, 40, 200), (250, 250, 5)]:
    back = c.hsl_to_rgb(*c.rgb_to_hsl(rgb))
    assert all(abs(a - b) <= 3 for a, b in zip(rgb, back)), (rgb, back)
assert round(c.contrast((0, 0, 0), (255, 255, 255))) == 21
assert c.readable_on((255, 255, 0)) == (0, 0, 0) and c.readable_on((10, 10, 80)) == (255, 255, 255)
assert c.formats((255, 128, 0))["HSL"] == "hsl(30, 100%, 50%)"
p = c.add_to_palette([], (1, 2, 3)); p = c.add_to_palette(p, (4, 5, 6)); p = c.add_to_palette(p, (1, 2, 3))
assert p == ["#010203", "#040506"]
assert len(c.add_to_palette(["#%06X" % i for i in range(40)], (9, 9, 9))) == c.MAX_PALETTE
from PIL import Image
im = Image.new("RGB", (4, 4), (10, 20, 30)); im.putpixel((2, 1), (200, 100, 50))
assert c.pixel(im, 2, 1) == (200, 100, 50) and c.pixel(im, 99, -5) == (10, 20, 30)
print("color core OK")
