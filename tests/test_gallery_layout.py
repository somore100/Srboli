# tests/test_gallery_layout.py - xvfb-run -a python3 tests/test_gallery_layout.py  (kivy screens.)
# Gallery Sorter's controls must all stay visible on a narrow phone screen.
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
Window.size = (360, 740)
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.button import Button
from screens.gallery_sorter_screen import GallerySorterScreen

sc = GallerySorterScreen(name="gallery")
Window.add_widget(sc); sc.size = Window.size; Window.canvas.ask_update()
for _ in range(5): Clock.tick()

def buttons(w):
    for c in w.walk(restrict=True):
        if isinstance(c, Button) and c.text:
            yield c

seen = {b.text: b for b in buttons(sc)}
for need in ("+ Source", "Save cfg", "Load cfg", "Undo", "Commit (0)", "Rescan",
             "Rename", "Pick", "Create", "Albums", "< Prev", "Pass >", "Delete", "Back"):
    assert need in seen, f"missing button {need}"
    b = seen[need]
    assert b.width >= dp(36) and b.height >= dp(24), (need, b.size)
    assert b.x >= -1 and b.right <= Window.width + 1, (need, b.x, b.right)
assert sc._src_lbl.width >= dp(40), sc._src_lbl.width      # the source name is not squeezed out
assert sc._dest_in.width >= dp(80), sc._dest_in.width
print("gallery layout OK")
