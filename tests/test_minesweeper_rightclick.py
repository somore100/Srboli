# tests/test_minesweeper_rightclick.py - needs a display (xvfb-run -a ...)
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import screens.minesweeper_screen as ms
scr = ms.MinesweeperScreen()
from kivy.core.window import Window
Window.add_widget(scr)
for _ in range(5): EventLoop.idle()
cell = scr._cells[0][0]
class T:
    def __init__(self, button): self.button = button; self.pos = cell.center; self.x, self.y = cell.center; self.grab_current = None
    def grab(self, w): self.grab_current = w
    def ungrab(self, w): self.grab_current = None
t = T("right")
assert cell.on_touch_down(t) is True
assert scr.flagged[0][0] and cell._flag_drawn and not scr.revealed[0][0]
assert cell.on_touch_up(t) is True
assert scr.flagged[0][0]                       # release must not reveal / unflag
t = T("right"); cell.on_touch_down(t); cell.on_touch_up(t)
assert not scr.flagged[0][0] and not cell._flag_drawn      # second right click unflags
print("minesweeper right-click OK")
