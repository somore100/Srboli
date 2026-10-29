# core/transfer_core.py - the engine behind Fast Transfer (parallel copy/move of
# many files). Kivy-free so it can be tested and reused; the screen only adds
# the buttons.
#
# SCOPE NOTE (a recorded design decision): this is for MANY SMALLER FILES
# (extracted projects, photo dumps, source trees) - not a general "faster than
# the file manager" claim. A handful of very large files, or a destination on
# a spinning disk that has to seek between simultaneous writes, can transfer
# SLOWER this way than one at a time.
#
# How it works: the file list is collected up front, then up to N files are in
# flight at once on a thread pool (a rolling window, not rigid batches). The
# threads spend nearly all their time waiting on disk or network I/O, so this
# is not CPU-bound and the CPU core count is irrelevant. What matters is how
# many requests the destination can serve at once: SSD / NVMe / network shares
# gain up to roughly 4-16 workers and then flatten; more than that only adds
# queueing. So the worker count is capped (WORKER_HARD_LIMIT) and a real
# measurement, autotune(), replaces guessing.
#
# Every file passes the "is it finished?" check in core/file_safety.py. Files
# not touched for a while (nearly all of them) pass with one stat() and no
# sleeping; before this, every file paid ~0.45 s of sleeping, which made
# "more workers" look like a big win only because they overlapped the sleeps.
# Copies and moves go through file_safety.safe_copy / safe_move: the destination
# only appears once complete and verified, and a cross-disk move deletes the
# original last.

import os
import platform
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from core import file_safety

WORKER_SOFT_LIMIT = 16        # above this: warn that it won't help
WORKER_HARD_LIMIT = 64        # above this: clamped
TRANSFER_SETTLE_SECONDS = file_safety.SETTLE_SECONDS
TRANSFER_MAX_WAIT = 120.0     # skip a file that stays in use this long
TEMP_MARK = ".srboli-part"    # file_safety's temp name marker; never transferred

TUNE_WORKERS = (1, 2, 4, 8, 16)
TUNE_MAX_FILES = 48
TUNE_MAX_BYTES = 64 * 1024 * 1024
TUNE_MIN_FILES = 8            # fewer than this and the result means nothing
TUNE_TOLERANCE = 0.10         # "as fast as the best" = within 10 %
TUNE_REPEATS = 2              # best of two runs per setting


def clamp_workers(value):
    """-> (workers, warning or None). Always at least 1, at most the hard limit."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 1
    n = max(1, n)
    if n > WORKER_HARD_LIMIT:
        return WORKER_HARD_LIMIT, (f"{n} is more than is ever useful - using "
                                   f"{WORKER_HARD_LIMIT}.")
    if n > WORKER_SOFT_LIMIT:
        return n, (f"{n} workers rarely beats {WORKER_SOFT_LIMIT}: the disk "
                   "serves only so many requests at once, and extra workers "
                   "just queue. Try Auto-tune.")
    return n, None


# ── finding the files ────────────────────────────────────────────────────────
def collect_files_with_relpaths(source, recursive=True):
    """[(abs_path, rel_path), ...] for every regular file under `source`
    (rel_path rebuilds the folder structure under the destination). Temporary
    files left by an interrupted safe copy are skipped."""
    pairs = []
    if recursive:
        for root, _dirs, files in os.walk(source):
            for name in files:
                if TEMP_MARK in name:
                    continue
                abs_path = os.path.join(root, name)
                pairs.append((abs_path, os.path.relpath(abs_path, source)))
    else:
        for name in os.listdir(source):
            abs_path = os.path.join(source, name)
            if TEMP_MARK not in name and os.path.isfile(abs_path):
                pairs.append((abs_path, name))
    return pairs


def detect_rotational(path):
    """Best-effort: True/False if we can tell the disk backing `path` is a
    spinning hard drive, None if we can't (non-Linux, network mount, container
    without /sys). Never raises.

    CAVEAT: virtualised disks (VMs, some containers) often report
    rotational=1 even when the real storage is an SSD/NVMe. Treat True as
    "possibly rotational, be careful", not as certainty."""
    if platform.system() != "Linux":
        return None
    try:
        st = os.stat(path)
        dev_link = f"/sys/dev/block/{os.major(st.st_dev)}:{os.minor(st.st_dev)}"
        if not os.path.exists(dev_link):
            return None
        parts = os.path.realpath(dev_link).split(os.sep)
        if "block" not in parts:
            return None
        # .../block/sda/sda1 (partition) or .../block/sda (whole disk):
        # queue/rotational only exists on the whole disk, right after "block".
        disk_dir = os.sep.join(parts[:parts.index("block") + 2])
        rot_file = os.path.join(disk_dir, "queue", "rotational")
        if os.path.exists(rot_file):
            with open(rot_file) as f:
                return f.read().strip() == "1"
    except Exception:
        pass
    return None


def recommend_concurrency(file_count, avg_size_bytes, rotational):
    """-> (workers, reason). A starting point from file count, average size and
    (Linux, best effort) whether the destination is a spinning disk - never an
    authoritative number. autotune() measures instead of guessing."""
    if file_count <= 1:
        return 1, "Only one file - nothing to parallelize."
    if rotational is True:
        return 2, ("Destination looks like a spinning hard drive - it has to "
                   "physically seek between simultaneous writes, so a high "
                   "number here can be slower, not faster. Kept low on purpose.")
    if avg_size_bytes > 200 * 1024 * 1024:
        return min(3, file_count), (
            "These are large files - a single transfer already saturates most "
            "of the available throughput, so extra parallel transfers help less "
            "than they do for many small files.")
    reason = ("Lots of smaller files - this is the case parallel transfer helps "
              "most with.")
    if rotational is None:
        reason += (" (couldn't determine the destination's disk type, so "
                   "treating it as best-case.)")
    return min(6, file_count), reason


# ── one file, and the whole run ──────────────────────────────────────────────
def unique_dest_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def transfer_one(abs_path, rel_path, dest_root, mode, overwrite, stop_check,
                 log, settle=TRANSFER_SETTLE_SECONDS, max_wait=TRANSFER_MAX_WAIT):
    """-> (status, abs_path, dest_path, size_or_message); status is "done",
    "error", "stopped" or "skipped" (still in use after max_wait: left alone)."""
    if stop_check and stop_check():
        return ("stopped", abs_path, None, None)
    dest_path = os.path.join(dest_root, rel_path)
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    except Exception as e:
        return ("error", abs_path, None, str(e))
    if not overwrite:
        dest_path = unique_dest_path(dest_path)

    if not file_safety.wait_until_ready(abs_path, settle=settle,
                                        poll_interval=0.25, max_wait=max_wait,
                                        log=log, stop_check=stop_check):
        if stop_check and stop_check():
            return ("stopped", abs_path, None, None)
        if os.path.exists(abs_path):
            return ("skipped", abs_path, None,
                    f"still in use after {int(max_wait)}s - left where it is")
        return ("error", abs_path, None, "file disappeared while waiting for it")
    try:
        size = os.path.getsize(abs_path)
        if mode == "move":
            file_safety.safe_move(abs_path, dest_path, overwrite=overwrite)
        else:
            file_safety.safe_copy(abs_path, dest_path, overwrite=overwrite)
        return ("done", abs_path, dest_path, size)
    except Exception as e:
        return ("error", abs_path, None, str(e))


def run_transfer(pairs, dest_root, mode, concurrency, overwrite=False,
                 stop_check=None, log=None, on_result=None,
                 settle=TRANSFER_SETTLE_SECONDS, max_wait=TRANSFER_MAX_WAIT):
    """Run the transfer with up to `concurrency` files in flight. on_result(
    status, abs_path, dest_path, size_or_message) is called from a worker
    thread as each file finishes."""
    concurrency, _warning = clamp_workers(concurrency)
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(transfer_one, a, r, dest_root, mode, overwrite,
                               stop_check, log, settle, max_wait)
                   for a, r in pairs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result:
                on_result(*result)
    return results


# ── auto-tune: measure instead of guess ──────────────────────────────────────
def pick_sample(pairs, max_files=TUNE_MAX_FILES, max_bytes=TUNE_MAX_BYTES):
    """Files spread evenly through the list, small enough to copy quickly.
    -> ([abs_path, ...], total_bytes). A file bigger than a quarter of the
    byte budget is skipped (the test is about many small files)."""
    sized = []
    for abs_path, _rel in pairs:
        try:
            sized.append((abs_path, os.path.getsize(abs_path)))
        except OSError:
            continue
    sized = [(p, s) for p, s in sized if 0 < s <= max_bytes // 4]
    if not sized:
        return [], 0
    stride = max(1, len(sized) // max_files)
    picked, total = [], 0
    for p, s in sized[::stride]:
        if len(picked) >= max_files or total + s > max_bytes:
            break
        picked.append(p)
        total += s
    return picked, total


def pick_knee(results, tolerance=TUNE_TOLERANCE):
    """results: [(workers, seconds)]. The FEWEST workers whose speed is within
    `tolerance` of the fastest - more than that only queues."""
    timed = [(w, 1.0 / max(sec, 1e-9)) for w, sec in results]
    best = max(speed for _w, speed in timed)
    return min(w for w, speed in timed if speed >= best * (1 - tolerance))


def _read_through(paths):
    """Read every sample file once so later runs read from memory, not disk:
    the test is about the destination, and an uncached first run would make
    the low worker counts look unfairly slow."""
    for p in paths:
        with open(p, "rb") as f:
            while f.read(1024 * 1024):
                pass


def _timed_copy(paths, tmp_dir, workers, stop_check):
    for name in os.listdir(tmp_dir):
        os.remove(os.path.join(tmp_dir, name))
    t0 = time.perf_counter()

    def one(item):
        i, p = item
        if stop_check and stop_check():
            return
        file_safety.safe_copy(p, os.path.join(tmp_dir, f"{i}.bin"))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, enumerate(paths)))
    if hasattr(os, "sync"):
        os.sync()                      # count the time to actually reach the disk
    return time.perf_counter() - t0


def autotune(pairs, dest_root, worker_counts=TUNE_WORKERS, stop_check=None,
             progress=None):
    """Copy a sample of the real files into a throwaway folder on the
    destination with 1, 2, 4, 8, 16 workers, and report what is fastest.

    -> None when there is nothing to measure (too few small files) or it was
    stopped; else {"results": [(workers, seconds, MB/s)], "best": workers,
    "sample_files": n, "sample_bytes": b}. `progress(workers, index, total)` is
    called before each run. The throwaway folder is always removed."""
    paths, total_bytes = pick_sample(pairs)
    if len(paths) < TUNE_MIN_FILES:
        return None
    os.makedirs(dest_root, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=".srboli_tune_", dir=dest_root)
    try:
        _read_through(paths)
        counts = [w for w in worker_counts if w <= len(paths)]
        results = []
        for i, w in enumerate(counts):
            if stop_check and stop_check():
                return None
            if progress:
                progress(w, i, len(counts))
            best = min(_timed_copy(paths, tmp_dir, w, stop_check)
                       for _ in range(TUNE_REPEATS))
            results.append((w, best))
        if stop_check and stop_check():
            return None
        mb = total_bytes / (1024 * 1024)
        return {"results": [(w, sec, mb / max(sec, 1e-9)) for w, sec in results],
                "best": pick_knee(results), "sample_files": len(paths),
                "sample_bytes": total_bytes}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
