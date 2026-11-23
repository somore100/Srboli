# tests/test_drawing_screen.py - xvfb-run -a python3 tests/test_drawing_screen.py  (kivy screens.)
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.core.window import Window
from screens.drawing_screen import DrawingScreen

class T:
    def __init__(self, x, y): self.pos = (x, y); self.x, self.y = x, y; self.grab_current = None
    def grab(self, w): self.grab_current = w
    def ungrab(self, w): self.grab_current = None

sc = DrawingScreen()
Window.add_widget(sc); sc.size = Window.size; Window.canvas.ask_update()
from kivy.clock import Clock
for _ in range(5): Clock.tick()
c = sc.canvas_w
assert c.width > 100 and c.height > 100, (c.size,)
x, y = c.x + 50, c.y + 50
t = T(x, y); c.on_touch_down(t)
t.pos = (x + 40, y + 10); c.on_touch_move(t); c.on_touch_up(t)
d = c.drawing
assert len(d.strokes) == 1 and len(d.strokes[0]["points"]) == 2
assert d.strokes[0]["points"][0] == (50, c.height - 50)           # top-left based
sc.set_tool("rect"); sc.toggle_fill(); assert c.filled
t2 = T(x + 100, y + 100); c.on_touch_down(t2); t2.pos = (x + 160, y + 140); c.on_touch_move(t2); c.on_touch_up(t2)
assert len(d.strokes) == 2 and d.strokes[1]["filled"]
sc.set_tool("eraser"); sc.set_color((255, 0, 0)); assert c.tool == "brush"
sc.undo(); assert len(d.strokes) == 1 and not sc.redo_btn.disabled
sc.redo(); sc.clear(); assert d.is_empty() and "Cleared" in sc.status.text
sc.undo(); assert not d.is_empty()
sc.bg_sp.text = "Black"; assert d.bg == (0, 0, 0)
sc.save(); assert "Saved:" in sc.status.text, sc.status.text
sc.size_slider.value = 20; assert c.brush == 20
print("drawing screen OK")
