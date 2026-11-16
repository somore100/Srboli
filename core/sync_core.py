# core/sync_core.py - one-way folder mirror: make folder B match folder A.
# Pure Python (no UI), tested with real folders.
#
#   new in A          -> copied to B
#   changed in A      -> copied to B; B's old version goes to the replaced folder
#   only in B         -> moved to the replaced folder (B no longer has it)
#   same in both      -> left alone
#
# Nothing is ever deleted. Whatever a sync would overwrite or remove is moved to
#   <B>/.srboli-replaced/<date_time>/<same relative path>
# so a mistake can be undone by moving the file back. Folder A is never
# changed. A stopped or crashed sync is safe: every file is handled on its
# own (copy to a temp name, then rename), so running again carries on.

import os
import shutil
import time

from core import file_safety

REPLACED = ".srboli-replaced"
SKIP_SUFFIX = ".srboli-part"
MTIME_SLACK_NS = 2_000_000_000          # FAT drives keep time to 2 seconds
BIG_REMOVAL = 0.5                       # warn when a sync would remove this share...
BIG_REMOVAL_MIN = 10                    # ...of B's files (and at least this many)


class Stopped(Exception):
    pass


def _real(p):
    return os.path.realpath(os.path.abspath(p))


def _inside(child, parent):
    child, parent = _real(child), _real(parent)
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def check_folders(a, b):
    """Why this pair can't be synced, or None."""
    if not a or not os.path.isdir(a):
        return "Pick the folder to copy FROM first."
    if not b:
        return "Pick the folder to copy TO."
    if os.path.exists(b) and not os.path.isdir(b):
        return "The target is a file, not a folder."
    if _real(a) == _real(b):
        return "The two folders are the same folder."
    if _inside(b, a):
        return "The target can't be inside the source folder."
    if _inside(a, b):
        return "The source can't be inside the target folder."
    return None


def scan(folder, skip_replaced=True):
    """{relative/path: (size, mtime_ns)} of the regular files under folder."""
    out = {}
    stack = [folder]
    while stack:
        cur = stack.pop()
        try:
            entries = list(os.scandir(cur))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    if skip_replaced and e.name == REPLACED and cur == folder:
                        continue
                    stack.append(e.path)
                elif e.is_file(follow_symlinks=False):
                    if SKIP_SUFFIX in e.name:
                        continue
                    st = e.stat(follow_symlinks=False)
                    out[os.path.relpath(e.path, folder).replace(os.sep, "/")] = (
                        st.st_size, st.st_mtime_ns)
            except OSError:
                continue
    return out


def same_file(x, y):
    return x[0] == y[0] and abs(x[1] - y[1]) <= MTIME_SLACK_NS


class Plan:
    def __init__(self):
        self.new = []             # in A only
        self.changed = []         # in both, different
        self.removed = []         # in B only
        self.same = 0
        self.copy_bytes = 0
        self.warning = ""

    @property
    def work(self):
        return len(self.new) + len(self.changed) + len(self.removed)


def make_plan(a, b):
    sa = scan(a)
    sb = scan(b) if os.path.isdir(b) else {}
    p = Plan()
    for rel in sorted(sa):
        if rel not in sb:
            p.new.append(rel)
            p.copy_bytes += sa[rel][0]
        elif same_file(sa[rel], sb[rel]):
            p.same += 1
        else:
            p.changed.append(rel)
            p.copy_bytes += sa[rel][0]
    p.removed = sorted(rel for rel in sb if rel not in sa)
    if not sa and sb:
        p.warning = ("The source folder looks EMPTY, so every file in the "
                     "target would be moved to the replaced folder. Check "
                     "that the right folder is picked (and that a drive "
                     "isn't unplugged).")
    elif (len(p.removed) >= BIG_REMOVAL_MIN
          and len(p.removed) > BIG_REMOVAL * len(sb)):
        p.warning = (f"{len(p.removed)} of the {len(sb)} files in the target "
                     f"are not in the source and would be moved away. Make "
                     f"sure the right folders are picked.")
    return p


class Result:
    def __init__(self):
        self.ok = False
        self.stopped = False
        self.copied = 0
        self.replaced = 0         # old versions moved aside
        self.removed = 0
        self.failed = []          # [(rel, reason)]
        self.error = ""
        self.replaced_dir = ""


def _join(base, rel):
    return os.path.join(base, *rel.split("/"))


def run_sync(a, b, progress=None, stop=None, plan=None):
    """Mirror a into b. Returns a Result."""
    res = Result()
    problem = check_folders(a, b)
    if problem:
        res.error = problem
        return res
    try:
        os.makedirs(b, exist_ok=True)
        plan = plan or make_plan(a, b)
        free = shutil.disk_usage(b).free
        if plan.copy_bytes > free:
            from core.backup_core import fmt_size
            res.error = (f"Not enough room in the target: {fmt_size(plan.copy_bytes)} "
                         f"needed, {fmt_size(free)} free.")
            return res
    except OSError as e:
        res.error = f"Couldn't prepare the target: {e}"
        return res

    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    rdir = os.path.join(b, REPLACED, stamp)
    n = 1
    while os.path.exists(rdir):
        n += 1
        rdir = os.path.join(b, REPLACED, f"{stamp}-{n}")
    res.replaced_dir = rdir

    def aside(rel):
        """Move B's version of rel into the replaced folder; returns where."""
        dst = _join(rdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(_join(b, rel), dst)
        return dst

    jobs = ([("remove", r) for r in plan.removed]
            + [("change", r) for r in plan.changed]
            + [("new", r) for r in plan.new])
    total = len(jobs)
    gone = []
    try:
        for i, (what, rel) in enumerate(jobs):
            if stop and stop():
                raise Stopped()
            if progress:
                progress(i, total, rel)
            src, dst = _join(a, rel), _join(b, rel)
            try:
                if what == "remove":
                    aside(rel)
                    gone.append(rel)
                    res.removed += 1
                    continue
                moved = None
                if what == "change" and os.path.lexists(dst):
                    moved = aside(rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    file_safety.safe_copy(src, dst)
                except BaseException:
                    if moved:                       # put the old version back
                        try:
                            os.replace(moved, dst)
                        except OSError:
                            pass
                    raise
                if moved:
                    res.replaced += 1
                res.copied += 1
            except Stopped:
                raise
            except OSError as e:
                res.failed.append((rel, str(e) or e.__class__.__name__))
        if progress:
            progress(total, total, "")
        res.ok = True
    except Stopped:
        res.stopped = True
    _prune(b, gone)
    try:
        os.rmdir(rdir)                      # nothing was moved aside
        os.rmdir(os.path.dirname(rdir))
    except OSError:
        pass
    return res


def _prune(b, rels):
    """Remove the folders that moving files away left empty (only those, and
    never B itself or the replaced folder)."""
    dirs = {os.path.dirname(_join(b, r)) for r in rels}
    for d in sorted(dirs, key=len, reverse=True):
        while _inside(d, b) and _real(d) != _real(b):
            try:
                os.rmdir(d)                 # only works when empty
            except OSError:
                break
            d = os.path.dirname(d)


# ── the replaced folder ──────────────────────────────────────────────────────
def replaced_info(b):
    """(number of files, bytes) kept in B's replaced folder."""
    folder = os.path.join(b, REPLACED)
    n = size = 0
    for root, _d, files in os.walk(folder):
        for f in files:
            try:
                size += os.path.getsize(os.path.join(root, f))
                n += 1
            except OSError:
                pass
    return n, size


def purge_replaced(b, older_than_days=30, now=None):
    """Delete replaced-folder batches older than the given number of days.
    This is the only place anything is really deleted, and only from the
    replaced folder. Returns how many batches were removed."""
    folder = os.path.join(b, REPLACED)
    now = now or time.time()
    removed = 0
    if not os.path.isdir(folder):
        return 0
    for name in os.listdir(folder):
        d = os.path.join(folder, name)
        try:
            age_days = (now - os.path.getmtime(d)) / 86400.0
        except OSError:
            continue
        if os.path.isdir(d) and age_days >= older_than_days:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
