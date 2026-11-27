# tests/test_plotter_toolbar.py - xvfb-run -a python3 tests/test_plotter_toolbar.py  (kivy screens.)
# Function Plotter's two toolbar rows must fit a narrow phone: no button squeezed to
# nothing, every row inside the window, long labels cut with "..." not spilled over.
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.core.window import Window
Window.size = (360, 740)
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from kivy.metrics import dp
from kivy.uix.button import Button
import screens.function_plotter_screen as fp

scr = fp.FunctionPlotterScreen(name="plotter")
Window.add_widget(scr); scr.size = Window.size
for _ in range(6): EventLoop.idle()

rows = []
for w in scr.walk():
    kids = [c for c in w.children if isinstance(c, Button)]
    if len(kids) >= 6 and abs(w.height - dp(44)) < 1:
        rows.append(w)
assert len(rows) >= 2, f"found {len(rows)} toolbar rows"
for row in rows[:2]:
    for b in row.children:
        assert b.width >= dp(28), (b.text, b.width)               # nobody squeezed out
        assert b.x >= -1 and b.right <= Window.width + 1, (b.text, b.x, b.right)
        assert b.shorten, b.text                                    # overflow is cut, not drawn over a neighbour
        assert b.texture_size[0] <= b.width + 1, (b.text, b.texture_size, b.width)
print("plotter toolbar OK")
