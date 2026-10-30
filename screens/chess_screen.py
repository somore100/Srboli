# screens/chess_screen.py
#
# Chess: play the built-in AI (you are White) or pass-and-play two players.
# Rules + AI live in core/chess_core.py (pure Python, unit-tested).
#   - Pieces are drawn as letters (K Q R B N P): Kivy's default Roboto has no
#     chess glyphs, same reason Minesweeper avoids emoji.
#   - Tap a piece, then a highlighted square. Tapping another own piece
#     re-selects. Pawn promotion is automatic (queen).
#   - The AI searches in a worker thread so the UI never freezes.
#   - Undo takes back one move (two against the AI). The board flips for
#     Black in two-player mode so each side plays from their own end.

import threading

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.metrics import dp, sp
from kivy.clock import Clock

from core import chess_core as cc

LEVELS = {"Easy": 0, "Medium": 2, "Hard": 3}      # name -> search depth
LEVEL_ORDER = ("Easy", "Medium", "Hard")

LIGHT = (0.86, 0.80, 0.66, 1)
DARK = (0.48, 0.36, 0.26, 1)
SELECT = (0.95, 0.85, 0.25, 1)
TARGET_L = (0.55, 0.78, 0.45, 1)
TARGET_D = (0.35, 0.60, 0.30, 1)
LAST_L = (0.80, 0.80, 0.45, 1)
LAST_D = (0.62, 0.58, 0.28, 1)
CHECK = (0.90, 0.25, 0.25, 1)
WHITE_PIECE = (1, 1, 1, 1)
BLACK_PIECE = (0.05, 0.05, 0.05, 1)


class ChessScreen(Screen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self.level = "Medium"
        self.vs_ai = True
        self._cells = {}          # square index -> Button
        self._gen = 0             # bumped on new game / undo: drops stale AI
        self._thinking = False
        self._new_state()

        root = BoxLayout(orientation="vertical", padding=dp(6),
                         spacing=dp(6))

        top = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self._mode_btn = Button(text="Vs: AI", font_size=sp(13))
        self._mode_btn.bind(on_release=self._toggle_mode)
        self._lvl_btn = Button(text=f"Level: {self.level}", font_size=sp(13))
        self._lvl_btn.bind(on_release=self._cycle_level)
        for w in (self._mode_btn, self._lvl_btn):
            top.add_widget(w)
        root.add_widget(top)

        self._status = Label(text="", font_size=sp(14), size_hint_y=None,
                             height=dp(28), color=(0.7, 0.9, 1, 1))
        root.add_widget(self._status)

        self._area = AnchorLayout(anchor_x="center", anchor_y="center")
        self._grid = GridLayout(cols=8, spacing=0, size_hint=(None, None))
        self._area.add_widget(self._grid)
        self._area.bind(size=lambda *a: self._fit_grid())
        root.add_widget(self._area)

        self._moves_lbl = Label(text="", font_size=sp(12), size_hint_y=None,
                                height=dp(36), halign="left", valign="top",
                                color=(0.75, 0.75, 0.75, 1))
        self._moves_lbl.bind(
            size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self._moves_lbl)

        bar = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for text, fn in (("New", lambda *a: self._new_game()),
                         ("Undo", lambda *a: self._undo()),
                         ("< Back", self._go_back)):
            b = Button(text=text, font_size=sp(14))
            b.bind(on_release=fn)
            bar.add_widget(b)
        root.add_widget(bar)
        self.add_widget(root)

        self._build_cells()
        self._refresh()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def on_enter(self, *a):
        self._fit_grid()
        self._maybe_ai()

    def _go_back(self, *a):
        self.manager.current = "dashboard"

    # ── state ─────────────────────────────────────────────────────────────
    def _new_state(self):
        self.game = cc.Position()
        self.history = []         # [(position_before, move, san)]
        self.selected = None
        self.targets = {}         # dest square -> move
        self.last = None

    def _new_game(self):
        self._gen += 1
        self._thinking = False
        self._new_state()
        self._refresh()

    def _toggle_mode(self, *a):
        self.vs_ai = not self.vs_ai
        self._mode_btn.text = "Vs: AI" if self.vs_ai else "Vs: 2 Players"
        self._new_game()

    def _cycle_level(self, *a):
        i = LEVEL_ORDER.index(self.level)
        self.level = LEVEL_ORDER[(i + 1) % len(LEVEL_ORDER)]
        self._lvl_btn.text = f"Level: {self.level}"
        self._new_game()

    def _undo(self):
        if not self.history:
            return
        self._gen += 1
        self._thinking = False
        steps = 2 if self.vs_ai and len(self.history) >= 2 else 1
        for _ in range(steps):
            self.game, _m, _s = self.history.pop()
        self.last = None
        if self.history:
            prev = self.history[-1]
            self.last = (prev[1][0], prev[1][1])
        self.selected, self.targets = None, {}
        self._refresh()
        self._maybe_ai()

    # ── board ─────────────────────────────────────────────────────────────
    def _flipped(self):
        return (not self.vs_ai) and self.game.turn == "b"

    def _build_cells(self):
        self._grid.clear_widgets()
        self._cells = {}
        order = range(63, -1, -1) if self._flipped() else range(64)
        self._flip_built = self._flipped()
        for i in order:
            b = Button(text="", bold=True, background_normal="",
                       background_down="", outline_width=2)
            b.bind(on_release=lambda inst, s=i: self._tap(s))
            self._grid.add_widget(b)
            self._cells[i] = b
        self._fit_grid()

    def _fit_grid(self):
        w, h = self._area.size
        if w <= 0 or h <= 0:
            return
        cell = max(min(w, h) / 8, 8)
        self._grid.size = (cell * 8, cell * 8)
        fs = max(int(cell * 0.62), 8)
        for b in self._cells.values():
            b.font_size = fs

    def _refresh(self):
        if self._flipped() != self._flip_built:
            self._build_cells()
        pos = self.game
        check_sq = (pos.king_square(pos.turn) if pos.in_check() else None)
        for i, b in self._cells.items():
            light = (i // 8 + i % 8) % 2 == 0
            col = LIGHT if light else DARK
            if self.last and i in self.last:
                col = LAST_L if light else LAST_D
            if i in self.targets:
                col = TARGET_L if light else TARGET_D
            if i == self.selected:
                col = SELECT
            if i == check_sq:
                col = CHECK
            b.background_color = col
            p = pos.board[i]
            b.text = p.upper() if p != "." else ""
            if p != ".":
                white = p.isupper()
                b.color = WHITE_PIECE if white else BLACK_PIECE
                b.outline_color = BLACK_PIECE if white else WHITE_PIECE
        self._moves_lbl.text = self._move_text()
        self._status.text = self._status_text()

    def _move_text(self):
        parts = []
        for n, (before, _m, san) in enumerate(self.history):
            if before.turn == "w":
                parts.append(f"{before.fullmove}. {san}")
            else:
                parts.append(san if n else f"{before.fullmove}... {san}")
        return " ".join(parts[-8:]) if len(parts) > 8 else " ".join(parts)

    def _status_text(self):
        st = self.game.status()
        side = "White" if self.game.turn == "w" else "Black"
        if st == "checkmate":
            winner = "Black" if self.game.turn == "w" else "White"
            return f"Checkmate - {winner} wins"
        if st == "stalemate":
            return "Stalemate - draw"
        if st == "draw":
            return "Draw"
        if self._thinking:
            return "Thinking..."
        return f"{side} to move" + (" - CHECK" if st == "check" else "")

    # ── input ─────────────────────────────────────────────────────────────
    def _human_turn(self):
        return not self._thinking and not (self.vs_ai and self.game.turn == "b")

    def _tap(self, s):
        if not self._human_turn() or self.game.status() in (
                "checkmate", "stalemate", "draw"):
            return
        if s in self.targets:
            self._make_move(self.targets[s])
            return
        p = self.game.board[s]
        if p != "." and p.isupper() == (self.game.turn == "w"):
            self.selected = s
            self.targets = {m[1]: m for m in self.game.moves_from(s)
                            if m[2] in ("", "q")}
        else:
            self.selected, self.targets = None, {}
        self._refresh()

    def _make_move(self, move):
        san = self.game.san(move)
        self.history.append((self.game, move, san))
        self.game = self.game.play(move)
        self.last = (move[0], move[1])
        self.selected, self.targets = None, {}
        self._refresh()
        self._maybe_ai()

    # ── AI ────────────────────────────────────────────────────────────────
    def _maybe_ai(self):
        if (not self.vs_ai or self.game.turn != "b" or self._thinking
                or self.game.status() in ("checkmate", "stalemate", "draw")):
            return
        self._thinking = True
        self._status.text = "Thinking..."
        gen, pos, depth = self._gen, self.game, LEVELS[self.level]

        def work():
            mv = cc.best_move(pos, depth)
            Clock.schedule_once(lambda dt: self._ai_done(gen, mv), 0)

        threading.Thread(target=work, daemon=True).start()

    def _ai_done(self, gen, move):
        if gen != self._gen:
            return                    # game was reset / undone meanwhile
        self._thinking = False
        if move is not None:
            self._make_move(move)
        else:
            self._refresh()
