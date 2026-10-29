# core/chess_core.py - pure-Python chess rules + a small AI. No Kivy imports,
# so it can be unit-tested without a display.
#
# Board: list of 64 one-char strings, index 0 = a8 ... 63 = h1 (row-major from
# Black's side). Upper case = White, lower case = Black, "." = empty.
# Move: (from_sq, to_sq, promo) where promo is "" or one of "qrbn".
# Supported: castling, en passant, promotion, check / checkmate / stalemate,
# fifty-move rule, insufficient material. Not supported: threefold repetition.

import random

START_BOARD = list(
    "rnbqkbnr" "pppppppp" + "." * 32 + "PPPPPPPP" "RNBQKBNR")

KNIGHT_D = ((-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1))
KING_D = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
          (0, 1), (1, -1), (1, 0), (1, 1))
ROOK_D = ((-1, 0), (1, 0), (0, -1), (0, 1))
BISHOP_D = ((-1, -1), (-1, 1), (1, -1), (1, 1))

VALUES = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 0}

# piece-square bonus (from White's point of view, index 0 = a8)
_PST_PAWN = [0, 0, 0, 0, 0, 0, 0, 0,
             50, 50, 50, 50, 50, 50, 50, 50,
             10, 10, 20, 30, 30, 20, 10, 10,
             5, 5, 10, 25, 25, 10, 5, 5,
             0, 0, 0, 20, 20, 0, 0, 0,
             5, -5, -10, 0, 0, -10, -5, 5,
             5, 10, 10, -20, -20, 10, 10, 5,
             0, 0, 0, 0, 0, 0, 0, 0]
_PST_KNIGHT = [-50, -40, -30, -30, -30, -30, -40, -50,
               -40, -20, 0, 0, 0, 0, -20, -40,
               -30, 0, 10, 15, 15, 10, 0, -30,
               -30, 5, 15, 20, 20, 15, 5, -30,
               -30, 0, 15, 20, 20, 15, 0, -30,
               -30, 5, 10, 15, 15, 10, 5, -30,
               -40, -20, 0, 5, 5, 0, -20, -40,
               -50, -40, -30, -30, -30, -30, -40, -50]
_PST = {"p": _PST_PAWN, "n": _PST_KNIGHT}


def sq(r, c):
    return r * 8 + c


def sq_name(i):
    return "abcdefgh"[i % 8] + str(8 - i // 8)


def is_white(p):
    return p.isupper()


class Position:
    """Mutable-by-copy position. Use .play(move) -> new Position."""

    def __init__(self, board=None, turn="w", castling="KQkq", ep=-1,
                 halfmove=0, fullmove=1):
        self.board = list(board) if board else list(START_BOARD)
        self.turn = turn
        self.castling = castling
        self.ep = ep
        self.halfmove = halfmove
        self.fullmove = fullmove

    def copy(self):
        return Position(self.board, self.turn, self.castling, self.ep,
                        self.halfmove, self.fullmove)

    # ── attacks / check ───────────────────────────────────────────────────
    def attacked(self, target, by):
        """Is square `target` attacked by colour `by` ("w"/"b")?"""
        b = self.board
        tr, tc = divmod(target, 8)
        up = by == "w"
        own = (lambda p: p.isupper()) if up else (lambda p: p.islower())
        # pawns: a white pawn attacks toward lower row index
        pr = tr + 1 if up else tr - 1
        if 0 <= pr < 8:
            for dc in (-1, 1):
                pc = tc + dc
                if 0 <= pc < 8 and b[sq(pr, pc)] == ("P" if up else "p"):
                    return True
        for dr, dc in KNIGHT_D:
            r, c = tr + dr, tc + dc
            if 0 <= r < 8 and 0 <= c < 8 and b[sq(r, c)] == ("N" if up else "n"):
                return True
        for dr, dc in KING_D:
            r, c = tr + dr, tc + dc
            if 0 <= r < 8 and 0 <= c < 8 and b[sq(r, c)] == ("K" if up else "k"):
                return True
        for dirs, kinds in ((ROOK_D, "rq"), (BISHOP_D, "bq")):
            for dr, dc in dirs:
                r, c = tr + dr, tc + dc
                while 0 <= r < 8 and 0 <= c < 8:
                    p = b[sq(r, c)]
                    if p != ".":
                        if own(p) and p.lower() in kinds:
                            return True
                        break
                    r += dr
                    c += dc
        return False

    def king_square(self, colour):
        k = "K" if colour == "w" else "k"
        return self.board.index(k)

    def in_check(self, colour=None):
        colour = colour or self.turn
        return self.attacked(self.king_square(colour),
                             "b" if colour == "w" else "w")

    # ── move generation ───────────────────────────────────────────────────
    def pseudo_moves(self):
        b = self.board
        white = self.turn == "w"
        mine = (lambda p: p.isupper()) if white else (lambda p: p.islower())
        theirs = (lambda p: p.islower()) if white else (lambda p: p.isupper())
        out = []
        for i, p in enumerate(b):
            if p == "." or not mine(p):
                continue
            r, c = divmod(i, 8)
            k = p.lower()
            if k == "p":
                d = -1 if white else 1
                start = 6 if white else 1
                last = 0 if white else 7
                r1 = r + d
                if 0 <= r1 < 8 and b[sq(r1, c)] == ".":
                    self._pawn_add(out, i, sq(r1, c), r1 == last)
                    if r == start and b[sq(r + 2 * d, c)] == ".":
                        out.append((i, sq(r + 2 * d, c), ""))
                for dc in (-1, 1):
                    c1 = c + dc
                    if not (0 <= r1 < 8 and 0 <= c1 < 8):
                        continue
                    t = sq(r1, c1)
                    if theirs(b[t]) or t == self.ep:
                        self._pawn_add(out, i, t, r1 == last)
            elif k in "nk":
                for dr, dc in (KNIGHT_D if k == "n" else KING_D):
                    r1, c1 = r + dr, c + dc
                    if 0 <= r1 < 8 and 0 <= c1 < 8:
                        t = b[sq(r1, c1)]
                        if t == "." or theirs(t):
                            out.append((i, sq(r1, c1), ""))
                if k == "k":
                    self._castle_moves(out, i)
            else:
                dirs = (ROOK_D if k == "r" else BISHOP_D if k == "b"
                        else ROOK_D + BISHOP_D)
                for dr, dc in dirs:
                    r1, c1 = r + dr, c + dc
                    while 0 <= r1 < 8 and 0 <= c1 < 8:
                        t = b[sq(r1, c1)]
                        if t == ".":
                            out.append((i, sq(r1, c1), ""))
                        else:
                            if theirs(t):
                                out.append((i, sq(r1, c1), ""))
                            break
                        r1 += dr
                        c1 += dc
        return out

    @staticmethod
    def _pawn_add(out, f, t, promo):
        if promo:
            for pc in "qrbn":
                out.append((f, t, pc))
        else:
            out.append((f, t, ""))

    def _castle_moves(self, out, ksq):
        white = self.turn == "w"
        home = 60 if white else 4
        if ksq != home or self.in_check():
            return
        enemy = "b" if white else "w"
        b = self.board
        rook = "R" if white else "r"
        ks, qs = ("K", "Q") if white else ("k", "q")
        if (ks in self.castling and b[home + 3] == rook
                and b[home + 1] == "." and b[home + 2] == "."
                and not self.attacked(home + 1, enemy)
                and not self.attacked(home + 2, enemy)):
            out.append((home, home + 2, ""))
        if (qs in self.castling and b[home - 4] == rook
                and b[home - 1] == "." and b[home - 2] == "."
                and b[home - 3] == "."
                and not self.attacked(home - 1, enemy)
                and not self.attacked(home - 2, enemy)):
            out.append((home, home - 2, ""))

    def legal_moves(self):
        out = []
        for m in self.pseudo_moves():
            nxt = self.play(m)
            if not nxt.in_check("b" if nxt.turn == "w" else "w"):
                out.append(m)
        return out

    def moves_from(self, i):
        return [m for m in self.legal_moves() if m[0] == i]

    # ── making a move ─────────────────────────────────────────────────────
    def play(self, move):
        f, t, promo = move
        n = self.copy()
        b = n.board
        p = b[f]
        white = p.isupper()
        capture = b[t] != "."
        k = p.lower()
        if k == "p" and t == self.ep and not capture:
            b[t + (8 if white else -8)] = "."          # en passant victim
            capture = True
        b[t] = p
        b[f] = "."
        if promo:
            b[t] = promo.upper() if white else promo.lower()
        if k == "k" and abs(t - f) == 2:               # castling: move rook
            if t > f:
                b[f + 1], b[f + 3] = b[f + 3], "."
            else:
                b[f - 1], b[f - 4] = b[f - 4], "."
        # castling rights
        cr = n.castling
        if k == "k":
            cr = cr.replace("K", "").replace("Q", "") if white \
                else cr.replace("k", "").replace("q", "")
        for s, right in ((63, "K"), (56, "Q"), (7, "k"), (0, "q")):
            if f == s or t == s:
                cr = cr.replace(right, "")
        n.castling = cr
        n.ep = (f + t) // 2 if k == "p" and abs(t - f) == 16 else -1
        n.halfmove = 0 if (k == "p" or capture) else self.halfmove + 1
        n.fullmove = self.fullmove + (0 if white else 1)
        n.turn = "b" if white else "w"
        return n

    # ── game state ────────────────────────────────────────────────────────
    def insufficient_material(self):
        pieces = [p for p in self.board if p not in ".kK"]
        if not pieces:
            return True
        if len(pieces) == 1 and pieces[0].lower() in "nb":
            return True
        return False

    def status(self):
        """'ongoing', 'check', 'checkmate', 'stalemate' or 'draw'."""
        if not self.legal_moves():
            return "checkmate" if self.in_check() else "stalemate"
        if self.halfmove >= 100 or self.insufficient_material():
            return "draw"
        return "check" if self.in_check() else "ongoing"

    def san(self, move):
        """Short algebraic-ish notation, good enough for a move list."""
        f, t, promo = move
        p = self.board[f]
        k = p.lower()
        if k == "k" and abs(t - f) == 2:
            text = "O-O" if t > f else "O-O-O"
        else:
            cap = self.board[t] != "." or (k == "p" and t == self.ep)
            if k == "p":
                text = (sq_name(f)[0] + "x" if cap else "") + sq_name(t)
                if promo:
                    text += "=" + promo.upper()
            else:
                text = k.upper()
                clash = [m for m in self.legal_moves()
                         if m[1] == t and m[0] != f
                         and self.board[m[0]] == p]
                if clash:
                    text += sq_name(f)[0] if all(
                        m[0] % 8 != f % 8 for m in clash) else sq_name(f)[1]
                text += ("x" if cap else "") + sq_name(t)
        nxt = self.play(move)
        st = nxt.status()
        if st == "checkmate":
            text += "#"
        elif st == "check":
            text += "+"
        return text


# ── AI ────────────────────────────────────────────────────────────────────
def evaluate(pos):
    """Static score in centipawns from White's point of view."""
    score = 0
    for i, p in enumerate(pos.board):
        if p == ".":
            continue
        k = p.lower()
        v = VALUES[k]
        table = _PST.get(k)
        if p.isupper():
            score += v + (table[i] if table else 0)
        else:
            score -= v + (table[(7 - i // 8) * 8 + i % 8] if table else 0)
    return score


def _order(pos, moves):
    def key(m):
        victim = pos.board[m[1]]
        s = VALUES.get(victim.lower(), 0) * 10 - VALUES[pos.board[m[0]].lower()] \
            if victim != "." else 0
        return -(s + (800 if m[2] == "q" else 0))
    return sorted(moves, key=key)


def _search(pos, depth, alpha, beta):
    moves = pos.legal_moves()
    if not moves:
        if pos.in_check():
            return (-100000 - depth) if pos.turn == "w" else (100000 + depth)
        return 0
    if pos.halfmove >= 100 or pos.insufficient_material():
        return 0
    if depth == 0:
        return evaluate(pos)
    if pos.turn == "w":
        best = -10 ** 9
        for m in _order(pos, moves):
            best = max(best, _search(pos.play(m), depth - 1, alpha, beta))
            alpha = max(alpha, best)
            if alpha >= beta:
                break
        return best
    best = 10 ** 9
    for m in _order(pos, moves):
        best = min(best, _search(pos.play(m), depth - 1, alpha, beta))
        beta = min(beta, best)
        if alpha >= beta:
            break
    return best


def best_move(pos, depth=2, rng=random):
    """Pick a move for pos.turn. depth 0 = random, 1+ = alpha-beta search."""
    moves = pos.legal_moves()
    if not moves:
        return None
    if depth <= 0:
        return rng.choice(moves)
    white = pos.turn == "w"
    scored = []
    alpha, beta = -10 ** 9, 10 ** 9
    for m in _order(pos, moves):
        s = _search(pos.play(m), depth - 1, alpha, beta)
        scored.append((s, m))
        if white:
            alpha = max(alpha, s - 1)      # window edge below the best so
        else:                              # exact ties still come back exact
            beta = min(beta, s + 1)
    top = max(s for s, _ in scored) if white else min(s for s, _ in scored)
    pool = [m for s, m in scored if s == top]
    return rng.choice(pool)
