# Infinite Mines: design handoff for the new project

Paste this file at the start of a new chat. It combines the original idea, the
design choices made so far, and what the Srboli demo already proves.

## The idea in one paragraph
An endless minesweeper. You pan around a map that is generated as you explore
(it never exists "all at once"). It is inspired by a mobile game called
Infinite Minesweeper, whose map is made of 9x9 boards that connect. That game
punishes a mistake with a paywall: pay in-game money, watch an ad, or get the
8 cells around the mine for free, and that gets annoying. This project replaces
the paywall with an explosion that costs the player progress but never blocks
play, and lets points earned by playing pay for repairs.

## Decisions so far
- **Separate project.** Not a Story Cards minigame (those are 10-15 second
  games for waiting between turns) and not part of Srboli beyond a raw demo.
- **The demo lives in Srboli** (`core/infinite_mines_core.py` +
  `screens/infinite_mines_screen.py`, tool "Infinite Mines"). It has the core
  rules only: no lore, no leaderboard, no shop. The core has no UI imports, so
  it can be copied into the new project as is.
- **Procedural, border-less world.** Mines come from a hash of
  `(seed, x, y)`, so any cell, and the numbers on any edge, can be computed
  without building the neighbouring area. The 9x9 grids are only a way to
  group cells (a sector is solved when all its safe cells are open); they do
  not decide how the world is generated.
- **Sparse saves.** Only what the player changed is stored (opened cells,
  flags, craters, scorch, ash, solved sectors).
- **Safe start.** Nothing within 2 cells of the origin is a mine; a new world
  opens that area.
- **Capped flood.** One dig opens at most 3000 cells (a 0 next to unopened
  cells can be tapped again to carry on), so low density cannot run away.

## The explosion (the core mechanic)
Original wording, kept: the mine you stepped on is black and that square
cannot be recovered (or only by a heavy, long process). Around it is brown,
1-5 cells of explosion radius. One or two cells beyond that are white and their
numbers are gone too. If it is near an area you already cleared, it can delete
some of your progress. By solving nearby mines and finding numbers, the brown
area slowly "fixes" (in lore) and technically disappears into white blocks.
The more enclosed it is by solved cells, the faster it heals.

As built in the demo:
- **Crater:** the mine you stepped on turns black and counts as a known mine
  for its neighbours' numbers. It is permanent.
- **Scorch zone:** brown cells within radius 1-5 (odds 30/25/20/15/10 %) cannot
  be touched. You work around them or heal them.
- **Fallout ring (ash):** the next 1-2 cells out are pale with their numbers
  erased. They can be dug again.
- **Healing:** a scorched cell heals once at least 3 of its 8 neighbours are
  solved (opened, healed, or a correct flag). Only the outside edge can heal at
  first, then one layer per action, so the brown shrinks from the edge inwards.
  A healed cell turns pale ("mended") and counts as solved for the next layer.
- **Fairness:** erased numbers can always be recomputed because mines come from
  the seed. A blast wipes at most 60 opened or flagged cells, nearest first.
- **Instant repair:** 3 points heal the 3x3 around a scorched cell. Points come
  from solved sectors (the sector's mine count, at least 1), so it replaces the
  ad or the gems by playing instead of paying.
- Radius and fallout width come from the seed and the mine's position, so the
  same blast always looks the same.

## Controls in the demo
Tap = the chosen mode (Dig, Flag, Repair). Long-press = the other of Dig/Flag.
Tapping an opened number whose flags match it opens the rest (chord; craters
count as flags). Drag pans, pinch or mouse wheel zooms. Sector borders are
drawn thicker every 9 cells.

## Not decided yet (for the new chat)
1. **Style.** "Mindustry style" came up: a build and automation layer on top
   (sectors as bases, collected resources, machines that clear or flag cells).
   Is the core loop still the minesweeper, with building as a reward?
2. **Story or setting.** Mining edge, exploration, connection, building. The
   cheapest is a sapper reclaiming a planet, where the explosion is "the cost"
   and clearing sectors is "the income".
3. **Healing numbers.** The 3-neighbour rule, the one-layer-per-action speed,
   whether a timer should also heal, and whether wrong flags should count.
   (The demo counts only correct flags, which leaks a little information.)
4. **Scale of damage.** The 60-cell cap, radius odds, whether big blasts should
   be rarer near the start, and whether the first blast in a sector is free.
5. **Economy.** Points per sector, repair cost and size, whether points buy
   other things, and what a "gem" or ad would be in a free version.
6. **Difficulty.** Density (now 17 %), whether it grows with distance, and
   whether the map should avoid forced guesses.
7. **Scope.** Leaderboards, daily seeds, multiplayer on a shared seed (the seed
   makes that cheap), and which platforms (it should run on Android).

## Technical notes
- Python 3 + Kivy (same as Srboli and Story Cards). The map widget draws only
  the visible cells, with cached number textures and a scissor clip.
  Zoomed far out (about 900 cells) it is the heaviest case on a phone: check
  it on a real device, and batch the cells into fewer canvas instructions if it
  stutters.
- The hash is a 64-bit splitmix-style mix, identical on every platform.
- Tests: `tests/test_infinite_mines_core.py` (rules, blasts, healing, repair,
  sectors, chord, saves, no display needed) and
  `tests/test_infinite_mines_screen.py` (screen, needs a display).
- Touch handling: own tap slop (10 dp) and long-press timer on the map widget,
  so a drag is never a dig.
