# core/daemon_ipc.py — talking to the background daemon.
#
# Kivy-free (imported by the daemon itself, which never imports Kivy at
# all — see core/daemon.py and main.py's --daemon dispatch).
#
# Transport: stdlib multiprocessing.connection over a local Unix domain
# socket (POSIX) or a named pipe (Windows), authenticated with a random
# key stored in a 0600 file in the data dir. One request, one response,
# one short-lived connection per call — this is a control channel for
# occasional commands (show the UI, check status, reload, stop), not a
# stream, so there's no need to keep a connection open.
#
# Single-instance lock: the socket/pipe address itself IS the lock.
# Before binding, a starting daemon tries to CONNECT to that address; if
# something answers, a daemon is already running and this one backs off.
# If nothing answers, any stale Unix socket file left behind by a daemon
# that crashed is removed and a fresh Listener is bound in its place.
# Config files stay the source of truth throughout; this module only
# carries signals, never state.

import os
import sys
import threading
import subprocess
from multiprocessing.connection import Listener, Client

import app_data

_DAEMON_DIR_NAME = "daemon"
_PIPE_NAME = r"\\.\pipe\SrboliDaemon"
_SOCKET_NAME = "srboli.sock"
_AUTHKEY_NAME = "authkey"
_CONNECT_TIMEOUT = 2.0     # seconds to wait for a response to one request


def _daemon_dir():
    return app_data.subdir(_DAEMON_DIR_NAME)


def _address_and_family():
    if os.name == "nt":
        return _PIPE_NAME, "AF_PIPE"
    return os.path.join(_daemon_dir(), _SOCKET_NAME), "AF_UNIX"


def get_authkey():
    """Bytes used to authenticate the IPC connection. Generated once and
    reused (0600 — readable only by the user who ran Srboli)."""
    path = os.path.join(_daemon_dir(), _AUTHKEY_NAME)
    try:
        with open(path, "rb") as f:
            key = f.read()
        if key:
            return key
    except OSError:
        pass
    key = os.urandom(32)
    with open(path, "wb") as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass                # no-op on platforms without POSIX permissions
    return key


# ── client side ──────────────────────────────────────────────────────────
def try_connect():
    """A live Connection if a daemon is listening, else None. Never
    raises — every flavour of "nothing there" collapses to None, since
    the caller only cares about the yes/no."""
    address, family = _address_and_family()
    try:
        return Client(address, family=family, authkey=get_authkey())
    except Exception:
        return None


def send_command(cmd, timeout=_CONNECT_TIMEOUT, **fields):
    """Send one {"cmd": cmd, **fields} request, wait up to `timeout` for
    the reply. Returns the reply dict, or None if no daemon answered or
    it didn't reply in time."""
    conn = try_connect()
    if conn is None:
        return None
    try:
        conn.send(dict(fields, cmd=cmd))
        if conn.poll(timeout):
            return conn.recv()
        return None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def is_running():
    return try_connect() is not None


# ── server side ──────────────────────────────────────────────────────────
class DaemonServer:
    """One accept-loop, one request per connection. `handler(request_dict)
    -> response_dict` does the actual work; this class only owns the
    socket/pipe lifecycle."""

    def __init__(self, handler):
        self.handler = handler
        self._listener = None
        self._stopped = threading.Event()

    def start(self):
        """Bind the listener. Raises OSError if binding genuinely fails
        (e.g. a permissions problem) — callers should check
        try_connect()/is_running() first so that case means "broken",
        not "already running"."""
        address, family = _address_and_family()
        if family == "AF_UNIX" and os.path.exists(address):
            try:
                os.remove(address)          # stale file from a crashed daemon
            except OSError:
                pass
        self._listener = Listener(address, family=family,
                                  authkey=get_authkey())
        if family == "AF_UNIX":
            try:
                os.chmod(address, 0o600)
            except OSError:
                pass

    def serve_forever(self):
        """Blocks. Returns once stop() has woken the accept() call."""
        while not self._stopped.is_set():
            try:
                conn = self._listener.accept()
            except OSError:
                break                        # listener closed -> shutting down
            if self._stopped.is_set():
                # this connection is stop()'s own wake-up poke, below —
                # not a real request, don't hand it to the handler
                try:
                    conn.close()
                except Exception:
                    pass
                break
            try:
                self._handle_one(conn)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def _handle_one(self, conn):
        try:
            if not conn.poll(_CONNECT_TIMEOUT):
                return
            request = conn.recv()
            response = self.handler(request)
            conn.send(response)
        except (EOFError, OSError):
            pass

    def stop(self):
        self._stopped.set()
        # Closing the listening socket from a different thread than the
        # one blocked in accept() does NOT reliably unblock that accept()
        # (observed on Linux — close() there just drops a reference,
        # the kernel call doesn't return). Connecting to ourselves does:
        # accept() returns immediately with that connection, the loop
        # above sees _stopped set and exits instead of serving it.
        try:
            poke = try_connect()
            if poke is not None:
                poke.close()
        except Exception:
            pass
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass


# ── launching a process (used by "show_ui" and by Settings' Start button) ──
def _app_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ui_launch_cmd():
    """Command that starts the normal (Kivy) UI."""
    if getattr(sys, "frozen", False):
        return [sys.executable]             # the exe IS Srboli — no args
    return [sys.executable, os.path.join(_app_root(), "main.py")]


def daemon_launch_cmd():
    """Command that starts the headless daemon."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--daemon"]
    return [sys.executable, os.path.join(_app_root(), "main.py"), "--daemon"]


def spawn_detached(cmd):
    """Start `cmd` as an independent process that outlives whatever
    started it (the UI closing shouldn't take the daemon down with it,
    and vice versa)."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)
