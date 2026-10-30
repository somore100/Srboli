# core/single_instance.py - keep two copies of the app from sharing one config.
#
# An OS file lock on a small file beside the config: the OS drops it when the
# process dies, so a crash never leaves a stale lock behind. Two instances
# writing the same JSON files would race, so the second launch backs off.
# Set SROBOLI_MULTI=1 to skip the check (for development).
import os
import sys

_held = None        # keeps the lock's file object alive for the whole run


def acquire(path):
    """True if this process now owns the lock (or locking is unavailable);
    False when another instance already holds it. Never raises."""
    global _held
    if os.environ.get("SROBOLI_MULTI"):
        return True
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        f = open(path, "a+")
        try:
            if sys.platform.startswith("win"):
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        f.seek(0)
        f.truncate()
        f.write(str(os.getpid()))
        f.flush()
        _held = f
        return True
    except Exception:
        return True          # can't lock (read-only folder...): don't block startup


def release():
    global _held
    if _held is not None:
        try:
            _held.close()
        except Exception:
            pass
        _held = None
