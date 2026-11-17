# core/twoway_core.py - two-way folder sync: keep folders A and B identical,
# carrying changes in BOTH directions. Pure Python (no UI), tested with real
# folders.
#
# To tell "new" from "deleted" it remembers what both folders looked like at
# the end of the last sync (the "base", kept in the app's data folder, one file
# per pair of folders). For every path:
#
#   same on both, unchanged since the base ..... nothing to do
#   changed on one side only .................. copied to the other side
#   new on one side (not in the base) ......... copied to the other side
#   gone from one side, unchanged on the other  deleted on the other side too
#   gone from one side, CHANGED on the other .. the changed file is kept and
#                                               copied back (a delete never
#                                               beats an edit)
#   changed on both sides, different content .. CONFLICT: the newer file wins,
#                                               the other version is kept next
#                                               to it as "name (conflict from
#                                               A 2026-11-17_153000).ext" on
#                                               both sides - nothing is lost
#   changed on both, same content ............. nothing to copy
#
# No base (first sync, or the record was lost): nothing is deleted - the two
# folders are combined, and differing files become conflicts.
#
# Nothing is ever really deleted: whatever a sync overwrites or removes is
# moved to "<that folder>/.srboli-replaced/<date_time>/<same path>".

import hashlib
import os
import shutil
import time

from core import file_safety
from core.jsonio import read_json, write_json_atomic
from core.sync_core import (REPLACED, MTIME_SLACK_NS, BIG_REMOVAL,
                            BIG_REMOVAL_MIN, scan, same_file, replaced_info,
                            purge_replaced, _inside, _real, _join)

EMPTY_SIDE_MIN = 5          # a side that lost this many tracked files and now has none


class Stopped(Exception):
    pass


def check_folders(a, b):
    if not a or not os.path.isdir(a):
        return "Pick folder A first."
    if not b:
        return "Pick folder B first."
    if os.path.exists(b) and not os.path.isdir(b):
        return "Folder B is a file, not a folder."
    if _real(a) == _real(b):
        return "A and B are the same folder."
    if _inside(b, a) or _inside(a, b):
        return "One folder can't be inside the other."
    return None


# ── the record of the last sync ──────────────────────────────────────────────
def state_path_for(a, b):
    import app_data
    key = hashlib.sha1("\n".join(sorted([_real(a), _real(b)])).encode()).hexdigest()[:16]
    return os.path.join(app_data.subdir("sync"), f"pair-{key}.json")


def load_state(path, a, b):
    """(base_a, base_b): {rel: [size, mtime_ns]} as last synced. Empty when
    there is no record. Handles the folders being given in the other order."""
    data = read_json(path, {}) if path and os.path.exists(path) else {}
    if not isinstance(data, dict) or not isinstance(data.get("base_a"), dict):
        return {}, {}
    ba, bb = data["base_a"], data.get("base_b", {})
    if data.get("a") == _real(b) and data.get("b") == _real(a):
        ba, bb = bb, ba
    elif data.get("a") != _real(a) or data.get("b") != _real(b):
        return {}, {}
    return dict(ba), dict(bb)


def save_state(path, a, b, base_a, base_b):
    write_json_atomic(path, {"a": _real(a), "b": _real(b), "base_a": base_a,
                             "base_b": base_b}, indent=None)


# ── planning ─────────────────────────────────────────────────────────────────
def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _equal(a, b, rel, xa, xb):
    """Do the two files hold the same bytes?"""
    if same_file(xa, xb):
        return True
    if xa[0] != xb[0]:
        return False
    try:
        return _sha(_join(a, rel)) == _sha(_join(b, rel))
    except OSError:
        return False


class Plan:
    def __init__(self):
        self.a2b = []
        self.b2a = []
        self.del_a = []           # delete on A (it was deleted on B)
        self.del_b = []
        self.conflicts = []
        self.adopt = []           # same content on both: just remember it
        self.same = 0
        self.to_a_bytes = 0
        self.to_b_bytes = 0
        self.first = False
        self.warning = ""
        self.note = ""

    @property
    def work(self):
        return (len(self.a2b) + len(self.b2a) + len(self.del_a)
                + len(self.del_b) + len(self.conflicts))


def make_plan(a, b, state_path=None):
    state_path = state_path or state_path_for(a, b)
    sa = scan(a)
    sb = scan(b) if os.path.isdir(b) else {}
    base_a, base_b = load_state(state_path, a, b)
    p = Plan()
    p.first = not base_a and not base_b
    for rel in sorted(set(sa) | set(sb)):
        xa, xb = sa.get(rel), sb.get(rel)
        ba, bb = base_a.get(rel), base_b.get(rel)
        known = ba is not None and bb is not None
        if xa and xb:
            if known:
                ca, cb = not same_file(xa, ba), not same_file(xb, bb)
                if not ca and not cb:
                    p.same += 1
                    continue
                if ca and not cb:
                    p.a2b.append(rel); p.to_b_bytes += xa[0]
                    continue
                if cb and not ca:
                    p.b2a.append(rel); p.to_a_bytes += xb[0]
                    continue
            if _equal(a, b, rel, xa, xb):
                p.adopt.append(rel)
            else:
                p.conflicts.append(rel)
                p.to_a_bytes += xb[0]; p.to_b_bytes += xa[0]
        elif xa:                                   # missing on B
            if known and same_file(xa, ba):
                p.del_a.append(rel)                # B deleted it, A never touched it
            else:
                p.a2b.append(rel); p.to_b_bytes += xa[0]
        else:                                      # missing on A
            if known and same_file(xb, bb):
                p.del_b.append(rel)
            else:
                p.b2a.append(rel); p.to_a_bytes += xb[0]
    if p.first:
        p.note = ("First sync of this pair: nothing will be deleted. The two "
                  "folders are combined, and files that differ become "
                  "conflicts (both versions kept).")
    dels_a, dels_b = len(p.del_a), len(p.del_b)
    if base_a and not sa and len(base_a) >= EMPTY_SIDE_MIN:
        p.warning = ("Folder A looks EMPTY but had files at the last sync. Is a "
                     "drive unplugged or the wrong folder picked? Syncing would "
                     "delete those files from B (they would go to the replaced "
                     "folder).")
    elif base_b and not sb and len(base_b) >= EMPTY_SIDE_MIN:
        p.warning = ("Folder B looks EMPTY but had files at the last sync. Is a "
                     "drive unplugged or the wrong folder picked? Syncing would "
                     "delete those files from A (they would go to the replaced "
                     "folder).")
    else:
        for n, side, total in ((dels_a, "A", len(sa)), (dels_b, "B", len(sb))):
            if n >= BIG_REMOVAL_MIN and n > BIG_REMOVAL * max(total, 1):
                p.warning = (f"{n} files would be deleted from {side} because "
                             f"they were deleted on the other side. Make sure "
                             f"that's what you want.")
                break
    return p


# ── running ──────────────────────────────────────────────────────────────────
class Result:
    def __init__(self):
        self.ok = False
        self.stopped = False
        self.to_a = 0
        self.to_b = 0
        self.deleted_a = 0
        self.deleted_b = 0
        self.conflicts = 0
        self.failed = []
        self.error = ""


def _sig(root, rel):
    try:
        st = os.stat(_join(root, rel))
        return [st.st_size, st.st_mtime_ns]
    except OSError:
        return None


def _conflict_rel(rel, label, stamp, roots):
    folder, name = os.path.split(rel)
    stem, ext = os.path.splitext(name)
    n = 0
    while True:
        tag = f"{stem} (conflict from {label} {stamp}{'' if not n else '-' + str(n)}){ext}"
        cand = f"{folder}/{tag}" if folder else tag
        if not any(os.path.lexists(_join(r, cand)) for r in roots):
            return cand
        n += 1


def run_sync(a, b, state_path=None, progress=None, stop=None, plan=None):
    res = Result()
    problem = check_folders(a, b)
    if problem:
        res.error = problem
        return res
    state_path = state_path or state_path_for(a, b)
    try:
        os.makedirs(b, exist_ok=True)
        plan = plan or make_plan(a, b, state_path)
        from core.backup_core import fmt_size
        for root, need in ((a, plan.to_a_bytes), (b, plan.to_b_bytes)):
            free = shutil.disk_usage(root).free
            if need > free:
                res.error = (f"Not enough room in {root}: {fmt_size(need)} "
                             f"needed, {fmt_size(free)} free.")
                return res
    except OSError as e:
        res.error = f"Couldn't prepare the folders: {e}"
        return res

    base_a, base_b = load_state(state_path, a, b)
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    rdirs = {}
    for root in (a, b):
        d, n = os.path.join(root, REPLACED, stamp), 1
        while os.path.exists(d):
            n += 1
            d = os.path.join(root, REPLACED, f"{stamp}-{n}")
        rdirs[root] = d

    def aside(root, rel):
        dst = _join(rdirs[root], rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(_join(root, rel), dst)
        return dst

    def record(rel):
        sa, sb = _sig(a, rel), _sig(b, rel)
        if sa and sb:
            base_a[rel], base_b[rel] = sa, sb
        else:
            base_a.pop(rel, None); base_b.pop(rel, None)

    def push(src_root, dst_root, rel):
        src, dst = _join(src_root, rel), _join(dst_root, rel)
        moved = aside(dst_root, rel) if os.path.lexists(dst) else None
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            file_safety.safe_copy(src, dst)
        except BaseException:
            if moved:
                try:
                    os.replace(moved, dst)
                except OSError:
                    pass
            raise

    def conflict(rel):
        sa, sb = _sig(a, rel), _sig(b, rel)
        a_wins = sa[1] >= sb[1]
        win, lose = (a, b) if a_wins else (b, a)
        label = "B" if a_wins else "A"            # the side that loses
        crel = _conflict_rel(rel, label, stamp, (a, b))
        pl, cl = _join(lose, rel), _join(lose, crel)
        os.makedirs(os.path.dirname(cl), exist_ok=True)
        os.replace(pl, cl)                        # the loser keeps its own bytes
        try:
            file_safety.safe_copy(_join(win, rel), pl)
        except BaseException:
            os.replace(cl, pl)
            raise
        try:
            file_safety.safe_copy(cl, _join(win, crel))
        except OSError as e:
            res.failed.append((crel, f"couldn't copy the conflict version: {e}"))
        record(rel)
        record(crel)

    jobs = ([("del_a", r) for r in plan.del_a] + [("del_b", r) for r in plan.del_b]
            + [("a2b", r) for r in plan.a2b] + [("b2a", r) for r in plan.b2a]
            + [("conflict", r) for r in plan.conflicts])
    total = len(jobs)
    gone = {a: [], b: []}
    try:
        for rel in plan.adopt:
            record(rel)
        try:
            for i, (what, rel) in enumerate(jobs):
                if stop and stop():
                    raise Stopped()
                if progress:
                    progress(i, total, rel)
                try:
                    if what == "del_a":
                        aside(a, rel); gone[a].append(rel); res.deleted_a += 1
                        base_a.pop(rel, None); base_b.pop(rel, None)
                    elif what == "del_b":
                        aside(b, rel); gone[b].append(rel); res.deleted_b += 1
                        base_a.pop(rel, None); base_b.pop(rel, None)
                    elif what == "a2b":
                        push(a, b, rel); res.to_b += 1; record(rel)
                    elif what == "b2a":
                        push(b, a, rel); res.to_a += 1; record(rel)
                    else:
                        conflict(rel); res.conflicts += 1
                except Stopped:
                    raise
                except OSError as e:
                    res.failed.append((rel, str(e) or e.__class__.__name__))
            if progress:
                progress(total, total, "")
            # forget paths that are gone from both folders
            for rel in list(base_a):
                if not _sig(a, rel) and not _sig(b, rel):
                    base_a.pop(rel, None); base_b.pop(rel, None)
            res.ok = True
        except Stopped:
            res.stopped = True
    finally:
        try:
            save_state(state_path, a, b, base_a, base_b)
        except OSError as e:
            res.error = f"Synced, but couldn't save the record: {e}"
            res.ok = False
    for root in (a, b):
        _prune(root, gone[root])
        try:
            os.rmdir(rdirs[root])
            os.rmdir(os.path.dirname(rdirs[root]))
        except OSError:
            pass
    return res


def _prune(root, rels):
    dirs = {os.path.dirname(_join(root, r)) for r in rels}
    for d in sorted(dirs, key=len, reverse=True):
        while _inside(d, root) and _real(d) != _real(root):
            try:
                os.rmdir(d)
            except OSError:
                break
            d = os.path.dirname(d)


def replaced_total(a, b):
    na, sa = replaced_info(a) if os.path.isdir(a) else (0, 0)
    nb, sb = replaced_info(b) if os.path.isdir(b) else (0, 0)
    return na + nb, sa + sb


def purge_both(a, b, older_than_days=30):
    return purge_replaced(a, older_than_days) + purge_replaced(b, older_than_days)
