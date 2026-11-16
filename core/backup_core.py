# core/backup_core.py - full, incremental and differential backups, restore.
# Pure Python (no UI), so it can be tested with real folders and, later, run
# by the background service.
#
# Layout inside the folder you choose as the destination:
#
#   <destination>/Srboli backups - <source name>/
#       set.json                      which source folder this set belongs to
#       2026-11-16_153000_full/       the files this backup had to copy
#           manifest.json             EVERY file of the source at that moment
#       2026-11-17_090000_incr/
#       2026-11-18_090000_diff/
#
# A manifest lists the whole source as it was, and for each file which backup
# folder holds its content. That makes all three kinds work the same way:
#   full         copies everything.
#   incremental  copies what changed since the LAST backup of any kind.
#   differential copies what changed since the last FULL backup.
# Unchanged files are not copied again; the manifest just points at the older
# folder that already has them. Restoring a backup = copy each file from the
# folder the manifest names, so there is no chain to replay.
#
# A backup only "exists" once its manifest is written (last, atomically). A
# backup that was stopped or crashed has no manifest and is removed/ignored.
# Nothing is ever deleted from the source, and a restore never overwrites.

import hashlib
import os
import shutil
import time

from core import file_safety
from core.jsonio import read_json, write_json_atomic

KINDS = ("full", "incr", "diff")
KIND_LABELS = {"full": "Full", "incr": "Incremental", "diff": "Differential"}
KIND_HELP = {
    "full": "Copies everything. The biggest and slowest, but on its own: "
            "restoring needs nothing else.",
    "incr": "Copies only what changed since the last backup of any kind. "
            "Small and fast. Keep all the backups before it.",
    "diff": "Copies everything changed since the last FULL backup. Bigger "
            "than incremental, but a restore needs only the full backup and "
            "this one.",
}
SET_PREFIX = "Srboli backups - "
MANIFEST = "manifest.json"
SKIP_SUFFIX = ".srboli-part"


class Stopped(Exception):
    pass


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_size(n):
    return _fmt_size(n)


# ── folders ──────────────────────────────────────────────────────────────────
def _real(p):
    return os.path.realpath(os.path.abspath(p))


def _inside(child, parent):
    child, parent = _real(child), _real(parent)
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def check_folders(source, dest):
    """A message saying why this pair can't be used, or None."""
    if not source or not os.path.isdir(source):
        return "Pick the folder to back up first."
    if not dest:
        return "Pick where the backups should go."
    if os.path.exists(dest) and not os.path.isdir(dest):
        return "The backup location is a file, not a folder."
    if _inside(dest, source):
        return ("The backup folder can't be inside the folder being backed up. "
                "Pick a different place.")
    return None


def set_dir_for(dest, source, create=False):
    """The folder holding the backups of `source` inside `dest`. Two sources
    with the same name get separate sets (-2, -3 ...)."""
    name = os.path.basename(_real(source).rstrip(os.sep)) or "root"
    src = _real(source)
    n = 1
    while True:
        d = os.path.join(dest, SET_PREFIX + name + ("" if n == 1 else f"-{n}"))
        info = read_json(os.path.join(d, "set.json"), {}) if os.path.isdir(d) else None
        if info is None:                       # nothing there yet
            if create:
                os.makedirs(d, exist_ok=True)
                write_json_atomic(os.path.join(d, "set.json"), {"source": src})
            return d
        if isinstance(info, dict) and info.get("source") == src:
            return d
        n += 1


# ── scanning ─────────────────────────────────────────────────────────────────
def scan(source, skip_inside=None):
    """{relative/path: (size, mtime_ns)} for every regular file under source.
    Symlinks are not followed; unreadable entries are skipped; anything under
    `skip_inside` (e.g. the backup folder itself) is left out."""
    out = {}
    skip = _real(skip_inside) if skip_inside else None
    stack = [source]
    while stack:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if skip and _real(e.path) == skip:
                        continue
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    if e.name.endswith(SKIP_SUFFIX) or SKIP_SUFFIX in e.name:
                        continue
                    st = e.stat(follow_symlinks=False)
                    rel = os.path.relpath(e.path, source).replace(os.sep, "/")
                    out[rel] = (st.st_size, st.st_mtime_ns)
            except OSError:
                continue
    return out


# ── reading what exists ──────────────────────────────────────────────────────
def list_backups(set_dir):
    """Backups that finished, oldest first: dicts with name, kind, created,
    created_ts, files, copied, bytes, base, failed."""
    out = []
    if not os.path.isdir(set_dir):
        return out
    for name in sorted(os.listdir(set_dir)):
        mpath = os.path.join(set_dir, name, MANIFEST)
        if not os.path.isfile(mpath):
            continue
        m = read_json(mpath, None)
        if not isinstance(m, dict) or not isinstance(m.get("files"), dict):
            continue
        out.append({"name": name, "kind": m.get("kind", "full"),
                    "created": m.get("created", ""),
                    "created_ts": m.get("created_ts", 0),
                    "files": len(m["files"]), "copied": m.get("copied", 0),
                    "bytes": m.get("bytes", 0), "base": m.get("base"),
                    "failed": m.get("failed", []),
                    "verified": bool(m.get("verified"))})
    out.sort(key=lambda b: (b["created_ts"], b["name"]))
    return out


def _manifest(set_dir, name):
    m = read_json(os.path.join(set_dir, name, MANIFEST), None)
    return m if isinstance(m, dict) and isinstance(m.get("files"), dict) else None


def reference_for(set_dir, kind):
    """(manifest, name, kind_used): what a backup of `kind` compares against.
    With nothing to compare to, incremental/differential become a full."""
    backups = list_backups(set_dir)
    if kind == "full" or not backups:
        return None, None, "full"
    if kind == "incr":
        pick = backups[-1]
    else:
        fulls = [b for b in backups if b["kind"] == "full"]
        if not fulls:
            return None, None, "full"
        pick = fulls[-1]
    m = _manifest(set_dir, pick["name"])
    if m is None:
        return None, None, "full"
    return m, pick["name"], kind


# ── planning ─────────────────────────────────────────────────────────────────
class Plan:
    def __init__(self):
        self.kind = "full"            # what will really happen
        self.asked = "full"
        self.base = None              # backup it compares against
        self.to_copy = []             # relative paths
        self.unchanged = 0
        self.removed = 0              # in the reference, gone from the source
        self.bytes = 0
        self.total_files = 0
        self.current = {}
        self.note = ""


def make_plan(source, dest, kind):
    set_dir = set_dir_for(dest, source)
    current = scan(source, skip_inside=dest if _inside(dest, source) else None)
    ref, base, used = reference_for(set_dir, kind)
    p = Plan()
    p.asked, p.kind, p.base, p.current = kind, used, base, current
    p.total_files = len(current)
    if used != kind:
        p.note = (f"There is no earlier {'full ' if kind == 'diff' else ''}"
                  f"backup to compare with, so this will be a full backup.")
    ref_files = ref["files"] if ref else {}
    for rel in sorted(current):
        size, mt = current[rel]
        old = ref_files.get(rel)
        if used == "full" or not old or old[0] != size or old[1] != mt:
            p.to_copy.append(rel)
            p.bytes += size
        else:
            p.unchanged += 1
    p.removed = sum(1 for rel in ref_files if rel not in current)
    return p


# ── running ──────────────────────────────────────────────────────────────────
class Result:
    def __init__(self):
        self.ok = False
        self.stopped = False
        self.name = ""
        self.kind = "full"
        self.copied = 0
        self.bytes = 0
        self.failed = []              # [(rel, reason)]
        self.verify_failed = []
        self.error = ""
        self.note = ""


def sha256_of(path, chunk=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _unique_dir(set_dir, kind):
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    name, n = f"{stamp}_{kind}", 1
    while os.path.exists(os.path.join(set_dir, name)):
        n += 1
        name = f"{stamp}-{n}_{kind}"
    return name


def run_backup(source, dest, kind, verify=False, progress=None, stop=None,
               plan=None):
    """Make a backup. progress(done, total, rel) / stop() are optional.
    Returns a Result; check .ok, .stopped, .failed."""
    res = Result()
    problem = check_folders(source, dest)
    if problem:
        res.error = problem
        return res
    try:
        os.makedirs(dest, exist_ok=True)
        set_dir = set_dir_for(dest, source, create=True)
        plan = plan or make_plan(source, dest, kind)
        res.kind, res.note = plan.kind, plan.note
        free = shutil.disk_usage(dest).free
        if plan.bytes > free:
            res.error = (f"Not enough room at the destination: this backup "
                         f"needs {_fmt_size(plan.bytes)} and {_fmt_size(free)} "
                         f"is free.")
            return res
        ref, base, _ = reference_for(set_dir, plan.kind)
        ref_files = ref["files"] if ref else {}
        name = _unique_dir(set_dir, plan.kind)
        out_dir = os.path.join(set_dir, name)
        os.makedirs(out_dir)
        res.name = name
    except OSError as e:
        res.error = f"Couldn't prepare the backup folder: {e}"
        return res

    files = {}
    copy_set = set(plan.to_copy)
    for rel, (size, mt) in plan.current.items():
        if rel not in copy_set:
            holder = ref_files[rel][2]
            files[rel] = [size, mt, holder]
    total = len(plan.to_copy)
    try:
        for i, rel in enumerate(plan.to_copy, 1):
            if stop and stop():
                raise Stopped()
            if progress:
                progress(i - 1, total, rel)
            src = os.path.join(source, *rel.split("/"))
            dst = os.path.join(out_dir, *rel.split("/"))
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                before = os.stat(src)
                file_safety.safe_copy(src, dst)
                size, mt = before.st_size, before.st_mtime_ns
                if verify and sha256_of(src) != sha256_of(dst):
                    res.verify_failed.append(rel)
                    os.remove(dst)
                    res.failed.append((rel, "the copy did not match the original"))
                    continue
                files[rel] = [size, mt, name]
                res.copied += 1
                res.bytes += size
            except Stopped:
                raise
            except OSError as e:
                res.failed.append((rel, str(e) or e.__class__.__name__))
        if progress:
            progress(total, total, "")
        write_json_atomic(os.path.join(out_dir, MANIFEST), {
            "version": 1, "source": _real(source), "kind": plan.kind,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "created_ts": time.time(), "base": plan.base,
            "files": files, "copied": res.copied, "bytes": res.bytes,
            "failed": [r for r, _ in res.failed], "verified": bool(verify)},
            indent=None)
        res.ok = True
    except Stopped:
        res.stopped = True
        shutil.rmtree(out_dir, ignore_errors=True)
    except OSError as e:
        res.error = f"Backup failed: {e}"
        shutil.rmtree(out_dir, ignore_errors=True)
    return res


def cleanup_unfinished(set_dir):
    """Remove folders left by a crashed backup (no manifest). Returns count."""
    n = 0
    if not os.path.isdir(set_dir):
        return 0
    for name in os.listdir(set_dir):
        d = os.path.join(set_dir, name)
        if os.path.isdir(d) and not os.path.exists(os.path.join(d, MANIFEST)):
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n


# ── restore / delete ─────────────────────────────────────────────────────────
class RestoreResult:
    def __init__(self):
        self.ok = False
        self.stopped = False
        self.restored = 0
        self.skipped = []             # already there, left alone
        self.failed = []              # [(rel, reason)]
        self.error = ""


def run_restore(set_dir, name, target, progress=None, stop=None):
    """Copy every file of backup `name` into `target`. A file that already
    exists there is left alone (and listed in .skipped), never overwritten."""
    res = RestoreResult()
    m = _manifest(set_dir, name)
    if m is None:
        res.error = "That backup is missing or damaged."
        return res
    if not target:
        res.error = "Pick where to restore to."
        return res
    if _inside(target, set_dir) or _inside(set_dir, target):
        res.error = "Restore to a different folder than the backups."
        return res
    try:
        os.makedirs(target, exist_ok=True)
    except OSError as e:
        res.error = f"Couldn't create that folder: {e}"
        return res
    items = sorted(m["files"].items())
    need = sum(v[0] for _, v in items)
    try:
        free = shutil.disk_usage(target).free
        if need > free:
            res.error = (f"Not enough room: {_fmt_size(need)} needed, "
                         f"{_fmt_size(free)} free.")
            return res
    except OSError:
        pass
    total = len(items)
    for i, (rel, (size, mt, holder)) in enumerate(items, 1):
        if stop and stop():
            res.stopped = True
            return res
        if progress:
            progress(i - 1, total, rel)
        src = os.path.join(set_dir, holder, *rel.split("/"))
        dst = os.path.join(target, *rel.split("/"))
        if os.path.lexists(dst):
            res.skipped.append(rel)
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            file_safety.safe_copy(src, dst)
            os.utime(dst, ns=(mt, mt))
            res.restored += 1
        except OSError as e:
            res.failed.append((rel, str(e) or e.__class__.__name__))
    if progress:
        progress(total, total, "")
    res.ok = True
    return res


def dependents(set_dir, name):
    """Names of other backups that still use files stored in backup `name`."""
    out = []
    for b in list_backups(set_dir):
        if b["name"] == name:
            continue
        m = _manifest(set_dir, b["name"])
        if m and any(v[2] == name for v in m["files"].values()):
            out.append(b["name"])
    return out


def delete_backup(set_dir, name):
    """(ok, message). Refused while later backups depend on this one."""
    if os.sep in name or name in ("", ".", ".."):
        return False, "Bad backup name."
    d = os.path.join(set_dir, name)
    if not os.path.isfile(os.path.join(d, MANIFEST)):
        return False, "That backup doesn't exist."
    deps = dependents(set_dir, name)
    if deps:
        return False, (f"{len(deps)} later backup(s) still use files stored "
                       f"in this one, so deleting it would break them. Delete "
                       f"those first.")
    try:
        shutil.rmtree(d)
    except OSError as e:
        return False, f"Couldn't delete it: {e}"
    return True, "Deleted."
