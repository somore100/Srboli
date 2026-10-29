# core/file_safety.py - "is it safe to touch this file yet?", and moves/copies
# that can't leave a half-written file behind. Kivy-free; shared by the File
# Sorter (screen + background watcher) and Fast Transfer.
#
# Why size-stability alone isn't enough (the old check): a file that is still
# 0 bytes, a writer that preallocates the final size, one that pauses for a few
# seconds, or a document simply open in an editor all look "finished". So a
# file is READY only when none of these says otherwise:
#   * it is a real file, not empty (an empty file must also be old),
#   * it was last modified / changed at least `settle` seconds ago,
#   * its name doesn't look like an unfinished download (.part, .crdownload...)
#     and it is young,
#   * no editor lock file sits beside it (.~lock.x#, ~$x, .x.swp, .#x),
#   * no other process has it open for writing (Linux: read from /proc;
#     Windows: an exclusive-open test).
# A file untouched for QUIET_SECONDS is accepted immediately; a younger one must
# also stay unchanged over one more poll. So thousands of old files cost one
# stat() each instead of a sleep each.
#
# safe_copy()/safe_move() write to a hidden temporary name in the destination
# folder and rename it into place only after checking the source didn't change
# and the sizes match. A move onto the same disk is a plain atomic rename; across
# disks the original is deleted only after the verified copy is in place.

import os
import stat
import sys
import threading
import time
from collections import namedtuple

SETTLE_SECONDS = 5.0          # untouched this long = probably finished
QUIET_SECONDS = 30.0          # untouched this long = trust it, no second look
EMPTY_FILE_MIN_AGE = 300.0    # a 0-byte file only counts as ready when this old
TEMP_SUFFIXES = (".part", ".partial", ".crdownload", ".download", ".tmp",
                 ".temp", ".!qb", ".aria2", ".opdownload", ".crswap",
                 ".swp", ".swx")

# ready: bool, reason: why not (or "ok"), sig: (size, mtime_ns) or None if gone,
# age: seconds since the last change
Readiness = namedtuple("Readiness", "ready reason sig age")


# ── what else is using the file ──────────────────────────────────────────────
def lock_files_for(path):
    """Editor lock files that exist beside `path`."""
    folder, name = os.path.split(path)
    candidates = [f".~lock.{name}#",          # LibreOffice
                  f"~${name}", f"~${name[2:]}",   # Word / Excel / PowerPoint
                  f".{name}.swp", f".{name}.swx",  # vim
                  f".#{name}"]                # emacs
    return [c for c in candidates if os.path.lexists(os.path.join(folder, c))]


_open_cache = {"at": -1e9, "paths": frozenset()}
_scan_lock = threading.Lock()


def open_for_write_paths(max_age=2.0):
    """Paths some OTHER process has open for writing (Linux only; empty
    elsewhere). One scan of /proc is reused for `max_age` seconds so checking
    thousands of files doesn't scan thousands of times."""
    if not sys.platform.startswith("linux"):
        return frozenset()
    if time.monotonic() - _open_cache["at"] < max_age:
        return _open_cache["paths"]
    # Many worker threads reach this at the same moment (Fast Transfer): only
    # one of them scans, the rest wait and then reuse its result.
    with _scan_lock:
        if time.monotonic() - _open_cache["at"] < max_age:
            return _open_cache["paths"]
        return _scan_open_files()


def _scan_open_files():
    found, me = set(), str(os.getpid())
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit() and p != me]
    except OSError:
        return frozenset()
    for pid in pids:
        fd_dir = f"/proc/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:                       # gone, or another user's
            continue
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if (not target.startswith("/") or target.endswith(" (deleted)")
                    or target.startswith(("/dev/", "/proc/", "/sys/"))):
                continue
            try:
                with open(f"/proc/{pid}/fdinfo/{fd}") as f:
                    for line in f:
                        if line.startswith("flags:"):
                            if int(line.split()[1], 8) & os.O_ACCMODE != os.O_RDONLY:
                                found.add(target)
                            break
            except (OSError, ValueError):
                continue
    _open_cache["at"], _open_cache["paths"] = time.monotonic(), frozenset(found)
    return _open_cache["paths"]


def _locked_on_windows(path):
    if os.name != "nt":
        return False
    try:
        open(path, "r+b").close()
        return False
    except PermissionError as e:
        return getattr(e, "winerror", None) in (32, 33)   # sharing / lock violation
    except OSError:
        return False


# ── the check ────────────────────────────────────────────────────────────────
def check(path, settle=SETTLE_SECONDS, now=None):
    """One instant look: Readiness(ready, reason, sig, age). Never sleeps."""
    now = time.time() if now is None else now
    try:
        st = os.stat(path)
    except OSError:
        return Readiness(False, "the file is gone", None, 0.0)
    sig = (st.st_size, st.st_mtime_ns)
    if not stat.S_ISREG(st.st_mode):
        return Readiness(False, "not a regular file", sig, 0.0)
    # Every write moves mtime, so "age" is time since the last modification. An
    # mtime in the future (a file copied with preserved timestamps from a clock
    # that runs ahead) is not believable: use ctime for those, so the file
    # doesn't wait until that future date.
    last = st.st_mtime if st.st_mtime <= now + 60 else st.st_ctime
    age = max(0.0, now - last)

    def no(reason):
        return Readiness(False, reason, sig, age)

    if st.st_size == 0 and age < EMPTY_FILE_MIN_AGE:
        return no("it is still empty (0 bytes)")
    if age < settle:
        return no(f"it changed {age:.0f}s ago")
    if os.path.basename(path).lower().endswith(TEMP_SUFFIXES) and age < QUIET_SECONDS:
        return no("it looks like an unfinished download")
    locks = lock_files_for(path)
    if locks:
        return no(f"an editor lock file exists ({locks[0]})")
    if _locked_on_windows(path):
        return no("another program has it open")
    if os.path.realpath(path) in open_for_write_paths():
        return no("another program has it open for writing")
    return Readiness(True, "ok", sig, age)


def is_ready(path, settle=SETTLE_SECONDS):
    return check(path, settle).ready


def wait_until_ready(path, settle=SETTLE_SECONDS, poll_interval=0.5,
                     max_wait=None, log=None, stop_check=None, progress=None):
    """Block (on a background thread - never the UI thread) until the file is
    ready. Returns False if it vanished, `stop_check()` turned true, or
    `max_wait` seconds passed. `progress(waited_seconds, size)` is called each
    poll so a UI can show it is still waiting."""
    last_sig, last_reason, waited = None, None, 0.0
    while True:
        if stop_check and stop_check():
            return False
        r = check(path, settle)
        if r.sig is None:
            return False
        if r.ready and (r.age >= QUIET_SECONDS or r.sig == last_sig):
            return True
        reason = r.reason if not r.ready else "making sure it has stopped changing"
        last_sig = r.sig
        if log and reason != last_reason:
            log(f"  waiting: {reason}")
        last_reason = reason
        if progress:
            progress(waited, r.sig[0])
        if max_wait is not None and waited >= max_wait:
            if log:
                log(f"  gave up waiting ({reason})")
            return False
        time.sleep(poll_interval)
        waited += poll_interval


# ── copy / move that can't leave a half-written file ─────────────────────────
class FileChangedError(OSError):
    """The source changed while it was being copied."""


def _sig(path):
    st = os.stat(path)
    return (st.st_size, st.st_mtime_ns)


def _same_device(src, dst):
    try:
        return os.stat(src).st_dev == os.stat(os.path.dirname(dst) or ".").st_dev
    except OSError:
        return False


def _temp_name(dst):
    folder, name = os.path.split(dst)
    tmp, n = os.path.join(folder, f".{name}.srboli-part"), 0
    while os.path.lexists(tmp):
        n += 1
        tmp = os.path.join(folder, f".{name}.srboli-part{n}")
    return tmp


def safe_copy(src, dst, overwrite=False):
    """Copy src to dst; dst appears only once the copy is complete and the
    source is verified unchanged. Raises (and cleans up) otherwise."""
    import shutil
    if not overwrite and os.path.lexists(dst):
        raise FileExistsError(f"{dst} already exists")
    before = _sig(src)
    tmp = _temp_name(dst)
    try:
        shutil.copy2(src, tmp)
        if _sig(src) != before:
            raise FileChangedError("the file changed while it was being copied")
        if os.path.getsize(tmp) != before[0]:
            raise OSError("the copy is a different size than the original")
        if not overwrite and os.path.lexists(dst):
            raise FileExistsError(f"{dst} already exists")
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def safe_move(src, dst, overwrite=False):
    """Move src to dst. Same disk: an atomic rename. Another disk: a verified
    safe_copy first, and the original is removed only after that succeeded."""
    if not overwrite and os.path.lexists(dst):
        raise FileExistsError(f"{dst} already exists")
    if _same_device(src, dst):
        os.replace(src, dst)
        return
    safe_copy(src, dst, overwrite)
    try:
        os.remove(src)
    except OSError as e:
        raise OSError(f"copied, but couldn't remove the original: {e}") from e
