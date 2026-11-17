# core/bulk_rename_core.py - rename many files at once, safely.
# Pure Python, no Kivy.
#
#   RULES               the chain of steps (replace, case, number, date, ...)
#   list_files(folder)  the files to work on (optionally filtered like "*.jpg")
#   build_plan(...)     old name -> new name for every file, with a status
#                       ("ok", "same", "conflict", "invalid"); nothing is touched
#   apply_plan(...)     does it in two phases, so swaps and chains work, rolls
#                       everything back if one rename fails, and records an undo
#   undo_last(...)      puts the names back (only if nothing changed since)

import datetime
import fnmatch
import os
import re
import time
import uuid

from core import jsonio

UNDO_KEEP = 20
BAD_CHARS = '<>:"/\\|?*'
MAX_NAME = 255
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}


class RenameError(Exception):
    """A problem worded for the user."""


# op -> (label, [(field, hint)])   fields are the option boxes the op needs
RULES = {
    "replace":   ("Replace text", [("a", "find"), ("b", "replace with")]),
    "regex":     ("Replace with regex", [("a", "pattern"), ("b", "replace with (\\1)")]),
    "upper":     ("UPPERCASE name", []),
    "lower":     ("lowercase name", []),
    "title":     ("Title Case name", []),
    "prefix":    ("Add at the start", [("a", "text")]),
    "suffix":    ("Add at the end (before .ext)", [("a", "text")]),
    "cut_start": ("Remove first N characters", [("a", "N")]),
    "cut_end":   ("Remove last N characters", [("a", "N")]),
    "spaces":    ("Spaces to _ (or text)", [("a", "replacement, default _")]),
    "clean":     ("Remove odd characters", []),
    "trim":      ("Trim spaces and dots at the ends", []),
    "number":    ("Add a number at the end", [("a", "start (1)"), ("b", "digits (e.g. 3 = 001)")]),
    "number_front": ("Add a number at the start", [("a", "start (1)"), ("b", "digits (e.g. 3 = 001)")]),
    "date":      ("Add the file's date at the start", [("a", "format (%Y-%m-%d)")]),
    "date_end":  ("Add the file's date at the end", [("a", "format (%Y-%m-%d)")]),
    "template":  ("New name from a pattern", [("a", "e.g. Holiday_{n}  ({name} {n} {date} {parent})")]),
    "ext_lower": ("lowercase extension", []),
    "ext_set":   ("Change the extension", [("a", "new extension, e.g. jpg")]),
}

SORTS = {"name": "Name (natural)", "date": "Date modified", "size": "Size"}


def _natural(s):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def split_ext(filename):
    """('photo', '.jpg'). A leading dot is part of the name (.bashrc has no ext);
    'a.tar.gz' keeps '.gz' as the extension."""
    stem, ext = os.path.splitext(filename)
    return stem, ext


def _int(text, default, what):
    text = (text or "").strip()
    if not text:
        return default
    try:
        n = int(text)
    except ValueError:
        raise RenameError(f"{what} must be a whole number.")
    if n < 0:
        raise RenameError(f"{what} can't be negative.")
    return n


def check_rules(rules):
    """Raises RenameError for a rule that can't work (bad regex, bad numbers)."""
    for r in rules:
        op = r.get("op")
        if op not in RULES:
            raise RenameError("Unknown rule.")
        a, b = r.get("a", ""), r.get("b", "")
        if op == "replace" and not a:
            raise RenameError("'Replace text' needs the text to find.")
        if op == "regex":
            if not a:
                raise RenameError("The regex rule needs a pattern.")
            try:
                re.sub(a, b, "test")
            except (re.error, IndexError) as e:
                raise RenameError(f"That regular expression doesn't work: {e}")
        if op in ("cut_start", "cut_end"):
            _int(a, 0, "N")
        if op in ("number", "number_front"):
            _int(a, 1, "The start")
            _int(b, 0, "The digits")
        if op == "template" and not a:
            raise RenameError("The pattern is empty.")
        if op == "ext_set" and not a.strip().strip("."):
            raise RenameError("Type the new extension.")
        if op in ("date", "date_end"):
            try:
                datetime.datetime(2000, 1, 2).strftime(a or "%Y-%m-%d")
            except ValueError:
                raise RenameError("That date format isn't valid.")


def apply_rules(rules, filename, index, mtime, parent=""):
    """The new file name for one file (rules run top to bottom).
    `index` is the 0-based position in the sorted list, for numbering."""
    stem, ext = split_ext(filename)
    when = datetime.datetime.fromtimestamp(mtime)
    for r in rules:
        op, a, b = r["op"], r.get("a", ""), r.get("b", "")
        if op == "replace":
            stem = stem.replace(a, b)
        elif op == "regex":
            stem = re.sub(a, b, stem)
        elif op == "upper":
            stem = stem.upper()
        elif op == "lower":
            stem = stem.lower()
        elif op == "title":
            stem = stem.title()
        elif op == "prefix":
            stem = a + stem
        elif op == "suffix":
            stem = stem + a
        elif op == "cut_start":
            stem = stem[_int(a, 0, "N"):]
        elif op == "cut_end":
            n = _int(a, 0, "N")
            stem = stem[:-n] if n else stem
        elif op == "spaces":
            stem = stem.replace(" ", a if a != "" else "_")
        elif op == "clean":
            stem = re.sub(r"[^\w\-. ()\[\]]", "", stem)
        elif op == "trim":
            stem = stem.strip(" .")
        elif op in ("number", "number_front"):
            n = _int(a, 1, "The start") + index
            num = str(n).zfill(_int(b, 0, "The digits"))
            stem = f"{stem}_{num}" if op == "number" else f"{num}_{stem}"
        elif op in ("date", "date_end"):
            d = when.strftime(a or "%Y-%m-%d")
            stem = f"{d}_{stem}" if op == "date" else f"{stem}_{d}"
        elif op == "template":
            n = 1 + index
            stem = (a.replace("{name}", stem).replace("{n}", str(n))
                    .replace("{date}", when.strftime("%Y-%m-%d"))
                    .replace("{parent}", parent))
        elif op == "ext_lower":
            ext = ext.lower()
        elif op == "ext_set":
            e = a.strip().lstrip(".")
            ext = "." + e if e else ""
    return stem + ext


def list_files(folder, pattern="", sort="name", reverse=False):
    """Files (not folders) directly inside `folder`, sorted. `pattern` is a
    glob like '*.jpg' (several separated by spaces or commas; case-insensitive)."""
    if not os.path.isdir(folder):
        raise RenameError("That folder doesn't exist.")
    pats = [p.lower() for p in re.split(r"[,\s]+", pattern.strip()) if p]
    items = []
    try:
        names = os.listdir(folder)
    except OSError as e:
        raise RenameError(f"Can't read that folder: {e}")
    for name in names:
        path = os.path.join(folder, name)
        if (name.startswith(".srboli-") or not os.path.isfile(path)
                or os.path.islink(path)):
            continue
        if pats and not any(fnmatch.fnmatch(name.lower(), p) for p in pats):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        items.append((name, st.st_mtime, st.st_size))
    key = {"name": lambda t: _natural(t[0]), "date": lambda t: (t[1], _natural(t[0])),
           "size": lambda t: (t[2], _natural(t[0]))}.get(sort, lambda t: _natural(t[0]))
    items.sort(key=key, reverse=reverse)
    return items


def problem_with(name):
    """Why a file name can't be used, or '' if it is fine."""
    if not name or not name.strip():
        return "empty name"
    if len(name.encode("utf-8")) > MAX_NAME:
        return "name too long"
    if any(c in name for c in BAD_CHARS) or any(ord(c) < 32 for c in name):
        return "contains a character that isn't allowed (" + BAD_CHARS + ")"
    if name in (".", "..") or name.endswith((" ", ".")):
        return "can't end with a space or dot"
    if name.split(".")[0].lower() in RESERVED:
        return "reserved name on Windows"
    return ""


def build_plan(folder, rules, pattern="", sort="name", reverse=False):
    """List of dicts: src, dst (full paths), old, new, status, why.
    status: ok | same | conflict | invalid. Nothing is changed on disk."""
    check_rules(rules)
    files = list_files(folder, pattern, sort, reverse)
    parent = os.path.basename(os.path.abspath(folder))
    plan = []
    for i, (name, mtime, _size) in enumerate(files):
        new = apply_rules(rules, name, i, mtime, parent)
        plan.append({"old": name, "new": new, "src": os.path.join(folder, name),
                     "dst": os.path.join(folder, new), "status": "ok", "why": ""})
    case_fold = _case_insensitive(folder)
    fold = (lambda x: x.lower()) if case_fold else (lambda x: x)
    taken = {}
    for p in plan:
        why = problem_with(p["new"])
        if why:
            p["status"], p["why"] = "invalid", why
        elif p["new"] == p["old"]:
            p["status"] = "same"
        taken.setdefault(fold(p["new"]), []).append(p)
    for group in taken.values():
        if len(group) > 1:
            for p in group:
                if p["status"] == "ok":
                    p["status"], p["why"] = "conflict", "another file gets the same new name"
    # a target that already exists is fine only if that file is itself being renamed away
    moving = {fold(p["old"]) for p in plan if p["status"] == "ok"}
    for p in plan:
        if (p["status"] == "ok" and os.path.lexists(p["dst"])
                and fold(p["new"]) not in moving):
            p["status"], p["why"] = "conflict", "a file with that name already exists"
    return plan


def _case_insensitive(folder):
    """True when 'A' and 'a' are the same file in this folder (Windows, macOS)."""
    name = f".srboli-case-{uuid.uuid4().hex[:8]}"
    probe = os.path.join(folder, name)
    try:
        with open(probe, "w"):
            pass
        try:
            return os.path.exists(os.path.join(folder, name.upper()))
        finally:
            os.remove(probe)
    except OSError:
        return False


def summary(plan):
    n = {"ok": 0, "same": 0, "conflict": 0, "invalid": 0}
    for p in plan:
        n[p["status"]] += 1
    return n


def apply_plan(plan, undo_path):
    """Rename every 'ok' entry; refuses if any entry is a conflict/invalid.
    Two phases (to unique temporary names, then to the final names) so that
    swaps and chains (a->b, b->c) work. Any failure rolls everything back.
    Returns the number renamed."""
    bad = [p for p in plan if p["status"] in ("conflict", "invalid")]
    if bad:
        raise RenameError(f"{len(bad)} file(s) have a problem; fix those first "
                          f"(or change the rules).")
    todo = [p for p in plan if p["status"] == "ok"]
    if not todo:
        return 0
    pairs = [(p["src"], p["dst"]) for p in todo]
    _move_all(pairs)
    record_undo(undo_path, pairs)
    return len(pairs)


def _move_all(pairs):
    """Two-phase move with rollback. pairs = [(from, to)]."""
    stage = []                       # (original, temp, final)
    done = []                        # (temp, final) already moved to final
    try:
        for src, dst in pairs:
            tmp = os.path.join(os.path.dirname(src), f".srboli-tmp-{uuid.uuid4().hex}")
            os.rename(src, tmp)
            stage.append((src, tmp, dst))
        for src, tmp, dst in stage:
            if os.path.lexists(dst):
                raise RenameError(f"'{os.path.basename(dst)}' appeared in the "
                                  f"meantime; nothing was renamed.")
            os.rename(tmp, dst)
            done.append((tmp, dst))
    except BaseException as e:
        for tmp, dst in reversed(done):
            try:
                os.rename(dst, tmp)
            except OSError:
                pass
        for src, tmp, _dst in reversed(stage):
            try:
                os.rename(tmp, src)
            except OSError:
                pass
        if isinstance(e, RenameError):
            raise
        if isinstance(e, OSError):
            raise RenameError(f"Renaming failed ({e.strerror or e}); "
                              f"everything was put back.")
        raise


# ── undo ────────────────────────────────────────────────────────────────────
def record_undo(undo_path, pairs):
    data = jsonio.read_json(undo_path, {"batches": []})
    batches = data.get("batches", []) if isinstance(data, dict) else []
    batches.append({"time": time.time(), "pairs": [list(p) for p in pairs]})
    jsonio.write_json_atomic(undo_path, {"batches": batches[-UNDO_KEEP:]})


def undo_info(undo_path):
    """(count, when) of the most recent batch, or None."""
    data = jsonio.read_json(undo_path, {"batches": []})
    batches = data.get("batches", []) if isinstance(data, dict) else []
    if not batches:
        return None
    last = batches[-1]
    return len(last["pairs"]), last["time"]


def undo_last(undo_path):
    """Put the names of the last batch back. Returns the number restored.
    Refuses (nothing touched) if a renamed file is gone or an old name is taken."""
    data = jsonio.read_json(undo_path, {"batches": []})
    batches = data.get("batches", []) if isinstance(data, dict) else []
    if not batches:
        raise RenameError("Nothing to undo.")
    pairs = batches[-1]["pairs"]
    new_names = {new for _old, new in pairs}
    for old, new in pairs:
        if not os.path.lexists(new):
            raise RenameError(f"'{os.path.basename(new)}' is gone or was "
                              f"renamed again, so this can't be undone safely.")
        if os.path.lexists(old) and old not in new_names:
            raise RenameError(f"'{os.path.basename(old)}' exists again; "
                              f"undo would overwrite it.")
    _move_all([(new, old) for old, new in pairs])
    batches.pop()
    jsonio.write_json_atomic(undo_path, {"batches": batches})
    return len(pairs)
