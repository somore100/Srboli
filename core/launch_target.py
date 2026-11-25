# core/launch_target.py - "open Srboli straight on one tool": the --open command-line flag,
# turning words ("paint", "Drawing") into a tool route, and a small request file so a second
# launch can hand its target to the copy that is already running. No Kivy.
import os
import re
import time

REQUEST_NAME = ".srboli_open_request"
STALE_S = 30


def extract_open(argv):
    """(target text or None, argv without the flag). Handles `--open x` and `--open=x`.
    Must run before Kivy is imported: Kivy aborts on flags it does not know."""
    out, target, i = [], None, 0
    while i < len(argv):
        a = argv[i]
        if a == "--open" and i + 1 < len(argv):
            target, i = argv[i + 1], i + 2
            continue
        if a.startswith("--open="):
            target, i = a[len("--open="):], i + 1
            continue
        out.append(a)
        i += 1
    return target, out


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def resolve(text, screens=None, labels=None, aliases=None):
    """The route a user's words mean, or None. Matches the route id, the label, then aliases;
    exact matches first, then a unique 'starts with'."""
    if screens is None:
        from screens import registry as R
        screens, labels, aliases = [r for r, _, _ in R.SCREENS], R.LABELS, R.ALIASES
    labels, aliases = labels or {}, aliases or {}
    q = _norm(text)
    if not q:
        return None
    for r in screens:
        if q == _norm(r) or q == _norm(labels.get(r, "")):
            return r
    for r in screens:
        if q in {_norm(a) for a in aliases.get(r, [])}:
            return r
    hits = [r for r in screens if _norm(r).startswith(q) or _norm(labels.get(r, "")).startswith(q)]
    return hits[0] if len(hits) == 1 else None


def open_args(route):
    """Extra command-line words that start Srboli on this tool."""
    return ["--open", route]


def request_path(folder):
    return os.path.join(folder, REQUEST_NAME)


def write_request(folder, target):
    try:
        os.makedirs(folder, exist_ok=True)
        with open(request_path(folder), "w", encoding="utf-8") as f:
            f.write(str(target))
        return True
    except OSError:
        return False


def take_request(folder, now=None):
    """The waiting target (and delete the file), or None. Old requests are dropped."""
    p = request_path(folder)
    try:
        age = (now or time.time()) - os.path.getmtime(p)
        with open(p, encoding="utf-8") as f:
            text = f.read().strip()
        os.remove(p)
    except OSError:
        return None
    return text if text and age <= STALE_S else None


def tool_argv(ui_cmd, route):
    """The full command that starts Srboli on one tool."""
    return list(ui_cmd) + open_args(route)


def open_file_argv(path):
    """Command that opens a file or folder with whatever the desktop uses for it."""
    return ["xdg-open", path]


def tool_choices(screens=None, labels=None):
    """[(label, route)] for the tool picker, in Dashboard order."""
    if screens is None:
        from screens import registry as R
        screens, labels = [r for r, _, _ in R.SCREENS], R.LABELS
    return [(labels.get(r) or r.replace("_", " ").title(), r) for r in screens]
