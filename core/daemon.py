# core/daemon.py — the headless background process (`Srboli --daemon`).
#
# HARD RULE: this module, and everything it imports, must never import
# Kivy. main.py dispatches to run() before any Kivy Config call, exactly
# like it does for --overlay, but --overlay's process still opens a tiny
# Kivy window; --daemon's does not open a UI at all. The UI is a
# separate process, started on demand (see "show_ui" below) and it exits
# when closed; this process keeps running in the background.
#
# Phase 0 built the shell (IPC + single-instance lock). Phase 1 (this)
# adds the reminders scheduler: a background thread that polls
# reminders.json/reminders_state.json (both Kivy-free, see
# core/reminders_core.py) and fires OS notifications (core/notify.py)
# for whatever's due, including catching up anything that was due while
# the daemon wasn't running.

import os
import sys
import time
import signal
import datetime
import threading

from core.daemon_ipc import DaemonServer, try_connect, ui_launch_cmd, spawn_detached
import core.reminders_core as reminders_core
import core.notify as notify
import core.file_sorter_watch as file_sorter_watch

START_GRACE = 0.15   # let a "stopping" reply actually reach the client
                     # before the listener socket goes away underneath it


class Daemon:
    def __init__(self):
        self.pid = os.getpid()
        self.start_time = time.time()
        self.server = DaemonServer(self._handle)
        self._watch_wake = threading.Event()
        self._wake = threading.Event()          # lets "reload" skip the wait
        self._scheduler_stop = threading.Event()
        self._scheduler_thread = None
        self._watch_thread = None

    # -- commands ---------------------------------------------------------
    def _handle(self, request):
        cmd = request.get("cmd")
        if cmd == "ping":
            return {"ok": True, "pid": self.pid}
        if cmd == "status":
            return {"ok": True, "pid": self.pid,
                    "uptime": time.time() - self.start_time}
        if cmd == "reload":
            # Config files (reminders.json, rulesets, ...) are always the
            # source of truth and get re-read from disk on every
            # scheduler tick regardless — "reload" just wakes the
            # scheduler immediately instead of making it wait out the
            # rest of its poll interval, so an edit in the UI (e.g.
            # saving a reminder for one second from now) is felt right
            # away rather than up to SCHEDULE_INTERVAL seconds later.
            self._wake.set()
            self._watch_wake.set()
            return {"ok": True, "reloaded": True}
        if cmd == "show_ui":
            try:
                spawn_detached(ui_launch_cmd())
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if cmd == "stop":
            threading.Thread(target=self._delayed_stop, daemon=True).start()
            return {"ok": True, "stopping": True}
        return {"ok": False, "error": f"unknown command: {cmd!r}"}

    def _delayed_stop(self):
        time.sleep(START_GRACE)
        self._scheduler_stop.set()
        self._wake.set()
        self.server.stop()

    # -- reminders scheduler ------------------------------------------------
    def _scan_reminders_once(self):
        try:
            reminders = reminders_core.load_reminders()
            state = reminders_core.load_state()
            now = datetime.datetime.now()
            due = reminders_core.scan_due(reminders, state, now)
            for r in due:
                notify.send_notification(r["title"], r.get("notes") or "Reminder")
                reminders_core.mark_fired(r, state, now)
            if due:
                reminders_core.prune_state(reminders, state)
                reminders_core.save_state(state)
        except Exception as e:
            # A bad reminders.json or a notifier hiccup must never take
            # the whole daemon down — log it and try again next tick.
            print(f"Srboli daemon: reminder scan failed: {e}")

    def _watch_loop(self):
        # Separate thread: waiting for a big download to finish must never
        # delay reminders.
        while not self._scheduler_stop.is_set():
            try:
                file_sorter_watch.scan_once(
                    stop_check=self._scheduler_stop.is_set)
            except Exception as e:
                print(f"Srboli daemon: folder watch failed: {e}")
            self._watch_wake.wait(timeout=file_sorter_watch.POLL_SECONDS)
            self._watch_wake.clear()

    def _scheduler_loop(self):
        while not self._scheduler_stop.is_set():
            self._scan_reminders_once()
            self._wake.wait(timeout=reminders_core.SCHEDULE_INTERVAL)
            self._wake.clear()

    # -- lifecycle ----------------------------------------------------------
    def run(self):
        if try_connect() is not None:
            print("Srboli daemon: already running, exiting.")
            return 1
        try:
            self.server.start()
        except OSError as e:
            print(f"Srboli daemon: couldn't start listening: {e}")
            return 1

        print(f"Srboli daemon: listening (pid {self.pid}).")
        self._install_signal_handlers()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        self._watch_thread = threading.Thread(
            target=self._watch_loop, daemon=True)
        self._watch_thread.start()

        self.server.serve_forever()
        self._scheduler_stop.set()
        self._wake.set()
        self._watch_wake.set()
        print("Srboli daemon: stopped.")
        return 0

    def _install_signal_handlers(self):
        def _on_signal(signum, frame):
            self._scheduler_stop.set()
            self._wake.set()
            self._watch_wake.set()
            self.server.stop()
        for sig in ("SIGTERM", "SIGINT"):
            handler = getattr(signal, sig, None)
            if handler is not None:
                try:
                    signal.signal(handler, _on_signal)
                except (ValueError, OSError):
                    pass        # e.g. not the main thread — best-effort only


def run():
    """Entry point for `Srboli --daemon` (called from main.py). Blocks
    until stopped; returns a process exit code."""
    return Daemon().run()


if __name__ == "__main__":
    sys.exit(run())
