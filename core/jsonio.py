# core/jsonio.py - JSON files that survive a crash and never fail silently.
#
# write_json_atomic: the file is either the old version or the new one, never
#   half-written (temp file in the same folder, fsync, os.replace).
# read_json: a missing file gives the default; a file that can't be parsed is
#   renamed to "<name>.corrupt-<timestamp>" (so the next save can't overwrite
#   it) and logged, then the default is returned.
import json
import os
import sys
import time


def write_json_atomic(path, data, **dump_kw):
    dump_kw.setdefault("indent", 2)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, f".{os.path.basename(path)}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def quarantine(path):
    """Move an unreadable file aside. Returns the new path, or None."""
    dst = f"{path}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    n = 0
    while os.path.exists(dst):
        n += 1
        dst = f"{path}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}-{n}"
    try:
        os.replace(path, dst)
        return dst
    except OSError:
        return None


def read_json(path, default=None, quarantine_bad=True):
    """Parsed content of path, or default. Pass quarantine_bad=False for a
    file the user chose (it must never be renamed behind their back)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except ValueError as e:         # JSONDecodeError and UnicodeDecodeError
        moved = quarantine(path) if quarantine_bad else None
        note = f" (moved to {moved})" if moved else ""
        print(f"JSON file unreadable: {path}: {e}{note}", file=sys.stderr)
        return default
    except OSError as e:
        print(f"JSON file not readable: {path}: {e}", file=sys.stderr)
        return default
