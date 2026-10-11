# core/bootlog.py - answers "where did the app get stuck?" without adb.
#
# 1. Breadcrumbs: log("stage") appends a timestamped line to Srboli_boot.log
#    (phone: shared storage root, PC: the data dir's parent fallback). The
#    previous run's file is kept as Srboli_boot.prev.log. If the app freezes
#    during start-up, the LAST line says which stage it never finished.
# 2. Watchdog: a daemon thread checks a heartbeat that the Kivy main loop
#    updates every 0.5 s. If the main loop stops beating for STALL seconds it
#    writes the main thread's Python stack to the same file - that stack is
#    where the app is actually stuck. (sys._current_frames is plain Python;
#    this is NOT faulthandler, which must stay off - see handoff lesson 4.)
#
# Cheap enough to leave on: one thread that sleeps, one tiny Clock callback.
# Never raises.

import os
import sys
import time
import threading
import traceback

STALL = 4.0          # seconds without a heartbeat = frozen
_path = None
_beat = [time.monotonic()]
_started = False
_lock = threading.Lock()


def _resolve_path():
    global _path
    if _path:
        return _path
    for base in _candidate_dirs():
        try:
            p = os.path.join(base, "Srboli_boot.log")
            if os.path.exists(p):
                os.replace(p, os.path.join(base, "Srboli_boot.prev.log"))
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"=== boot {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            _path = p
            return p
        except Exception:
            continue
    return None


def _candidate_dirs():
    dirs = []
    try:
        from core.android_storage import shared_storage_root
        dirs.append(shared_storage_root())
    except Exception:
        pass
    try:
        import app_data
        dirs.append(app_data.get_data_dir())
    except Exception:
        pass
    dirs.append(os.getcwd())
    return dirs


_t0 = time.monotonic()


def log(msg):
    try:
        with _lock:
            p = _resolve_path()
            if p:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(f"{time.monotonic() - _t0:8.2f}s {msg}\n")
    except Exception:
        pass


def flag(name):
    """True if an empty file `name` exists in the phone's storage root.
    Lets the user switch features off from a file manager, even when the
    app itself is too frozen to open Settings."""
    try:
        from core.android_storage import shared_storage_root
        return os.path.exists(os.path.join(shared_storage_root(), name))
    except Exception:
        return False


def start_watchdog():
    """Call once from App.build() (main thread)."""
    global _started
    if _started:
        return
    _started = True
    try:
        from kivy.clock import Clock

        def beat(dt):
            _beat[0] = time.monotonic()
        Clock.schedule_interval(beat, 0.5)
    except Exception:
        return
    main_ident = threading.main_thread().ident

    def watch():
        reported_at = 0.0
        while True:
            time.sleep(1.0)
            late = time.monotonic() - _beat[0]
            if late > STALL and time.monotonic() - reported_at > 20:
                reported_at = time.monotonic()
                try:
                    frame = sys._current_frames().get(main_ident)
                    stack = "".join(traceback.format_stack(frame)) \
                        if frame else "(no main frame)"
                except Exception as e:
                    stack = f"(could not read stack: {e})"
                log(f"!! MAIN LOOP STALLED {late:.1f}s - main thread stack:\n"
                    + stack)
            elif late <= STALL and reported_at:
                log(f"main loop recovered after a stall")
                reported_at = 0.0
    threading.Thread(target=watch, daemon=True, name="srboli-watchdog").start()
