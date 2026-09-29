# core/file_sorter_core.py — File Sorter engine (rules, matching, actions).
#
# Kivy-free by design: this is the module screens/file_sorter_screen.py
# (the UI) AND the headless --daemon folder watcher both import. Neither
# `import kivy` nor anything that transitively imports it belongs in this
# file — that is the one hard rule, since the daemon process never starts
# Kivy at all (see main.py's --daemon dispatch).
#
# This is a mechanical extraction of the module-level functions that used
# to live directly in file_sorter_screen.py (see that file's history / the
# project's continuation docs): rule evaluation, plan building, and
# applying an action to a file. The UI file now imports everything here
# instead of defining it, so there is exactly one copy of this logic.
#
# One behavioural change from the original: the old code read image
# metadata (Make/Model/Software/GPS) through screens.metadata_screen,
# which imports Kivy at module level — fine for the UI process, but it
# would have dragged Kivy into the daemon just to check a JPEG's EXIF
# Make tag. _extract_image_meta() below is a small self-contained PIL
# reader instead, kept to exactly the fields File Sorter rules use.

import os
import re
import json
import shutil
import datetime
import time

try:
    import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

try:
    from PIL import Image as _PILImage
    from PIL.ExifTags import TAGS as _EXIF_TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import app_data

RULESETS_DIR = "file_sorter_rulesets"
LAST_USED_KEY = "_last_used"

FIELDS = {
    "file_type":     {"label": "File type",              "kind": "category",
                      "ops": ["is", "is_not"]},
    "extension":     {"label": "File extension",        "kind": "text_list",
                      "ops": ["is_one_of", "is_not_one_of"]},
    "name":          {"label": "File name",              "kind": "text",
                      "ops": ["contains", "not_contains", "starts_with",
                             "ends_with", "equals", "regex"]},
    "size":          {"label": "File size",              "kind": "size",
                      "ops": ["greater_than", "less_than"]},
    "modified":      {"label": "Date modified",          "kind": "days",
                      "ops": ["older_than_days", "newer_than_days"]},
    "created":       {"label": "Date created",           "kind": "days",
                      "ops": ["older_than_days", "newer_than_days"]},
    "meta_make":     {"label": "Metadata: Camera Make",  "kind": "text",
                      "ops": ["contains", "equals", "is_missing"]},
    "meta_model":    {"label": "Metadata: Camera Model", "kind": "text",
                      "ops": ["contains", "equals", "is_missing"]},
    "meta_software": {"label": "Metadata: Software",     "kind": "text",
                      "ops": ["contains", "equals", "is_missing"]},
    "meta_has_gps":  {"label": "Metadata: Has GPS",      "kind": "bool",
                      "ops": ["is_true", "is_false"]},
}
FIELD_ORDER = list(FIELDS.keys())
FIELD_LABELS = {k: v["label"] for k, v in FIELDS.items()}
SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}

FILE_TYPE_CATEGORIES = {
    "Image":    {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif",
                "heic", "heif", "svg", "raw", "cr2", "nef", "arw"},
    "Video":    {"mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v",
                "mpg", "mpeg"},
    "Audio":    {"mp3", "wav", "flac", "aac", "ogg", "wma", "m4a", "opus"},
    "Document": {"pdf", "doc", "docx", "txt", "rtf", "odt", "md", "xls",
                "xlsx", "ppt", "pptx", "csv"},
    "Archive":  {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"},
}
FILE_TYPE_NAMES = list(FILE_TYPE_CATEGORIES.keys())

ACTION_TYPES = ["move", "copy", "rename", "delete"]
ACTION_LABELS = {"move": "Move to folder", "copy": "Copy to folder",
                 "rename": "Rename", "delete": "Delete"}

# A file is considered "still being written" (download/install in
# progress) until its size stops changing across this many consecutive
# polls, spaced this far apart. Apply waits this out rather than acting
# on a partial/corrupt file - e.g. an .iso rule firing while the .iso is
# still 8KB and downloading.
STABLE_POLL_INTERVAL = 1.0
STABLE_CHECKS_REQUIRED = 3
# Quick two-look check used only to flag likely-incomplete files in
# Preview (cheap - doesn't block scanning).
PREVIEW_QUICK_CHECK_GAP = 0.05

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
             ".tiff", ".tif"}
HAS_META = HAS_PIL


def _home():
    return os.path.expanduser("~")


def _rulesets_dir():
    return app_data.subdir(RULESETS_DIR)


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def save_ruleset(name, rules):
    path = os.path.join(_rulesets_dir(), f"{name}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rules": rules}, f, indent=2)
        return True
    except Exception as e:
        print(f"FileSorter: save ruleset failed: {e}")
        return False


def load_ruleset(name):
    path = os.path.join(_rulesets_dir(), f"{name}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("rules", [])
    except Exception:
        return []


def list_rulesets():
    d = _rulesets_dir()
    try:
        return sorted(f[:-5] for f in os.listdir(d)
                      if f.endswith(".json") and f != f"{LAST_USED_KEY}.json")
    except Exception:
        return []


def delete_ruleset(name):
    """Remove a saved ruleset file. Returns True if it was deleted."""
    path = os.path.join(_rulesets_dir(), f"{name}.json")
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def _validate_rule(rule):
    """Lenient shape check for a single imported rule dict - good enough
    to keep obviously-malformed entries out without being fussy about
    minor version differences."""
    if not isinstance(rule, dict):
        return False
    if not isinstance(rule.get("conditions"), list):
        return False
    action = rule.get("action")
    if not isinstance(action, dict) or action.get("type") not in ACTION_TYPES:
        return False
    return True


def export_ruleset_to_path(path, rules):
    """Save the current in-memory ruleset to an arbitrary file location
    the user picked (as opposed to save_ruleset(), which always writes
    into the app's own internal rulesets folder under a name). This is
    what makes a ruleset actually shareable/backupable outside the app."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rules": rules}, f, indent=2)
        return True, None
    except Exception as e:
        return False, str(e)


def import_ruleset_from_path(path):
    """Loads a ruleset from an arbitrary external file (the counterpart
    to export_ruleset_to_path). Returns (rules, error, skipped_count).
    `rules` is [] and `error` is set on total failure; a partially-bad
    file still returns whatever valid rules it found plus a
    skipped_count so the caller can tell the user."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [], f"Couldn't read that file: {e}", 0

    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        return [], "That file doesn't look like a Srboli ruleset export.", 0

    valid = [r for r in data["rules"] if _validate_rule(r)]
    skipped = len(data["rules"]) - len(valid)
    return valid, None, skipped


# ── metadata (Make / Model / Software / GPS presence only - the fields
# File Sorter rules can match on) ───────────────────────────────────────
_meta_cache = {}


def _extract_image_meta(path):
    """PIL-only EXIF reader, deliberately narrow: just the tags File
    Sorter rules can match on. Kept separate from the Metadata Inspector
    screen's own (much larger) reader so this module never needs to
    import anything Kivy-adjacent."""
    meta = {}
    if not HAS_PIL:
        return meta
    try:
        img = _PILImage.open(path)
        exif_raw = img._getexif() if hasattr(img, "_getexif") else None
        if exif_raw:
            for tag_id, val in exif_raw.items():
                tag = _EXIF_TAGS.get(tag_id, str(tag_id))
                if tag in ("Make", "Model", "Software"):
                    if isinstance(val, bytes):
                        try:
                            val = val.decode("utf-8", errors="replace")
                        except Exception:
                            val = repr(val)
                    meta[tag] = str(val).strip()
                elif tag == "GPSInfo":
                    meta["GPSInfo"] = val
    except Exception:
        pass
    return meta


def clear_meta_cache():
    _meta_cache.clear()


def _get_meta(path):
    if path in _meta_cache:
        return _meta_cache[path]
    meta = {}
    ext = os.path.splitext(path)[1].lower()
    if HAS_META and ext in IMAGE_EXTS:
        try:
            raw = _extract_image_meta(path)
            meta["make"]     = raw.get("Make", "")
            meta["model"]    = raw.get("Model", "")
            meta["software"] = raw.get("Software", "")
            meta["has_gps"]  = "GPSInfo" in raw and bool(raw.get("GPSInfo"))
        except Exception:
            pass
    _meta_cache[path] = meta
    return meta


def gather_file_info(path):
    st = os.stat(path)
    name, ext = os.path.splitext(os.path.basename(path))
    return {
        "path": path, "name": name, "ext": ext.lstrip(".").lower(),
        "size": st.st_size, "mtime": st.st_mtime,
        "ctime": getattr(st, "st_birthtime", st.st_ctime),
    }


def _text_match(op, value, target):
    value = value or ""
    target = (target or "").lower()
    value_l = value.lower()
    if op == "contains":
        return value_l in target
    if op == "not_contains":
        return value_l not in target
    if op == "starts_with":
        return target.startswith(value_l)
    if op == "ends_with":
        return target.endswith(value_l)
    if op == "equals":
        return target == value_l
    if op == "regex":
        try:
            return re.search(value, target, re.IGNORECASE) is not None
        except re.error:
            return False
    if op == "is_missing":
        return not target
    return False


def evaluate_condition(cond, info):
    field = cond["field"]
    op = cond["op"]
    value = cond.get("value", "")
    spec = FIELDS.get(field)
    if not spec:
        return False

    if field == "file_type":
        wanted_ext = FILE_TYPE_CATEGORIES.get(value, set())
        hit = info["ext"] in wanted_ext
        return hit if op == "is" else not hit

    if field == "extension":
        wanted = {v.strip().lower().lstrip(".") for v in value.split(",") if v.strip()}
        hit = info["ext"] in wanted
        return hit if op == "is_one_of" else not hit

    if field == "name":
        return _text_match(op, value, info["name"])

    if field == "size":
        try:
            num, unit = _parse_size_value(value)
            threshold = num * SIZE_UNITS.get(unit, 1)
        except Exception:
            return False
        return info["size"] > threshold if op == "greater_than" else info["size"] < threshold

    if field in ("modified", "created"):
        try:
            days = float(value)
        except Exception:
            return False
        ts = info["mtime"] if field == "modified" else info["ctime"]
        age_days = (datetime.datetime.now().timestamp() - ts) / 86400
        return age_days > days if op == "older_than_days" else age_days < days

    if field in ("meta_make", "meta_model", "meta_software"):
        key = {"meta_make": "make", "meta_model": "model",
               "meta_software": "software"}[field]
        meta = _get_meta(info["path"])
        return _text_match(op, value, meta.get(key, ""))

    if field == "meta_has_gps":
        meta = _get_meta(info["path"])
        has_gps = bool(meta.get("has_gps"))
        return has_gps if op == "is_true" else not has_gps

    return False


def _parse_size_value(value):
    # "500 MB" / "500MB" / "500"  (bare number defaults to bytes)
    m = re.match(r"^\s*([\d.]+)\s*([A-Za-z]*)\s*$", value or "")
    if not m:
        raise ValueError("bad size value")
    num = float(m.group(1))
    unit = (m.group(2) or "B").upper()
    if unit not in SIZE_UNITS:
        unit = "B"
    return num, unit


def evaluate_rule(rule, info):
    conds = rule.get("conditions", [])
    if not conds:
        return False
    logic = rule.get("logic", "AND")
    results = [evaluate_condition(c, info) for c in conds]
    return all(results) if logic == "AND" else any(results)


def build_plan(files, rules):
    """Returns list of (path, [rule, rule, ...]) for files with at least
    one matching rule, respecting each rule's continue_after_match flag.
    Disabled rules (rule["enabled"] == False) are skipped entirely, as
    if they weren't in the list - this is what the compact overview's
    per-rule Enable/Disable toggle actually does under the hood."""
    plan = []
    for path in files:
        try:
            info = gather_file_info(path)
        except Exception:
            continue
        matched = []
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            if evaluate_rule(rule, info):
                matched.append(rule)
                if not rule.get("continue_after_match", False):
                    break
        if matched:
            plan.append((path, matched))
    return plan


def _unique_path(folder, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    n = 1
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return candidate


def _apply_rename_pattern(pattern, current_path, counter):
    base, ext = os.path.splitext(os.path.basename(current_path))
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(current_path))
    out = pattern.replace("{name}", base)
    out = out.replace("{ext}", ext)   # ext already includes the leading dot
    out = out.replace("{counter}", str(counter))
    out = out.replace("{date}", mtime.strftime("%Y-%m-%d"))
    if not os.path.splitext(out)[1]:
        out += ext
    return out


def _is_locked_for_write(path):
    """Best-effort check for another process holding the file open.
    Reliable on Windows (exclusive-open fails while e.g. a browser or
    installer still has the file open). On POSIX, locks aren't mandatory
    so this mostly can't detect it - size-stability below is the real
    signal there, this is just a bonus check when it happens to work."""
    try:
        f = open(path, "r+b")
        f.close()
        return False
    except OSError:
        return True
    except Exception:
        return False


def wait_for_stable_file(path, log=None, stop_check=None,
                          progress=None,
                          poll_interval=STABLE_POLL_INTERVAL,
                          checks_required=STABLE_CHECKS_REQUIRED):
    """Blocks (on a background thread - never call from the UI thread)
    until `path`'s size stops changing across `checks_required`
    consecutive polls, so a rule doesn't act on a file that's still
    downloading/installing/being written.

    Returns True once the file looks finished, or False if the file
    disappeared/got renamed out from under us, or the user requested a
    stop while waiting (stop_check callable returning True).

    `progress(elapsed_seconds, size)` is called on every poll so the
    caller can push a live "still waiting..." status to the UI - this
    can run for a long time (a large download) and the UI must not look
    frozen while it does.
    """
    last_size = None
    stable_count = 0
    waited = 0.0
    while True:
        if stop_check and stop_check():
            return False
        try:
            size = os.path.getsize(path)
        except OSError:
            return False  # vanished / renamed mid-wait

        if size == last_size:
            stable_count += 1
        else:
            if last_size is not None and log:
                log(f"  still being written ({_fmt_size(size)} so far) - waiting...")
            stable_count = 0
        last_size = size

        if progress:
            progress(waited, size)

        if stable_count >= checks_required and not _is_locked_for_write(path):
            return True

        time.sleep(poll_interval)
        waited += poll_interval


def apply_action(current_path, action, counter, log, confirm_delete=None):
    """Returns (new_path_or_None, still_exists).

    `confirm_delete(path)` -> bool, only called for delete actions where
    action.get("auto_delete") is falsy. If it returns False, the delete
    is skipped (file untouched, still exists) rather than performed -
    the OS-trash-style "are you sure?" the auto-delete checkbox controls
    the opt-out of."""
    a_type = action["type"]
    try:
        if a_type == "move":
            dest_folder = action["dest"]
            os.makedirs(dest_folder, exist_ok=True)
            dest = _unique_path(dest_folder, os.path.basename(current_path))
            shutil.move(current_path, dest)
            log(f"  moved -> {dest}")
            return dest, True

        if a_type == "copy":
            dest_folder = action["dest"]
            os.makedirs(dest_folder, exist_ok=True)
            dest = _unique_path(dest_folder, os.path.basename(current_path))
            shutil.copy2(current_path, dest)
            log(f"  copied -> {dest}")
            return current_path, True   # chain continues on the original

        if a_type == "rename":
            folder = os.path.dirname(current_path)
            new_name = _apply_rename_pattern(action.get("pattern", "{name}{ext}"),
                                             current_path, counter)
            dest = _unique_path(folder, new_name)
            os.rename(current_path, dest)
            log(f"  renamed -> {os.path.basename(dest)}")
            return dest, True

        if a_type == "delete":
            if not action.get("auto_delete", False):
                allowed = confirm_delete(current_path) if confirm_delete else True
                if not allowed:
                    log("  skipped delete (declined at confirmation prompt)")
                    return current_path, True
            if HAS_SEND2TRASH:
                send2trash.send2trash(current_path)
                log("  deleted (sent to recycle bin/trash)")
            else:
                os.remove(current_path)
                log("  deleted (PERMANENTLY - send2trash not installed)")
            return None, False

    except Exception as e:
        log(f"  ERROR: {e}")
        return current_path, True

    return current_path, True


_OP_WORDS = {
    "is_one_of": "is", "is_not_one_of": "is not",
    "contains": "contains", "not_contains": "doesn't contain",
    "starts_with": "starts with", "ends_with": "ends with",
    "equals": "is exactly", "regex": "matches pattern",
    "greater_than": ">", "less_than": "<",
    "older_than_days": "older than", "newer_than_days": "newer than",
    "is_true": "is true", "is_false": "is false", "is_missing": "is missing",
    "is": "is", "is_not": "is not",
}


def _condition_one_liner(cond):
    field = cond.get("field", "")
    label = FIELD_LABELS.get(field, field)
    op = cond.get("op", "")
    value = cond.get("value", "")
    op_word = _OP_WORDS.get(op, op)
    if op in ("is_true", "is_false", "is_missing"):
        return f"{label} {op_word}"
    if op in ("older_than_days", "newer_than_days"):
        return f"{label} {op_word} {value} days"
    return f"{label} {op_word} {value}".rstrip()


def _action_one_liner(action):
    kind = action.get("type")
    if kind in ("move", "copy"):
        verb = "Move" if kind == "move" else "Copy"
        return f"{verb} TO {action.get('dest', '?')}"
    if kind == "rename":
        return f"Rename TO {action.get('pattern', '?')}"
    if kind == "delete":
        return "Delete" + ("" if action.get("auto_delete") else " (asks first)")
    return kind or "?"


def rule_one_liner(rule):
    """Compact "IF ... THEN ..." summary for the rules overview list."""
    conds = rule.get("conditions", [])
    joiner = " AND " if rule.get("logic", "AND") == "AND" else " OR "
    cond_text = joiner.join(_condition_one_liner(c) for c in conds) or "(no conditions)"
    action_text = _action_one_liner(rule.get("action", {}))
    cont = ", then keep checking more rules" if rule.get("continue_after_match") else ""
    return f"IF {cond_text} THEN {action_text}{cont}"
