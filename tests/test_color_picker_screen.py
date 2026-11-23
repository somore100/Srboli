# tests/test_color_picker_screen.py - xvfb-run -a python3 tests/test_color_picker_screen.py  (kivy screens.)
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from screens.color_picker_screen import ColorPickerScreen, PickerImage
from core import color_core as core

sc = ColorPickerScreen()
sc.palette = []
sc.hex_in.text = "#336699"
sc._from_text()
assert sc.rgb == (0x33, 0x66, 0x99) and [int(s.value) for s in sc.sliders] == [0x33, 0x66, 0x99]
sc.sliders[0].value = 255
assert sc.rgb == (255, 0x66, 0x99) and sc.hex_in.text == "#FF6699"
sc.hex_in.text = "garbage"; sc._from_text()
assert sc.rgb == (255, 0x66, 0x99) and "Not a colour" in sc.status.text
sc.save_color(); assert sc.palette == ["#FF6699"]
sc.clear_palette(); assert sc.palette == [] and not sc.grid.children
from PIL import Image
im = Image.new("RGB", (10, 10), (1, 2, 3)); im.putpixel((3, 4), (9, 8, 7))
got = []
pi = PickerImage(im, got.append)
assert pi.texture.size == (10, 10)
pi.pos, pi.size = (0, 0), (100, 100)
class T: pass
t = T(); t.x, t.y = 35, 55            # pixel column 3, row 4 (y counts from the bottom)
assert pi._pixel_at(t) == (9, 8, 7), pi._pixel_at(t)
print("color picker screen OK")
