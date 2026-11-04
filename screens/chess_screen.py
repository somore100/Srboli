# screens/chess_screen.py
#
# Chess: play the built-in AI (you are White), pass-and-play two players, or
# watch the AI play itself (AI vs AI, with a speed setting and pause).
# Rules + AI live in core/chess_core.py (pure Python, unit-tested).
#   - Pieces are drawn as letters, White in capitals (K Q R B N P) and Black in
#     lowercase (k q r b n p): Kivy's default Roboto has no
#     chess glyphs, same reason Minesweeper avoids emoji.
#   - Tap a piece, then a highlighted square. Tapping another own piece
#     re-selects. Pawn promotion is automatic (queen).
#   - The AI searches in a worker thread so the UI never freezes.
#   - Undo takes back one move (two against the AI). The board flips for
#     Black in two-player mode so each side plays from their own end (the
#     "Board" button keeps it fixed instead).

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
# Rough strength, a guess from play against itself and ordinary club
# players, not a rating measured against a real engine.
LEVEL_ELO = {"Easy": "<400", "Medium": "~800", "Hard": "~1100"}
SPEEDS = (("Slow", 1.5), ("Normal", 0.6), ("Fast", 0.15))   # pause between AI moves
MODES = ("ai", "two", "aivai")
MODE_TEXT = {"ai": "Vs: AI", "two": "Vs: 2 Players", "aivai": "AI vs AI"}

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
        self.level = "Medium"          # Black's AI (the AI when you play White)
        self.level_w = "Medium"        # White's AI, AI vs AI only
        self.mode = "ai"
        self.flip_board = True         # two players: turn the board for Black
        self.speed = 1                 # index into SPEEDS
        self.paused = False
        self._next_ev = None
        self._cells = {}          # square index -> Button
        self._gen = 0             # bumped on new game / undo: drops stale AI
        self._thinking = False
        self._new_state()

        root = BoxLayout(orientation="vertical", padding=dp(6),
                         spacing=dp(6))

        top = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self._mode_btn = Button(text="Vs: AI", font_size=sp(13))
        self._mode_btn.bind(on_release=self._toggle_mode)
        self._lvl_btn = Button(font_size=sp(13))
        self._lvl_btn.bind(on_release=self._cycle_level)
        for w in (self._mode_btn, self._lvl_btn):
            top.add_widget(w)
        root.add_widget(top)

        # second row: what applies to the current mode (board fixed / flip in
        # two-player; White's level, speed and pause in AI vs AI)
        self._ctx = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self._flip_btn = Button(font_size=sp(13))
        self._flip_btn.bind(on_release=self._toggle_flip)
        self._lvlw_btn = Button(font_size=sp(13))
        self._lvlw_btn.bind(on_release=self._cycle_level_w)
        self._speed_btn = Button(font_size=sp(13))
        self._speed_btn.bind(on_release=self._cycle_speed)
        self._pause_btn = Button(font_size=sp(13))
        self._pause_btn.bind(on_release=self._toggle_pause)
        root.add_widget(self._ctx)

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
        self._sync_controls()
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

    @property
    def vs_ai(self):
        return self.mode == "ai"

    def _cancel_next(self):
        if self._next_ev is not None:
            self._next_ev.cancel()
            self._next_ev = None

    def _new_game(self):
        self._gen += 1
        self._thinking = False
        self._cancel_next()
        self.paused = False
        self._new_state()
        self._sync_controls()
        self._refresh()
        self._maybe_ai()

    def _sync_controls(self):
        """Labels and the context row for the current mode."""
        self._mode_btn.text = MODE_TEXT[self.mode]
        if self.mode == "aivai":
            self._lvl_btn.text = f"Black: {self.level} ({LEVEL_ELO[self.level]})"
        elif self.mode == "ai":
            self._lvl_btn.text = f"Level: {self.level} ({LEVEL_ELO[self.level]})"
        else:
            self._lvl_btn.text = "Level: -"
        self._lvl_btn.disabled = self.mode == "two"
        self._flip_btn.text = "Board: Flips" if self.flip_board else "Board: Fixed"
        self._lvlw_btn.text = f"White: {self.level_w} ({LEVEL_ELO[self.level_w]})"
        self._speed_btn.text = f"Speed: {SPEEDS[self.speed][0]}"
        self._pause_btn.text = "Resume" if self.paused else "Pause"
        self._ctx.clear_widgets()
        if self.mode == "two":
            self._ctx.add_widget(self._flip_btn)
        elif self.mode == "aivai":
            for w in (self._lvlw_btn, self._speed_btn, self._pause_btn):
                self._ctx.add_widget(w)
        self._ctx.opacity = 1 if self._ctx.children else 0
        self._ctx.height = dp(40) if self._ctx.children else 0

    def _toggle_mode(self, *a):
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        self._new_game()

    def _cycle_level(self, *a):
        i = LEVEL_ORDER.index(self.level)
        self.level = LEVEL_ORDER[(i + 1) % len(LEVEL_ORDER)]
        self._new_game()

    def _cycle_level_w(self, *a):
        i = LEVEL_ORDER.index(self.level_w)
        self.level_w = LEVEL_ORDER[(i + 1) % len(LEVEL_ORDER)]
        self._new_game()

    def _toggle_flip(self, *a):
        self.flip_board = not self.flip_board
        self._sync_controls()
        self._refresh()

    def _cycle_speed(self, *a):
        self.speed = (self.speed + 1) % len(SPEEDS)
        self._sync_controls()

    def _toggle_pause(self, *a):
        self.paused = not self.paused
        self._sync_controls()
        if self.paused:
            self._cancel_next()
        else:
            self._maybe_ai()

    def _undo(self):
        if not self.history:
            return
        self._gen += 1
        self._thinking = False
        self._cancel_next()
        if self.mode == "aivai" and not self.paused:
            self.paused = True          # take one move back and stay there
            self._sync_controls()
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
        return (self.mode == "two" and self.flip_board
                and self.game.turn == "b")

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
            b.text = p if p != "." else ""      # White K Q R B N P, Black k q r b n p
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
        if self.mode == "aivai" and self.paused:
            return f"Paused - {side} to move"
        return f"{side} to move" + (" - CHECK" if st == "check" else "")

    # ── input ─────────────────────────────────────────────────────────────
    def _human_turn(self):
        return (not self._thinking and self.mode != "aivai"
                and not (self.vs_ai and self.game.turn == "b"))

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
        if self.mode == "aivai":
            self._cancel_next()
            if not self.paused:
                self._next_ev = Clock.schedule_once(self._maybe_ai,
                                                    SPEEDS[self.speed][1])
        else:
            self._maybe_ai()

    # ── AI ────────────────────────────────────────────────────────────────
    def _ai_to_move(self):
        if self.mode == "aivai":
            return True
        return self.mode == "ai" and self.game.turn == "b"

    def _maybe_ai(self, *a):
        self._next_ev = None
        if (not self._ai_to_move() or self._thinking or self.paused
                or self.game.status() in ("checkmate", "stalemate", "draw")):
            return
        self._thinking = True
        self._status.text = "Thinking..."
        gen, pos = self._gen, self.game
        depth = LEVELS[self.level_w if pos.turn == "w" and self.mode == "aivai"
                       else self.level]

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
