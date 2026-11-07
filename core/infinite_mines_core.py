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
#   ash      the next 1-2 cells out: pale, numbers erased (they can be dug again)
# Scorched cells heal from the edge inwards as the cells around them get
# solved (opened, or a correct flag). Healing runs one layer per action, so it
# is slow on purpose. Opened cells lost to a blast are capped (MAX_ERASE).
import math
import random
from collections import deque

HIDDEN, FLAG, CRATER, SCORCH, ASH = "hidden", "flag", "crater", "scorch", "ash"

CHUNK = 9                  # sector size (cells per side)
SAFE_RADIUS = 2            # nothing within this many cells of (0,0) is a mine
DEFAULT_DENSITY = 0.17
RADII = [1] * 30 + [2] * 25 + [3] * 20 + [4] * 15 + [5] * 10   # blast radius odds
MAX_ERASE = 60             # most opened/flagged cells one blast can wipe
HEAL_NEED = 3              # solved neighbours a scorched cell needs to heal
REPAIR_COST = 3            # points for an instant repair (3x3 around a cell)
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
                 "sectors", "points")

    def __init__(self, kind):
        self.kind = kind
        self.revealed = 0       # cells opened
        self.blast = None       # (x, y) of the last mine stepped on
        self.radius = 0
        self.erased = 0         # opened/flagged cells the blast wiped
        self.healed = 0         # scorched cells that healed
        self.sectors = []       # [((cx, cy), points)] newly solved
        self.points = 0         # points gained (repair: spent, negative)


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
        self.solved = set()     # sectors already paid out
        self.points = 0
        self.dug = 0
        self.blasts = 0
        self._touched = set()
        self._safe_total = {}

    # ---------------- the world itself (pure) ----------------
    def is_mine(self, x, y):
        if abs(x) <= SAFE_RADIUS and abs(y) <= SAFE_RADIUS:
            return False
        return (_mix(self.seed, x, y, 0) >> 11) / 9007199254740992.0 < self.density

    def number(self, x, y):
        return sum(1 for dx, dy in _NB if self.is_mine(x + dx, y + dy))

    def blast_shape(self, x, y):
        """(radius, fallout width) of a blast at x, y - fixed by the seed."""
        h = _mix(self.seed, x, y, 1)
        return RADII[h % 100], 1 + ((h >> 8) & 1)

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
        return self._finish(Outcome("flag"))

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
        erased = 0
        for d, cx, cy in cells:
            c = (cx, cy)
            if c in self.craters:
                continue
            opened = c in self.revealed or c in self.flags
            if opened:
                if erased >= MAX_ERASE:
                    continue
                erased += 1
            if c in self.scorch and d > core:
                continue                # never soften an older, harder scar
            self.revealed.pop(c, None)
            self.flags.discard(c)
            self.mended.discard(c)
            if d <= core:
                self.scorch.add(c)
                self.ash.discard(c)
            else:
                self.ash.add(c)
        out.blast, out.radius = c0, r
        out.erased += erased

    def _mend(self, c):
        self.scorch.discard(c)
        self.ash.add(c)
        self.mended.add(c)

    def _settled(self, c):
        return (c in self.revealed or c in self.mended
                or (c in self.flags and self.is_mine(*c)))

    def _heal(self):
        """One layer of healing: scorched cells with enough solved neighbours."""
        if not self.scorch:
            return 0
        ready = [c for c in self.scorch
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
        out.healed += self._heal()
        for ch in sorted(self._touched):
            if ch in self.solved:
                continue
            got, total = self._sector_stats(ch)
            if got >= total:
                self.solved.add(ch)
                mines = CHUNK * CHUNK - total
                pts = max(1, mines)
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
                "solved": flat(self.solved), "points": self.points,
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

        try:
            w = cls(seed=d.get("seed"), density=d.get("density", DEFAULT_DENSITY))
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
        w.points, w.dug, w.blasts = num("points"), num("dug"), num("blasts")
        return w
