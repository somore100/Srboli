# core/tool_removal.py - removing tools for good (and bringing them back).
# "Hide" (Settings) only drops a tool from the Dashboard list; "remove" also
# stops it being opened by a shortcut or built at start-up. Nothing is deleted
# from the app itself, so a removed tool can always be restored.

PROTECTED = {"quickswitcher"}      # the shortcut engine itself is always kept


def clean(removed, known):
    """The removed list reduced to routes that exist and may be removed."""
    out = []
    for r in removed or []:
        if r in known and r not in PROTECTED and r not in out:
            out.append(r)
    return out


def remove(removed, route, known):
    return clean(list(removed or []) + [route], known)


def restore(removed, route):
    return [r for r in (removed or []) if r != route]


def is_removed(removed, route):
    return route in (removed or [])
