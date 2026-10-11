# screens/minesweeper_screen.py
#
# Minesweeper. Based on a DeepSeek draft, reviewed and reworked for this app.
# What changed from the draft and why:
#   - Emoji (bomb, flag, party popper) -> ASCII. Kivy's default Roboto has no
#     emoji glyphs, so they rendered as empty boxes on the phone.
#   - Board is SQUARE cells sized from the available space (the draft used a
#     plain GridLayout, so cells became tall rectangles on a phone).
#   - Long-press flags a cell (the natural phone gesture); Flag Mode is kept as
#     the alternative. Tapping a revealed number whose flags match it reveals
#     the remaining neighbours ("chording").
#   - Mines are placed on the first REVEAL, never on a flag tap (the draft
#     placed them on the first tap of any kind, so flagging first could put a
#     mine anywhere, including under the cell you meant to open).
#   - Iterative flood fill (the draft recursed; big boards could hit Python's
#     recursion limit).
#   - Timer (pauses when you leave the screen), three difficulties, best time
#     per difficulty saved in <data dir>/minesweeper/scores.json.
#   - Wrong flags are marked when you lose; mines left counter can go negative
#     like the classic game; the cell you lost on is highlighted.

import os
import json
import time
import random
from collections import deque

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.togglebutton import ToggleButton
from kivy.metrics import dp
from kivy.clock import Clock

import app_data

# name -> (rows, cols, mines)
LEVELS = {
    "Easy":   (9, 9, 10),
    "Medium": (12, 12, 24),
    "Hard":   (16, 16, 40),
}
LEVEL_ORDER = ("Easy", "Medium", "Hard")

NUM_COLORS = {
    1: (0.15, 0.35, 0.95, 1), 2: (0.1, 0.55, 0.15, 1),
    3: (0.85, 0.15, 0.15, 1), 4: (0.1, 0.1, 0.6, 1),
    5: (0.6, 0.1, 0.1, 1),    6: (0.1, 0.5, 0.5, 1),
    7: (0.1, 0.1, 0.1, 1),    8: (0.4, 0.4, 0.4, 1),
}
HIDDEN = (0.62, 0.64, 0.68, 1)
OPEN = (0.88, 0.88, 0.9, 1)
RED = (0.9, 0.25, 0.25, 1)
LONG_PRESS = 0.38


class _Cell(Button):
    """One square. Long-press -> flag, short tap -> reveal/chord."""

    def __init__(self, r, c, game, **kw):
        super().__init__(**kw)
        self.r, self.c = r, c
        self._game = game
        self._lp_ev = None
        self._lp_fired = False

    def on_press(self):
        self._lp_fired = False
        if self._lp_ev:
            self._lp_ev.cancel()
        self._lp_ev = Clock.schedule_once(self._long_press, LONG_PRESS)

    def _long_press(self, dt):
        self._lp_ev = None
        self._lp_fired = True
        self._game.cell_long_press(self.r, self.c)

    def on_release(self):
        if self._lp_ev:
            self._lp_ev.cancel()
            self._lp_ev = None
        if not self._lp_fired:
            self._game.cell_tap(self.r, self.c)

    def on_touch_up(self, touch):
        # finger slid off the cell: don't let a pending long-press fire
        if touch.grab_current is self or self.collide_point(*touch.pos):
            pass
        elif self._lp_ev:
            self._lp_ev.cancel()
            self._lp_ev = None
        return super().on_touch_up(touch)


class MinesweeperScreen(Screen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self.level = "Easy"
        self.rows, self.cols, self.mines = LEVELS[self.level]
        self._cells = []
        self._timer_ev = None
        self._elapsed = 0.0       # seconds banked while the timer was paused
        self._t0 = None           # monotonic start of the running stretch
        self._started = False
        self._over = False
        self._flag_mode = False

        root = BoxLayout(orientation="vertical", padding=dp(6),
                         spacing=dp(6))

        # difficulty row
        lvl_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self._lvl_btns = {}
        for name in LEVEL_ORDER:
            b = ToggleButton(text=name, group="ms_level", font_size=13,
                             allow_no_selection=False,
                             state="down" if name == self.level else "normal")
            b.bind(on_release=lambda inst, n=name: self._set_level(n))
            lvl_row.add_widget(b)
            self._lvl_btns[name] = b
        root.add_widget(lvl_row)

        # counters
        top = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self._mine_lbl = Label(text="Mines: 10", font_size=15,
                               size_hint_x=None, width=dp(100))
        self._time_lbl = Label(text="0:00", font_size=15,
                               size_hint_x=None, width=dp(60))
        self._flag_btn = ToggleButton(text="Flag: OFF", font_size=12)
        self._flag_btn.bind(on_release=self._toggle_flag_mode)
        new_btn = Button(text="New", font_size=13, size_hint_x=None,
                         width=dp(70))
        new_btn.bind(on_release=lambda *a: self._new_game())
        for w in (self._mine_lbl, self._time_lbl, self._flag_btn, new_btn):
            top.add_widget(w)
        root.add_widget(top)

        self._status = Label(text="", font_size=13, size_hint_y=None,
                             height=dp(24), color=(0.7, 0.9, 1, 1))
        root.add_widget(self._status)

        # board area: the grid inside is re-sized to SQUARE cells
        self._area = AnchorLayout(anchor_x="center", anchor_y="center")
        self._grid = GridLayout(cols=self.cols, spacing=dp(2),
                                size_hint=(None, None))
        self._area.add_widget(self._grid)
        self._area.bind(size=lambda *a: self._fit_grid())
        root.add_widget(self._area)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=self._go_back)
        root.add_widget(back)
        self.add_widget(root)

        self._new_game()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def on_enter(self, *a):
        if self._started and not self._over:
            self._resume_timer()
        self._fit_grid()

    def on_leave(self, *a):
        self._pause_timer()

    def _go_back(self, *a):
        self.manager.current = "dashboard"

    # ── game setup ────────────────────────────────────────────────────────
    def _set_level(self, name):
        if name == self.level:
            return
        self.level = name
        self._new_game()

    def _new_game(self):
        self._pause_timer()
        self.rows, self.cols, self.mines = LEVELS[self.level]
        self._elapsed, self._t0 = 0.0, None
        self._started = False
        self._over = False
        self._flag_mode = False
        self._flag_btn.state = "normal"
        self._flag_btn.text = "Flag: OFF"
        for n, b in self._lvl_btns.items():
            b.state = "down" if n == self.level else "normal"

        R, C = self.rows, self.cols
        self.board = [[0] * C for _ in range(R)]        # -1 mine, else count
        self.revealed = [[False] * C for _ in range(R)]
        self.flagged = [[False] * C for _ in range(R)]
        self._mines_placed = False

        self._grid.clear_widgets()
        self._grid.cols = C
        self._cells = []
        for r in range(R):
            row = []
            for c in range(C):
                cell = _Cell(r, c, self, text="", bold=True,
                             background_normal="", background_down="",
                             background_color=HIDDEN, color=(0, 0, 0, 1))
                self._grid.add_widget(cell)
                row.append(cell)
            self._cells.append(row)
        self._time_lbl.text = "0:00"
        self._update_mine_counter()
        best = self._best_time()
        self._status.text = ("Tap to dig, hold to flag"
                             + (f"   Best: {self._fmt(best)}" if best else ""))
        self._fit_grid()

    def _fit_grid(self):
        """Square cells that fill the board area."""
        if not self._cells:
            return
        w, h = self._area.size
        if w <= 0 or h <= 0:
            return
        gap = self._grid.spacing[0]
        cell = min((w - gap * (self.cols - 1)) / self.cols,
                   (h - gap * (self.rows - 1)) / self.rows)
        cell = max(cell, 8)
        self._grid.size = (cell * self.cols + gap * (self.cols - 1),
                           cell * self.rows + gap * (self.rows - 1))
        fs = max(int(cell * 0.52), 8)      # already pixels: not density-scaled
        for row in self._cells:
            for b in row:
                b.font_size = fs

    def _place_mines(self, safe_r, safe_c):
        R, C = self.rows, self.cols
        # keep the first cell AND its neighbours clear so the first tap opens
        # up an area; fall back to just the cell if the board is too small
        def pool(radius):
            return [(r, c) for r in range(R) for c in range(C)
                    if max(abs(r - safe_r), abs(c - safe_c)) > radius]
        spots = pool(1)
        if len(spots) < self.mines:
            spots = pool(0)
        for r, c in random.sample(spots, self.mines):
            self.board[r][c] = -1
        for r in range(R):
            for c in range(C):
                if self.board[r][c] != -1:
                    self.board[r][c] = sum(
                        1 for nr, nc in self._neighbours(r, c)
                        if self.board[nr][nc] == -1)
        self._mines_placed = True

    def _neighbours(self, r, c):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    yield nr, nc

    # ── input ─────────────────────────────────────────────────────────────
    def _toggle_flag_mode(self, *a):
        self._flag_mode = self._flag_btn.state == "down"
        self._flag_btn.text = "Flag: ON" if self._flag_mode else "Flag: OFF"

    def cell_long_press(self, r, c):
        if not self._over:
            self._toggle_flag(r, c)

    def cell_tap(self, r, c):
        if self._over:
            return
        if self._flag_mode:
            self._toggle_flag(r, c)
            return
        if self.revealed[r][c]:
            self._chord(r, c)
            return
        if self.flagged[r][c]:
            return
        if not self._mines_placed:
            self._place_mines(r, c)
            self._started = True
            self._resume_timer()
        if self.board[r][c] == -1:
            self._lose(r, c)
            return
        self._reveal_from(r, c)
        self._check_win()

    def _toggle_flag(self, r, c):
        if self.revealed[r][c]:
            return
        self.flagged[r][c] = not self.flagged[r][c]
        b = self._cells[r][c]
        b.text = "F" if self.flagged[r][c] else ""
        b.color = RED if self.flagged[r][c] else (0, 0, 0, 1)
        self._update_mine_counter()

    def _chord(self, r, c):
        """Tap a number whose flag count matches it: open the other
        neighbours. A wrong flag means this can hit a mine - same as the
        classic game."""
        n = self.board[r][c]
        if n <= 0:
            return
        around = list(self._neighbours(r, c))
        if sum(self.flagged[nr][nc] for nr, nc in around) != n:
            return
        for nr, nc in around:
            if self.flagged[nr][nc] or self.revealed[nr][nc]:
                continue
            if self.board[nr][nc] == -1:
                self._lose(nr, nc)
                return
            self._reveal_from(nr, nc)
        self._check_win()

    # ── reveal / end ──────────────────────────────────────────────────────
    def _reveal_from(self, r, c):
        """Iterative flood fill from (r, c)."""
        todo = deque([(r, c)])
        while todo:
            r, c = todo.popleft()
            if self.revealed[r][c] or self.flagged[r][c]:
                continue
            self.revealed[r][c] = True
            val = self.board[r][c]
            b = self._cells[r][c]
            b.background_color = OPEN
            b.text = str(val) if val > 0 else ""
            b.color = NUM_COLORS.get(val, (0, 0, 0, 1))
            if val == 0:
                todo.extend(self._neighbours(r, c))

    def _lose(self, hit_r, hit_c):
        self._over = True
        self._pause_timer()
        for r in range(self.rows):
            for c in range(self.cols):
                b = self._cells[r][c]
                if self.board[r][c] == -1 and not self.flagged[r][c]:
                    b.text = "*"
                    b.color = (0, 0, 0, 1)
                    b.background_color = (0.75, 0.55, 0.55, 1)
                elif self.flagged[r][c] and self.board[r][c] != -1:
                    b.text = "X"                    # a flag that was wrong
                    b.color = RED
        hit = self._cells[hit_r][hit_c]
        hit.text = "*"
        hit.color = (1, 1, 1, 1)
        hit.background_color = RED
        self._status.text = "BOOM - you hit a mine. Tap New to retry."

    def _check_win(self):
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] != -1 and not self.revealed[r][c]:
                    return
        self._over = True
        self._pause_timer()
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] == -1:
                    self.flagged[r][c] = True
                    self._cells[r][c].text = "F"
                    self._cells[r][c].color = RED
        self._update_mine_counter()
        t = int(self._elapsed)
        best = self._best_time()
        if best is None or t < best:
            self._save_best(t)
            self._status.text = f"You win in {self._fmt(t)} - new best!"
        else:
            self._status.text = (f"You win in {self._fmt(t)}   "
                                 f"(best {self._fmt(best)})")

    # ── counters / timer ──────────────────────────────────────────────────
    def _update_mine_counter(self):
        left = self.mines - sum(sum(row) for row in self.flagged)
        self._mine_lbl.text = f"Mines: {left}"

    @staticmethod
    def _fmt(sec):
        sec = int(sec)
        return f"{sec // 60}:{sec % 60:02d}"

    def _resume_timer(self):
        if self._timer_ev is None and self._started and not self._over:
            self._t0 = time.monotonic()
            self._timer_ev = Clock.schedule_interval(self._tick, 0.25)

    def _pause_timer(self):
        if self._timer_ev is not None:
            self._timer_ev.cancel()
            self._timer_ev = None
        if self._t0 is not None:
            self._elapsed += time.monotonic() - self._t0
            self._t0 = None
        self._time_lbl.text = self._fmt(self._elapsed)

    def _tick(self, dt):
        if self._t0 is not None:
            self._time_lbl.text = self._fmt(
                self._elapsed + time.monotonic() - self._t0)

    # ── best times ────────────────────────────────────────────────────────
    def _scores_path(self):
        return os.path.join(app_data.subdir("minesweeper"), "scores.json")

    def _load_scores(self):
        try:
            with open(self._scores_path(), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _best_time(self):
        v = self._load_scores().get(self.level)
        return v if isinstance(v, (int, float)) else None

    def _save_best(self, seconds):
        scores = self._load_scores()
        scores[self.level] = int(seconds)
        try:
            with open(self._scores_path(), "w", encoding="utf-8") as f:
                json.dump(scores, f)
        except OSError:
            pass
