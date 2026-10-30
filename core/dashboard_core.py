# core/dashboard_core.py - what the Dashboard shows, Kivy-free.
#
# The Dashboard used to be one flat list of every tool. It now shows
#   * a search box: type a few letters and only matching tools are listed,
#   * a "Recent" row with the tools used last,
#   * collapsible sections (Writing, Files, ...), see screens/registry.GROUPS.
# This module only decides WHAT is shown; main.py draws it.
#
# menu = [(route, label), ...] in the user's own order, hidden tools already
# removed (settings_screen.effective_menu_order()).

RECENT_SHOWN = 4          # tools in the "Recent" row
RECENT_KEPT = 8           # remembered (some may be hidden later)
OTHER_KEY, OTHER_TITLE = "other", "Other"


def group_menu(menu, groups):
    """-> [(key, title, [(route, label), ...])]. Sections in `groups` order,
    tools inside in menu (= the user's) order, empty sections left out, and any
    tool no section lists collected in a last "Other" section."""
    by_route = dict(menu)
    order = {r: i for i, (r, _l) in enumerate(menu)}
    claimed = set()
    out = []
    for key, title, routes in groups:
        members = [r for r in routes if r in by_route]
        claimed.update(members)
        members.sort(key=order.__getitem__)    # the USER's order, not the registry's
        if members:
            out.append((key, title, [(r, by_route[r]) for r in members]))
    leftover = [(r, l) for r, l in menu if r not in claimed]
    if leftover:
        out.append((OTHER_KEY, OTHER_TITLE, leftover))
    return out


def search(menu, query, aliases=None):
    """Tools whose name (or alias, see registry.ALIASES) contains every word of
    `query` (case-insensitive). Names that START with the first word come
    first. [] for an empty query."""
    words = query.lower().split()
    if not words:
        return []
    aliases = aliases or {}
    hits = [(r, l) for r, l in menu
            if all(w in l.lower() or w in r.lower().replace("_", " ")
                   or any(w in a.lower() for a in aliases.get(r, ()))
                   for w in words)]
    return sorted(hits, key=lambda rl: not rl[1].lower().startswith(words[0]))


def push_recent(recent, route, keep=RECENT_KEPT):
    """The new recent list after using `route`: it moves to the front."""
    return ([route] + [r for r in recent if r != route])[:keep]


def visible_recent(recent, menu, shown=RECENT_SHOWN):
    """[(route, label)] for the Recent row: only tools still in the menu
    (not hidden, not removed), newest first."""
    by_route = dict(menu)
    return [(r, by_route[r]) for r in recent if r in by_route][:shown]


def toggle_collapsed(collapsed, key):
    """A new list with `key` collapsed, or expanded if it was collapsed."""
    return [k for k in collapsed if k != key] if key in collapsed \
        else list(collapsed) + [key]


def clean_state(recent, collapsed, known_routes, known_groups):
    """Drop unknown routes / groups from saved dashboard state."""
    known_routes, known_groups = set(known_routes), set(known_groups)
    seen, rec = set(), []
    for r in recent if isinstance(recent, list) else []:
        if isinstance(r, str) and r in known_routes and r not in seen:
            seen.add(r)
            rec.append(r)
    col = [k for k in (collapsed if isinstance(collapsed, list) else [])
           if isinstance(k, str) and k in known_groups]
    return rec[:RECENT_KEPT], col


# ── pinned tools, tile layout ───────────────────────────────────────────────
PINNED_KEPT = 12
TILE_MIN_DP = 220          # a tile is at least this wide (dp)
NARROW_DP = 480            # below this window width the Recent row is shorter
RECENT_NARROW = 3


def toggle_pin(pinned, route):
    """A new list with `route` pinned (appended), or unpinned if it was."""
    if route in pinned:
        return [r for r in pinned if r != route]
    return (list(pinned) + [route])[-PINNED_KEPT:]


def clean_routes(routes, known_routes, keep=PINNED_KEPT):
    """Drop unknown / repeated routes from a saved list."""
    known, seen, out = set(known_routes), set(), []
    for r in routes if isinstance(routes, list) else []:
        if isinstance(r, str) and r in known and r not in seen:
            seen.add(r)
            out.append(r)
    return out[:keep]


def tile_columns(width, dp_unit=1.0):
    """How many tiles fit side by side in a window `width` pixels wide;
    dp_unit is the pixels-per-dp factor (kivy.metrics.dp(1))."""
    return max(1, int(width // (TILE_MIN_DP * dp_unit)))


def recent_shown(width, dp_unit=1.0):
    return RECENT_NARROW if width < NARROW_DP * dp_unit else RECENT_SHOWN
