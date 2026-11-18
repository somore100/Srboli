# core/infinite_mines_core.py - the rules of Infinite Mines, with no UI imports
# so every rule can be tested anywhere (CI runs it without a display).
#
# The world is endless and is never generated "all at once". Whether a cell
# is a mine is a pure function of (seed, x, y), so a number next to any edge
# is right without the neighbouring area having been built. Only what the
# player CHANGED is stored (a sparse set of cells), so a save stays small.
# The 9x9 "sectors" are only a way to group cells (a sector is solved when all
# its safe cells are open); they have nothing to do with how mines are made.
#
# Stepping on a mine does not end the game. It makes an explosion:
#   crater   the mine itself - permanent, counts as a known mine for numbers
#   scorch   brown cells around it (radius 1-5) that cannot be touched
#   fallout  the next 1-2 cells out: every SAFE cell there is opened for you
#            (its number shown), so the hidden ones left in that ring are all
#            mines. That ring is the anchor you solve the brown area from, so
#            recovering never needs a blind guess at the edge.
#   ash      a healed (formerly brown) cell: pale, dig it again
# Blasts scale with how much you have explored: early on they are small
# (max_radius), and the opened cells one can wipe are a fraction of what you
# dug (erase_cap), so a blast can never undo most of your progress.
# Scorched cells heal from the edge inwards, one layer per action, and only
# NEAR the cells you just opened (or the blast's own ring, on the next action):
# digging far away heals nothing. Only OPENED cells count towards healing, never
# flags, so spamming flags around a crater can't clear it; the pale cells a
# layer leaves behind are dug to carry the healing one layer further in.
# Defusing: when a sector is solved every correctly flagged mine in it pays an
# extra point ("defused"); a flag put on a mine of an already solved sector
# pays one too. Nothing pays at the moment of flagging, so a flag never tells
# you whether it was right.
# Hints cost HINT_COST points and only ever name a move that is certain.
import math
import random
from collections import deque

HIDDEN, FLAG, CRATER, SCORCH, ASH = "hidden", "flag", "crater", "scorch", "ash"

CHUNK = 9                  # sector size (cells per side)
SAFE_RADIUS = 2            # nothing within this many cells of (0,0) is a mine
DEFAULT_DENSITY = 0.17
RADII = [1] * 30 + [2] * 25 + [3] * 20 + [4] * 15 + [5] * 10   # blast radius odds
MAX_ERASE = 60             # absolute most opened/flagged cells one blast can wipe
HEAL_NEED = 3              # opened neighbours a scorched cell needs to heal
HEAL_REACH = 2             # a dug cell heals scar cells this close to it
REPAIR_COST = 3            # points for an instant repair (3x3 around a cell)
HINT_COST = 2              # points for a hint (a move that is certain)
FLOOD_CAP = 3000           # most cells one dig opens (tap a 0 to carry on)

_MASK = (1 << 64) - 1
_NB = tuple((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy)


def _mix(a, b, c, d):
    """A 64-bit hash (splitmix style): same on every platform and run."""
    z = (a * 0x9E3779B97F4A7C15 + b * 0xBF58476D1CE4E5B9
         + c * 0x94D049BB133111EB + d * 0xD6E8FEB86659FD93 + 0x1234567) & _MASK
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
    return z ^ (z >> 31)


def chunk_of(x, y):
    return (x // CHUNK, y // CHUNK)


class Outcome:
    """What one action did. `kind` is one of: dug, chord, blast, flag, unflag,
    repair, scorch, crater, flagged, revealed, poor, noop."""
    __slots__ = ("kind", "revealed", "blast", "radius", "erased", "healed",
                 "sectors", "points", "defused", "target", "action")

    def __init__(self, kind):
        self.kind = kind
        self.revealed = 0       # cells opened
        self.blast = None       # (x, y) of the last mine stepped on
        self.radius = 0
        self.erased = 0         # opened/flagged cells the blast wiped
        self.healed = 0         # scorched cells that healed
        self.sectors = []       # [((cx, cy), points)] newly solved
        self.points = 0         # points gained (repair: spent, negative)
        self.defused = 0        # mines paid as defused
        self.target = None      # hint: the cell to act on
        self.action = None      # hint: "dig" / "flag" / "unflag"


class World:
    def __init__(self, seed=None, density=DEFAULT_DENSITY):
        self.seed = int(seed) if seed is not None else random.randrange(1, 2 ** 31)
        self.density = max(0.0, min(0.6, float(density)))
        self.revealed = {}      # (x, y) -> number, filled when a cell opens
        self.flags = set()
        self.craters = set()
        self.scorch = set()
        self.ash = set()        # pale cells: fallout and healed cells, not yet dug
        self.mended = set()     # the healed part of ash; counts as solved
        self.defused = set()    # mines whose defuse point is paid
        self.solved = set()     # sectors already paid out
        self.points = 0
        self.dug = 0
        self.blasts = 0
        self._touched = set()
        self._changed = set()   # cells opened since the last heal (heal triggers)
        self._safe_total = {}

    # ---------------- the world itself (pure) ----------------
    def is_mine(self, x, y):
        if abs(x) <= SAFE_RADIUS and abs(y) <= SAFE_RADIUS:
            return False
        return (_mix(self.seed, x, y, 0) >> 11) / 9007199254740992.0 < self.density

    def number(self, x, y):
        return sum(1 for dx, dy in _NB if self.is_mine(x + dx, y + dy))

    def blast_shape(self, x, y):
        """(radius, fallout width) of a blast at x, y - fixed by the seed, and
        kept small while little of the world has been explored."""
        h = _mix(self.seed, x, y, 1)
        return min(RADII[h % 100], self.max_radius()), 1 + ((h >> 8) & 1)

    def max_radius(self):
        """Biggest blast radius for the progress so far: 1 at the start, +1
        for every 30 cells dug, never more than 5."""
        return max(1, min(5, 1 + self.dug // 30))

    def erase_cap(self):
        """Most opened cells one blast may wipe: an eighth of what you dug."""
        return max(3, min(MAX_ERASE, self.dug // 8))

    # ---------------- what to draw ----------------
    def view(self, x, y):
        """An int (opened cell with that number) or HIDDEN/FLAG/CRATER/SCORCH/ASH."""
        c = (x, y)
        if c in self.craters:
            return CRATER
        if c in self.scorch:
            return SCORCH
        n = self.revealed.get(c)
        if n is not None:
            return n
        if c in self.flags:
            return FLAG
        if c in self.ash:
            return ASH
        return HIDDEN

    # ---------------- actions ----------------
    def start(self):
        """Open the safe start area (a new world)."""
        return self.dig(0, 0)

    def dig(self, x, y):
        c = (x, y)
        if c in self.scorch:
            return Outcome(SCORCH)
        if c in self.craters:
            return Outcome(CRATER)
        if c in self.flags:
            return Outcome("flagged")
        if c in self.revealed:
            return self._chord(x, y)
        if self.is_mine(x, y):
            out = Outcome("blast")
            self._blast(x, y, out)
            return self._finish(out)
        out = Outcome("dug")
        out.revealed = self._flood(x, y)
        return self._finish(out)

    def toggle_flag(self, x, y):
        c = (x, y)
        if c in self.scorch:
            return Outcome(SCORCH)
        if c in self.craters:
            return Outcome(CRATER)
        if c in self.revealed:
            return Outcome("revealed")
        if c in self.flags:
            self.flags.discard(c)
            return self._finish(Outcome("unflag"))
        self.flags.add(c)
        out = Outcome("flag")
        if (chunk_of(x, y) in self.solved and c not in self.defused
                and self.is_mine(x, y)):
            # the sector is solved, so this hidden cell is surely a mine
            self.defused.add(c)
            self.points += 1
            out.points = out.defused = 1
        return self._finish(out)

    def repair(self, x, y):
        """Spend points to heal the scorched cells in the 3x3 around x, y."""
        if (x, y) not in self.scorch:
            return Outcome("noop")
        if self.points < REPAIR_COST:
            return Outcome("poor")
        self.points -= REPAIR_COST
        out = Outcome("repair")
        out.points = -REPAIR_COST
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = (x + dx, y + dy)
                if c in self.scorch:
                    self._mend(c)
                    out.healed += 1
        return self._finish(out)

    def find_hint(self, cx, cy, reach=30):
        """A certain move near (cx, cy): (action, (x, y)) with action "dig",
        "flag" or "unflag" (a flag that is surely wrong), or None. Uses only
        what is opened: a number whose unknown neighbours must all be mines or
        all be safe, and two numbers one of which sits inside the other."""
        cons, index = [], {}
        for (x, y), n in self.revealed.items():
            if n == 0 or abs(x - cx) > reach or abs(y - cy) > reach:
                continue
            unk, known = set(), 0
            for nb in self._nbrs((x, y)):
                if nb in self.craters:
                    known += 1
                elif nb not in self.revealed:
                    unk.add(nb)
            if unk:
                cons.append((frozenset(unk), n - known))
        for i, (u, _k) in enumerate(cons):
            for c in u:
                index.setdefault(c, []).append(i)
        safe, mines = set(), set()
        for u, k in cons:
            if k == 0:
                safe |= u
            elif k == len(u):
                mines |= u
        for i, (ua, ka) in enumerate(cons):
            near = {j for c in ua for j in index[c] if j != i}
            for j in near:
                ub, kb = cons[j]
                if ua < ub:
                    diff, dk = ub - ua, kb - ka
                    if dk == 0:
                        safe |= diff
                    elif dk == len(diff):
                        mines |= diff
        found = []
        for c in safe - mines:
            if c in self.scorch or c in self.craters or c in self.revealed:
                continue
            found.append((0 if c not in self.flags else 2, c))
        for c in mines - safe:
            if c in self.scorch or c in self.craters or c in self.flags:
                continue
            found.append((1, c))
        if not found:
            return None
        found.sort(key=lambda t: (t[0], (t[1][0] - cx) ** 2 + (t[1][1] - cy) ** 2))
        order, c = found[0]
        return ("dig", "flag", "unflag")[order], c

    def hint(self, cx, cy, reach=30):
        """Spend HINT_COST points to be shown a certain move."""
        if self.points < HINT_COST:
            return Outcome("poor_hint")
        found = self.find_hint(cx, cy, reach)
        if not found:
            return Outcome("nohint")            # nothing certain: nothing charged
        self.points -= HINT_COST
        out = Outcome("hint")
        out.points = -HINT_COST
        out.action, out.target = found
        return out

    # ---------------- internals ----------------
    def _nbrs(self, c):
        x, y = c
        return [(x + dx, y + dy) for dx, dy in _NB]

    def _reveal(self, c):
        n = self.number(*c)
        self.revealed[c] = n
        self.ash.discard(c)
        self.mended.discard(c)
        self._touched.add(chunk_of(*c))
        self._changed.add(c)
        self.dug += 1
        return n

    def _flood(self, x, y):
        """Open (x, y); a 0 opens its neighbours too, up to FLOOD_CAP cells."""
        queue, count = deque([(x, y)]), 0       # breadth first: a capped flood is a disc
        while queue and count < FLOOD_CAP:
            c = queue.popleft()
            if (c in self.revealed or c in self.scorch or c in self.craters
                    or c in self.flags or self.is_mine(*c)):
                continue
            if self._reveal(c) == 0:
                queue.extend(self._nbrs(c))
            count += 1
        return count

    def _chord(self, x, y):
        """Dig on an opened number whose flags (and craters) match it."""
        c = (x, y)
        marks = sum(1 for nb in self._nbrs(c) if nb in self.flags or nb in self.craters)
        if marks != self.revealed[c]:
            return Outcome("noop")
        out = Outcome("chord")
        for t in self._nbrs(c):
            if (t in self.revealed or t in self.flags or t in self.craters
                    or t in self.scorch):
                continue
            if self.is_mine(*t):
                out.kind = "blast"
                self._blast(*t, out)
            else:
                out.revealed += self._flood(*t)
        if out.kind == "chord" and not out.revealed:
            return Outcome("noop")
        return self._finish(out)

    def _blast(self, x, y, out):
        self.blasts += 1
        c0 = (x, y)
        self.craters.add(c0)
        for s in (self.flags, self.scorch, self.ash, self.mended):
            s.discard(c0)
        self.revealed.pop(c0, None)
        r, fw = self.blast_shape(x, y)
        core, edge = r + 0.5, r + 0.5 + fw
        span = int(math.ceil(edge))
        cells = []
        for dy in range(-span, span + 1):
            for dx in range(-span, span + 1):
                d = math.hypot(dx, dy)
                if 0 < d <= edge:
                    cells.append((d, x + dx, y + dy))
        cells.sort()                    # nearest first: the cap spares the far ones
        erased, cap = 0, self.erase_cap()
        for d, cx, cy in cells:
            c = (cx, cy)
            if c in self.craters:
                continue
            if c in self.scorch and d > core:
                continue                # never soften an older, harder scar
            if d > core:
                # fallout ring: safe cells are opened, mines stay hidden
                # (a flag on a mine stays; a flag on a safe cell is dropped)
                if self.is_mine(cx, cy):
                    continue
                self.flags.discard(c)
                if c not in self.revealed:
                    self._reveal(c)
                    out.revealed += 1
                continue
            opened = c in self.revealed or c in self.flags
            if opened:
                if erased >= cap:
                    continue
                erased += 1
            self.revealed.pop(c, None)
            self.flags.discard(c)
            self.mended.discard(c)
            self.scorch.add(c)
            self.ash.discard(c)
        out.blast, out.radius = c0, r
        out.erased += erased

    def _mend(self, c):
        self.scorch.discard(c)
        self.ash.add(c)
        self.mended.add(c)

    def _settled(self, c):
        """Counts towards healing: an opened cell or a healed one. Flags never
        count (they could be spammed to clear a crater)."""
        return c in self.revealed or c in self.mended

    def _heal(self):
        """One layer of healing, near the cells opened since the last heal:
        scorched cells with enough opened neighbours."""
        changed, self._changed = self._changed, set()
        if not self.scorch or not changed:
            return 0
        near = set()
        for (x, y) in changed:
            for dy in range(-HEAL_REACH, HEAL_REACH + 1):
                for dx in range(-HEAL_REACH, HEAL_REACH + 1):
                    c = (x + dx, y + dy)
                    if c in self.scorch:
                        near.add(c)
        ready = [c for c in near
                 if sum(1 for nb in self._nbrs(c) if self._settled(nb)) >= HEAL_NEED]
        for c in ready:
            self._mend(c)
        return len(ready)

    def _sector_stats(self, ch):
        total = self._safe_total.get(ch)
        if total is None:
            total = 0
            for dy in range(CHUNK):
                for dx in range(CHUNK):
                    if not self.is_mine(ch[0] * CHUNK + dx, ch[1] * CHUNK + dy):
                        total += 1
            self._safe_total[ch] = total
        got = 0
        for dy in range(CHUNK):
            for dx in range(CHUNK):
                if (ch[0] * CHUNK + dx, ch[1] * CHUNK + dy) in self.revealed:
                    got += 1
        return got, total

    def sector_progress(self, x, y):
        """(opened safe cells, safe cells) of the sector holding x, y."""
        return self._sector_stats(chunk_of(x, y))

    def _finish(self, out):
        if out.kind != "blast":           # the blast itself heals nothing
            out.healed += self._heal()
        for ch in sorted(self._touched):
            if ch in self.solved:
                continue
            got, total = self._sector_stats(ch)
            if got >= total:
                self.solved.add(ch)
                mines = CHUNK * CHUNK - total
                pts = max(1, mines)
                good = [c for c in self.flags if chunk_of(*c) == ch
                        and self.is_mine(*c) and c not in self.defused]
                self.defused.update(good)
                pts += len(good)
                out.defused += len(good)
                self.points += pts
                out.points += pts
                out.sectors.append((ch, pts))
        self._touched.clear()
        return out

    # ---------------- saving ----------------
    def to_dict(self):
        def flat(cells):
            return [v for c in sorted(cells) for v in c]
        return {"v": 1, "seed": self.seed, "density": self.density,
                "revealed": flat(self.revealed), "flags": flat(self.flags),
                "craters": flat(self.craters), "scorch": flat(self.scorch),
                "ash": flat(self.ash), "mended": flat(self.mended),
                "solved": flat(self.solved), "defused": flat(self.defused),
                "points": self.points,
                "dug": self.dug, "blasts": self.blasts}

    @classmethod
    def from_dict(cls, d):
        """A World from saved data, or None when the data is not usable."""
        if not isinstance(d, dict) or d.get("v") != 1:
            return None

        def ok(v):
            return isinstance(v, int) and not isinstance(v, bool) and abs(v) < 10 ** 9

        def pairs(key):
            raw = d.get(key, [])
            if not isinstance(raw, list):
                return []
            raw = raw[:len(raw) // 2 * 2]
            return [(raw[i], raw[i + 1]) for i in range(0, len(raw), 2)
                    if ok(raw[i]) and ok(raw[i + 1])]

        def num(key, default=0):
            v = d.get(key, default)
            return v if ok(v) and v >= 0 else default

        seed = d.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            return None                 # without the seed the cells would not match the world
        try:
            w = cls(seed=seed, density=d.get("density", DEFAULT_DENSITY))
        except (TypeError, ValueError):
            return None
        for c in pairs("revealed"):
            w.revealed[c] = w.number(*c)
        w.flags = set(pairs("flags"))
        w.craters = set(pairs("craters"))
        w.scorch = set(pairs("scorch"))
        w.ash = set(pairs("ash"))
        w.mended = set(pairs("mended")) & w.ash
        w.solved = set(pairs("solved"))
        w.defused = set(pairs("defused"))
        w.points, w.dug, w.blasts = num("points"), num("dug"), num("blasts")
        return w
