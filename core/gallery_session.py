# core/gallery_session.py - Gallery Sorter remembers where you left off.
# The sources, destinations and the file you were looking at are saved on every
# change (small JSON, written atomically). On the next visit the screen offers
# "Continue where you left off?". Pure Python, no Kivy.
import os

from core.jsonio import read_json, write_json_atomic

NAME = "last_session.json"


def _path():
    import app_data
    return os.path.join(app_data.subdir("gallery_state"), NAME)


def save(sources, dest_tree, current=None):
    """Remember this state. Nothing worth keeping -> forget (no empty file)."""
    if not sources and not dest_tree:
        clear()
        return False
    try:
        write_json_atomic(_path(), {"v": 1, "sources": list(sources),
                                    "dest_tree": list(dest_tree),
                                    "current": current or ""})
        return True
    except Exception:
        return False


def clear():
    try:
        os.remove(_path())
    except OSError:
        pass


def load():
    """The saved session with folders that no longer exist dropped, or None
    when there is nothing left worth resuming."""
    d = read_json(_path(), None)
    if not isinstance(d, dict):
        return None
    sources = [s for s in d.get("sources", []) if isinstance(s, str) and os.path.isdir(s)]
    dests = [t for t in d.get("dest_tree", [])
             if isinstance(t, dict) and isinstance(t.get("path"), str)
             and os.path.isdir(t["path"])]
    if not sources and not dests:
        return None
    cur = d.get("current") or ""
    return {"sources": sources, "dest_tree": dests,
            "current": cur if isinstance(cur, str) and os.path.isfile(cur) else ""}


def describe(s):
    n, m = len(s["sources"]), len(s["dest_tree"])
    return f"{n} source folder{'s' if n != 1 else ''}, {m} destination{'s' if m != 1 else ''}"
