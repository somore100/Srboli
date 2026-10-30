# tests/test_chess.py - core rules need no display; the screen part needs one
# (xvfb-run -a python3 tests/test_chess.py). Core part runs alone with --core.
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.chess_core import Position, best_move

def perft(p, d):
    return 1 if d == 0 else sum(perft(p.play(m), d - 1) for m in p.legal_moves())

assert [perft(Position(), d) for d in (1, 2, 3)] == [20, 400, 8902]
kiwi = Position(list("r...k..r" "p.ppqpb." "bn..pnp." "...PN..." ".p..P..." "..N..Q.p" "PPPBBPPP" "R...K..R"), "w", "KQkq")
assert [perft(kiwi, d) for d in (1, 2)] == [48, 2039]
p = Position()
for f, t in ((53, 45), (12, 28), (54, 38), (3, 39)):
    p = p.play((f, t, ""))
assert p.status() == "checkmate"
assert best_move(Position(), 2) in Position().legal_moves()
print("core OK")
if "--core" in sys.argv:
    sys.exit(0)

os.environ["KIVY_NO_ARGS"] = "1"
from kivy.base import EventLoop; EventLoop.ensure_window()
from kivy.clock import Clock
import app_data; app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from kivy.uix.screenmanager import ScreenManager
from kivy.core.window import Window
from screens.chess_screen import ChessScreen
sm = ScreenManager(); s = ChessScreen(name="chess"); sm.add_widget(s); Window.add_widget(sm)
for _ in range(5): Clock.tick()
s.level = "Easy"
s._tap(52); assert len(s.targets) == 2, s.targets          # e2 -> e3/e4
s._tap(36)
assert s.game.turn == "b" and s._thinking
t0 = time.time()
while s._thinking and time.time() - t0 < 10:
    Clock.tick(); time.sleep(0.01)
assert s.game.turn == "w" and len(s.history) == 2, (s.game.turn, len(s.history))
s._undo(); assert len(s.history) == 0 and s.game.turn == "w"
s._toggle_mode(); s._tap(52); s._tap(36); assert s._flipped() and s._cells
print("screen OK")
