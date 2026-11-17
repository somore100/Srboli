# tests/test_infinite_mines_core.py - no display needed (python3 tests/test_infinite_mines_core.py)
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import infinite_mines_core as im

def first_mine(w, y=0, lo=3, hi=200):
    for x in range(lo, hi):
        if w.is_mine(x, y):
            return x, y
    raise AssertionError("no mine found")

# ---- the world is a pure function of (seed, x, y)
a, b, c = im.World(seed=7), im.World(seed=7), im.World(seed=8)
grid = [(x, y) for x in range(-60, 60) for y in range(-60, 60)]
assert [a.is_mine(*p) for p in grid] == [b.is_mine(*p) for p in grid]
assert [a.is_mine(*p) for p in grid] != [c.is_mine(*p) for p in grid]
assert a.is_mine(-10 ** 6, -10 ** 6) in (True, False)            # far and negative is fine
for x in range(-im.SAFE_RADIUS, im.SAFE_RADIUS + 1):
    for y in range(-im.SAFE_RADIUS, im.SAFE_RADIUS + 1):
        assert not a.is_mine(x, y)
big = [(x, y) for x in range(-150, 150) for y in range(-150, 150)]
share = sum(a.is_mine(*p) for p in big) / len(big)
assert abs(share - im.DEFAULT_DENSITY) < 0.015, share
assert not any(im.World(seed=3, density=0).is_mine(*p) for p in grid)
# a number never depends on what was opened before
w = im.World(seed=7); w.start()
assert w.number(40, 40) == a.number(40, 40) == sum(a.is_mine(40 + dx, 40 + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)

# ---- a new world opens a safe area, no blast
w = im.World(seed=11); out = w.start()
assert out.kind == "dug" and out.revealed >= 9 and not w.craters
assert all(w.revealed[p] == w.number(*p) for p in w.revealed)
assert w.view(0, 0) == w.revealed[(0, 0)] and w.view(500, 500) == im.HIDDEN
assert w.dig(0, 0).kind in ("noop", "chord")                      # digging an open cell is not a blast

# ---- a flood never runs away
z = im.World(seed=5, density=0); z.start()
assert z.dug <= im.FLOOD_CAP + 1 and z.dug > 1000

# ---- flags
w = im.World(seed=11); w.start()
assert w.toggle_flag(300, 300).kind == "flag" and w.view(300, 300) == im.FLAG
assert w.dig(300, 300).kind == "flagged" and (300, 300) not in w.revealed
assert w.toggle_flag(300, 300).kind == "unflag" and w.view(300, 300) == im.HIDDEN
assert w.toggle_flag(0, 0).kind == "revealed"

# ---- a blast: crater, scorch (brown), ash (pale), nothing else touched
w = im.World(seed=21); w.start()
mx, my = first_mine(w, lo=20)
r, fw = w.blast_shape(mx, my)
assert 1 <= r <= 5 and fw in (1, 2) and w.blast_shape(mx, my) == (r, fw)
out = w.dig(mx, my)
assert out.kind == "blast" and out.blast == (mx, my) and out.radius == r
assert w.view(mx, my) == im.CRATER and w.blasts == 1
import math
for dx in range(-8, 9):
    for dy in range(-8, 9):
        if not (dx or dy):
            continue
        d = math.hypot(dx, dy); v = w.view(mx + dx, my + dy)
        if d <= r + 0.5:
            assert v == im.SCORCH, (dx, dy, v)
        elif d <= r + 0.5 + fw:
            # fallout ring: safe cells opened with their number, mines hidden
            if w.is_mine(mx + dx, my + dy):
                assert v in (im.HIDDEN, im.FLAG, im.CRATER, im.SCORCH), (dx, dy, v)
            else:
                assert isinstance(v, int) and v == w.number(mx + dx, my + dy), (dx, dy, v)
        else:
            assert v != im.SCORCH and v != im.ASH
assert w.dig(mx, my).kind == im.CRATER                            # a crater is permanent
assert w.toggle_flag(mx, my).kind == im.CRATER
sx, sy = next(iter(w.scorch))
assert w.dig(sx, sy).kind == im.SCORCH and w.toggle_flag(sx, sy).kind == im.SCORCH
assert not w.ash                                                   # fallout is opened, not pale
# the crater counts as a known mine for the numbers next to it
nx = mx + r + 3
assert w.number(nx, my) == sum(w.is_mine(nx + i, my + j) for i in (-1, 0, 1) for j in (-1, 0, 1) if i or j)

# ---- fairness: a blast never wipes more than MAX_ERASE opened cells
z = im.World(seed=5, density=0); z.start()                        # ~3000 opened cells
z.density = 0.0
before = len(z.revealed)
o = im.Outcome("blast")
z._blast(0, 0, o)                                                 # worst case: in the middle of it all
assert o.erased == im.MAX_ERASE, o.erased                         # capped
assert before - len(z.revealed) <= im.MAX_ERASE + 1               # +1: the mine's own cell
assert len(z.scorch) > 0 and (0, 0) in z.craters

# ---- healing: from the edge inwards, one layer per action, and never faster
import math as _m
z = im.World(seed=5, density=0)
bx = next(x for x in range(30, 400) if z.blast_shape(x, 0)[0] >= 3)
r, fw = z.blast_shape(bx, 0)
z._blast(bx, 0, im.Outcome("blast"))
n_scorch = len(z.scorch); assert n_scorch >= 28 and len(z.revealed) >= 8
assert len(z.scorch) == n_scorch                                  # the blast itself healed nothing
for dx in range(-12, 13):                                         # solve everything outside the scorch
    for dy in range(-12, 13):
        if _m.hypot(dx, dy) > r + 0.5 and (bx + dx, dy) not in z.revealed:
            z._reveal((bx + dx, dy))
counts = [len(z.scorch)]
for _ in range(10):
    z.toggle_flag(900, 900); z.toggle_flag(900, 900)              # harmless actions, one layer each
    counts.append(len(z.scorch))
assert counts == sorted(counts, reverse=True), counts
assert counts[0] == n_scorch and 0 < counts[1] < n_scorch, counts   # slow: one layer, not all at once
assert counts[-1] == 0, counts                                    # and it does finish, edge inwards
assert (bx, 0) in z.craters and not z.scorch
# a hidden mine next to the rim is solved only by a correct flag
w = im.World(seed=21); w.start()
mx, my = first_mine(w, lo=20); w.dig(mx, my)
n0 = len(w.scorch)
w._heal()                                  # only the rim, next to the opened fallout ring, can mend
assert len(w.scorch) >= n0 - (n0 // 2 + 8)
assert (mx + 0, my + 1) in w.scorch or (mx + 1, my) in w.scorch or w.blast_shape(mx, my)[0] == 1

# ---- instant repair: costs points, heals a 3x3
z = im.World(seed=5, density=0); z._blast(30, 0, im.Outcome("blast"))
cell = next(iter(z.scorch))
assert z.repair(*cell).kind == "poor" and z.points == 0
z.points = 10
out = z.repair(*cell)
assert out.kind == "repair" and out.healed >= 1 and z.points == 10 - im.REPAIR_COST
assert cell not in z.scorch and cell in z.ash and cell in z.mended
assert z.repair(10 ** 4, 10 ** 4).kind == "noop"

# ---- sectors pay out once
z = im.World(seed=5, density=0); out = z.start()
assert z.solved and z.points == len(z.solved) == sum(p for _, p in out.sectors)
p0 = z.points
z.dig(0, 0); z.dig(1, 1)
assert z.points == p0                                             # no double award
assert all(isinstance(ch, tuple) for ch in z.solved)
got, total = z.sector_progress(0, 0); assert got == total == 81

# ---- chord: a number whose flags match it opens the rest; a wrong flag blasts
def find_number(world):
    """An opened number n >= 1 with more hidden neighbours than mines."""
    for p, n in sorted(world.revealed.items()):
        hidden = [nb for nb in world._nbrs(p) if nb not in world.revealed]
        mines = [nb for nb in hidden if world.is_mine(*nb)]
        if n >= 1 and len(mines) == n and len(hidden) > n:
            return p, n, hidden, mines
    raise AssertionError("no usable number near the start")

w = im.World(seed=11); w.start()
p, n, hidden, mines = find_number(w)
assert w.dig(*p).kind == "noop"                                   # no flags yet: nothing happens
for m in mines:
    w.toggle_flag(*m)
out = w.dig(*p)
assert out.kind == "chord" and out.revealed >= 1 and not w.craters

w = im.World(seed=11); w.start()
p, n, hidden, mines = find_number(w)
safe = next(h for h in hidden if not w.is_mine(*h))
for m in mines[:-1]:
    w.toggle_flag(*m)
w.toggle_flag(*safe)                                              # n flags, one of them wrong
out = w.dig(*p)
assert out.kind == "blast" and w.craters and mines[-1] in w.craters

# ---- saving: round trip, tolerant of garbage
w = im.World(seed=21); w.start(); w.toggle_flag(300, 300); w.dig(*first_mine(w, lo=20)); w.points = 4
s = json.loads(json.dumps(w.to_dict()))
r = im.World.from_dict(s)
assert r.seed == w.seed and r.revealed == w.revealed and r.flags == w.flags
assert r.craters == w.craters and r.scorch == w.scorch and r.ash == w.ash
assert r.mended == w.mended and r.solved == w.solved
assert (r.points, r.dug, r.blasts) == (w.points, w.dug, w.blasts)
assert [r.view(x, y) for x, y in grid[:500]] == [w.view(x, y) for x, y in grid[:500]]
for big in (2017031098, 2 ** 31 - 1, 10 ** 9, 12345):                # seeds are random up to 2**31: all must survive a save
    assert im.World.from_dict(json.loads(json.dumps(im.World(seed=big).to_dict()))).seed == big
for bad in (None, [], "x", {}, {"v": 2}, {"v": 1, "seed": "abc"}):
    assert im.World.from_dict(bad) is None, bad                      # unusable saves are rejected
g = im.World.from_dict({"v": 1, "seed": 3, "revealed": [1, 2, 3], "flags": "no", "craters": [1, "a", 2, 3],
                        "points": -5, "dug": True, "scorch": [10 ** 12, 1]})
assert g is not None and g.points == 0 and g.dug == 0 and not g.scorch and (1, 2) in g.revealed
assert g.craters == {(2, 3)}
print("infinite mines core OK")


# ---- recovery without guessing: after a blast, every hidden cell left in the
# fallout ring is a mine (all safe ones there were opened for the player)
for seed in range(1, 40):
    w = im.World(seed=seed); w.start()
    mx, my = first_mine(w, lo=15)
    w.dig(mx, my)
    r, fw = w.blast_shape(mx, my)
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            d = math.hypot(dx, dy)
            c = (mx + dx, my + dy)
            if r + 0.5 < d <= r + 0.5 + fw and w.view(*c) == im.HIDDEN:
                assert w.is_mine(*c), (seed, dx, dy)

# ---- defusing: flags pay when the sector is solved, never at flag time
w = im.World(seed=3); w.start()
assert w.toggle_flag(40, 40).points == 0                           # no tell-tale reward
w.toggle_flag(40, 40)
ch = (0, 0)
mines0 = [(x, y) for x in range(0, 9) for y in range(0, 9) if w.is_mine(x, y)]
assert mines0
for x in range(0, 9):
    for y in range(0, 9):
        if not w.is_mine(x, y) and (x, y) not in w.revealed:
            w._reveal((x, y))
w.flags.add(mines0[0])                                              # one correct flag
w.flags.add((-30, -30)) if not w.is_mine(-30, -30) else None        # a wrong one elsewhere pays nothing
before = w.points
out = w.toggle_flag(500, 500)                                       # any action finishes the sector
sec = dict(out.sectors)
assert ch in sec and out.defused == 1, (out.sectors, out.defused)
assert sec[ch] == max(1, len(mines0)) + 1                           # mines + 1 defused flag
assert mines0[0] in w.defused
# flagging a mine of a solved sector pays once
o = w.toggle_flag(*mines0[1]) if len(mines0) > 1 else None
if o:
    assert o.defused == 1 and o.points == 1
    p0 = w.points; w.toggle_flag(*mines0[1]); w.toggle_flag(*mines0[1])
    assert w.points == p0                                            # not twice
r = im.World.from_dict(w.to_dict())
assert r.defused == w.defused

# ---- hints: only certain moves, cost points, nothing charged when none
import random
bad = 0; checked = 0
for seed in range(1, 12):
    w = im.World(seed=seed); w.start()
    rnd = random.Random(seed)
    for step in range(60):
        h = w.find_hint(0, 0, reach=40)
        if h:
            act, c = h; checked += 1
            if act == "dig": assert not w.is_mine(*c), (seed, c)
            elif act == "flag": assert w.is_mine(*c), (seed, c)
            else: assert not w.is_mine(*c)
            if act == "dig": w.dig(*c)
            elif act == "flag": w.toggle_flag(*c)
            else: w.toggle_flag(*c)
        else:
            cells = [c for c in w.revealed if w.revealed[c] == 0]
            x, y = rnd.choice(cells) if cells else (0, 0)
            nb = [(x + dx, y + dy) for dx in (-2, -1, 0, 1, 2) for dy in (-2, -1, 0, 1, 2)]
            safe = [c for c in nb if not w.is_mine(*c) and c not in w.revealed and c not in w.scorch]
            if safe: w.dig(*rnd.choice(safe))
assert checked > 30, checked
w = im.World(seed=3); w.start(); w.points = 1
assert w.hint(0, 0).kind == "poor_hint" and w.points == 1
w.points = 10
o = w.hint(0, 0)
assert o.kind in ("hint", "nohint")
assert w.points == (10 - im.HINT_COST if o.kind == "hint" else 10)
if o.kind == "hint":
    assert o.action in ("dig", "flag", "unflag") and o.target
print("infinite mines recovery/defuse/hint ok")
