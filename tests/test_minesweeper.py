# tests/test_minesweeper.py - needs a display (xvfb-run -a python3 tests/test_minesweeper.py)
import os, sys, tempfile, time, random
os.environ["KIVY_NO_ARGS"]="1"; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop; EventLoop.ensure_window()
from kivy.clock import Clock
import app_data; app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from kivy.uix.screenmanager import ScreenManager
from kivy.core.window import Window
from screens.minesweeper_screen import MinesweeperScreen, LEVELS
sm=ScreenManager(); s=MinesweeperScreen(name="minesweeper"); sm.add_widget(s); Window.add_widget(sm)
for _ in range(5): Clock.tick()
random.seed(3)
# flag first must NOT place mines
s.cell_long_press(0,0); print("mines placed after flag:", s._mines_placed, "| counter:", s._mine_lbl.text)
s.cell_long_press(0,0)
s.cell_tap(4,4)
mines=sum(row.count(-1) for row in s.board); print("mines:", mines, "(want 10) | first cell safe:", s.board[4][4]!=-1, "| zero opening:", s.board[4][4]==0, "| revealed:", sum(sum(r) for r in s.revealed))
# square cells
sizes={tuple(round(v) for v in b.size) for row in s._cells for b in row}; print("cell sizes (square):", sizes, "grid:", tuple(round(v) for v in s._grid.size))
# play to win by revealing every safe cell
for r in range(s.rows):
    for c in range(s.cols):
        if s.board[r][c]!=-1 and not s.revealed[r][c]: s.cell_tap(r,c)
print("won:", s._over, "|", s._status.text, "| scores file:", open(s._scores_path()).read())
# lose + wrong flag
s._new_game(); s.cell_tap(0,0)
mr=[(r,c) for r in range(9) for c in range(9) if s.board[r][c]==-1][0]
safe=[(r,c) for r in range(9) for c in range(9) if s.board[r][c]!=-1 and not s.revealed[r][c]][0]
s.cell_long_press(*safe); s.cell_tap(*mr); print("lost:", s._over, "| wrong flag shown as:", s._cells[safe[0]][safe[1]].text, "| mine cell:", s._cells[mr[0]][mr[1]].text, "|", s._status.text)
# chord
s._new_game(); s.cell_tap(4,4)
num=[(r,c) for r in range(9) for c in range(9) if s.revealed[r][c] and s.board[r][c]>0][0]
for nr,nc in s._neighbours(*num):
    if s.board[nr][nc]==-1: s.cell_long_press(nr,nc)
before=sum(sum(r) for r in s.revealed); s.cell_tap(*num); print("chord revealed more:", sum(sum(r) for r in s.revealed)>before, "| over:", s._over)
# levels + timer pause
s._set_level("Hard"); print("hard grid:", s.rows, s.cols, len(s._cells), len(s._cells[0]), s._mine_lbl.text)
s.cell_tap(8,8); time.sleep(.5); Clock.tick(); Clock.tick(); s.on_leave(); e=s._elapsed; time.sleep(.4); print("timer paused while away:", abs(s._elapsed-e)<0.01, "| elapsed>=0.5:", e>=0.5)
print("OK")
