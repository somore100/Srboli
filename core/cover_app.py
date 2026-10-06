# core/cover_app.py — the Cover process (`Srboli --cover`).
#
# Runs with tkinter, NOT Kivy: Kivy allows one Window per process, and this
# feature needs several frameless always-on-top windows (boxes, frame
# strips, a blackout, a region picker). The process:
#   * shows privacy boxes ("solid" = opaque cover, "frame" = see-through
#     outline) and a full-desktop blackout,
#   * on Windows can hide chosen boxes from screen capture
#     (SetWindowDisplayAffinity) so you see them but recordings don't,
#   * registers global hotkeys via pynput (X11 / Windows; NOT Wayland),
#   * listens on a localhost control socket so the UI, the daemon, or a
#     system shortcut (`Srboli --cover-cmd toggle`) can drive it.
#
# Boxes are configured in cover.json (edited by the Cover screen); this
# process reloads it whenever the file changes.

import os
import sys
import time
import queue
import socket
import threading

import core.cover_core as cc

TICK_MS = 40
RELOAD_POLL_MS = 600
TOPMOST_MS = 1500
FRAME_THICKNESS = 3
GRIP = 16                       # px bottom-right resize zone on solid boxes
WDA_MONITOR = 0x01              # capture shows black
WDA_EXCLUDEFROMCAPTURE = 0x11   # capture shows what's underneath (Win10 2004+)


def _log(msg):
    line = f"{time.strftime('%H:%M:%S')} cover: {msg}"
    print(line)
    try:
        import app_data
        with open(os.path.join(app_data.subdir("cover"), "cover.log"),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _geo(x, y, w, h):
    return f"{int(w)}x{int(h)}{int(x):+d}{int(y):+d}"


# ── Windows-only: capture exclusion + DPI ───────────────────────────────
def _set_dpi_aware():
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _hide_from_capture(win):
    """Make `win` invisible to screen capture. True on success."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetAncestor(win.winfo_id(), 2)  # GA_ROOT
        fn = ctypes.windll.user32.SetWindowDisplayAffinity
        if fn(hwnd, WDA_EXCLUDEFROMCAPTURE):
            return True
        return bool(fn(hwnd, WDA_MONITOR))      # older Windows: black box
    except Exception as e:
        _log(f"capture exclusion failed: {e}")
        return False


def virtual_screen(root):
    """(x, y, w, h) covering all monitors."""
    if os.name == "nt":
        try:
            import ctypes
            g = ctypes.windll.user32.GetSystemMetrics
            return g(76), g(77), g(78), g(79)
        except Exception:
            pass
    try:
        w, h = root.winfo_vrootwidth(), root.winfo_vrootheight()
        if w > 0 and h > 0:
            return root.winfo_vrootx(), root.winfo_vrooty(), w, h
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


# ── hotkeys ─────────────────────────────────────────────────────────────
class HotkeyManager:
    def __init__(self, post):
        self._post = post
        self._listener = None
        self.status = "not started"

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def start(self, cfg):
        self.stop()
        if not cc.global_hotkeys_supported():
            self.status = (f"global hotkeys unavailable on "
                           f"{cc.session_type()} — use system shortcuts")
            return
        if not cc.pynput_available():
            self.status = "pynput not installed (pip install pynput)"
            return
        try:
            from pynput import keyboard
        except Exception as e:      # e.g. no X display / missing backend
            self.status = f"pynput failed to load: {e}"
            return
        mapping, bad = {}, []

        def bind(combo, action):
            if not combo:
                return
            try:
                keyboard.HotKey.parse(combo)
            except Exception:
                bad.append(combo)
                return
            if combo in mapping:
                bad.append(f"{combo} (duplicate)")
                return
            mapping[combo] = lambda a=action: self._post(a)

        for act in cc.HOTKEY_ACTIONS:
            bind(cfg["hotkeys"].get(act, ""), (act, ""))
        for b in cfg["boxes"]:
            bind(b.get("hotkey", ""), ("toggle_box", b["id"]))
        if not mapping:
            self.status = "no hotkeys configured"
            return
        try:
            self._listener = keyboard.GlobalHotKeys(mapping)
            self._listener.daemon = True
            self._listener.start()
            self.status = f"{len(mapping)} hotkey(s) active"
            if bad:
                self.status += f"; skipped: {', '.join(bad)}"
        except Exception as e:
            self.status = f"hotkey listener failed: {e}"


# ── control socket ──────────────────────────────────────────────────────
class ControlServer:
    def __init__(self, post, status_fn):
        self._post = post
        self._status = status_fn
        self._sock = None
        self._stop = False

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name == "nt":
            # SO_REUSEADDR on Windows would let a second instance bind the
            # same port; exclusive bind makes "already running" detectable.
            s.setsockopt(socket.SOL_SOCKET,
                         getattr(socket, "SO_EXCLUSIVEADDRUSE", 0), 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((cc.CONTROL_HOST, cc.CONTROL_PORT))     # OSError if taken
        s.listen(4)
        s.settimeout(0.5)
        self._sock = s
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            self._sock.close()
        except Exception:
            pass

    def _loop(self):
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._one, args=(conn,),
                             daemon=True).start()

    def _one(self, conn):
        try:
            conn.settimeout(2.0)
            data = b""
            while b"\n" not in data and len(data) < 512:
                chunk = conn.recv(256)
                if not chunk:
                    break
                data += chunk
            token, cmd, arg = cc.parse_control_line(
                data.decode("utf-8", "replace"))
            if cmd is None or not cc.token_ok(token):
                reply = "err auth"
            elif cmd == "ping":
                reply = f"ok {os.getpid()}"
            elif cmd == "status":
                reply = "ok " + self._status()
            elif cmd in ("toggle", "show", "hide", "blackout", "add_box",
                         "lock", "reload", "quit", "toggle_box"):
                self._post((cmd, arg))
                reply = "ok"
            else:
                reply = "err unknown command"
            conn.sendall((reply + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ── boxes ───────────────────────────────────────────────────────────────
class Box:
    def __init__(self, app, cfg):
        self.app = app
        self.cfg = cfg
        self.wins = []
        self.visible = False
        self._drag = None
        self._build()

    def _mk(self, bg):
        import tkinter as tk
        w = tk.Toplevel(self.app.root)
        w.withdraw()
        w.overrideredirect(True)
        w.configure(bg=bg, cursor="fleur")
        try:
            w.attributes("-topmost", True)
            w.attributes("-alpha", self.cfg["opacity"])
        except Exception:
            pass
        w.bind("<ButtonPress-1>", self._press)
        w.bind("<B1-Motion>", self._motion)
        w.bind("<ButtonRelease-1>", self._release)
        w.bind("<ButtonPress-3>", lambda e: self.app.set_box(self.cfg["id"],
                                                             False))
        w.bind("<Motion>", self._hover)
        return w

    def _build(self):
        c = self.cfg
        n = 4 if c["style"] == "frame" else 1
        self.wins = [self._mk(c["color"]) for _ in range(n)]
        self._place()
        if c["hide_from_capture"]:
            for w in self.wins:
                w.deiconify()
                _hide_from_capture(w)
                w.withdraw()

    def _rects(self):
        c, t = self.cfg, FRAME_THICKNESS
        x, y, w, h = c["x"], c["y"], c["w"], c["h"]
        if c["style"] != "frame":
            return [(x, y, w, h)]
        t = min(t, max(1, min(w, h) // 2))
        return [(x, y, w, t), (x, y + h - t, w, t),
                (x, y + t, t, max(1, h - 2 * t)),
                (x + w - t, y + t, t, max(1, h - 2 * t))]

    def _place(self):
        for win, r in zip(self.wins, self._rects()):
            win.geometry(_geo(*r))

    def show(self):
        for w in self.wins:
            w.deiconify()
            try:
                w.attributes("-topmost", True)
            except Exception:
                pass
            w.lift()
        self.visible = True

    def hide(self):
        for w in self.wins:
            w.withdraw()
        self.visible = False

    def keep_on_top(self):
        if self.visible:
            for w in self.wins:
                try:
                    w.lift()
                except Exception:
                    pass

    def destroy(self):
        for w in self.wins:
            try:
                w.destroy()
            except Exception:
                pass
        self.wins = []

    # ── mouse: drag to move, bottom-right corner to resize (solid) ──
    def _in_grip(self, e):
        c = self.cfg
        return (c["style"] == "solid"
                and e.x_root >= c["x"] + c["w"] - GRIP
                and e.y_root >= c["y"] + c["h"] - GRIP)

    def _hover(self, e):
        cur = "size_nw_se" if self._in_grip(e) else "fleur"
        try:
            e.widget.configure(cursor=cur)
        except Exception:
            pass

    def _press(self, e):
        c = self.cfg
        self._drag = {"mode": "resize" if self._in_grip(e) else "move",
                      "mx": e.x_root, "my": e.y_root,
                      "x": c["x"], "y": c["y"], "w": c["w"], "h": c["h"]}

    def _motion(self, e):
        d = self._drag
        if not d:
            return
        dx, dy = e.x_root - d["mx"], e.y_root - d["my"]
        c = self.cfg
        if d["mode"] == "move":
            c["x"], c["y"] = d["x"] + dx, d["y"] + dy
        else:
            c["w"], c["h"] = max(24, d["w"] + dx), max(24, d["h"] + dy)
        self._place()

    def _release(self, e):
        if self._drag:
            self._drag = None
            c = self.cfg
            self.app.save_geometry(c["id"], c["x"], c["y"], c["w"], c["h"])


# ── application ─────────────────────────────────────────────────────────
class CoverApp:
    def __init__(self):
        import tkinter as tk
        _set_dpi_aware()
        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.report_callback_exception = (
            lambda et, ev, tb: _log(f"tk callback error: {ev!r}"))
        self.q = queue.Queue()
        self.cfg = cc.load_config()
        self.boxes = {}
        self.override = {}          # box id -> True/False (individual toggle)
        self.shown = not self.cfg["start_hidden"]
        self.blackout_win = None
        self.picker = None
        self._own_mtime = 0.0
        self._seen_mtime = cc.config_mtime()
        self.hotkeys = HotkeyManager(self.q.put)
        self.server = ControlServer(self.q.put, self._status_text)
        self._status_cache = "starting"

    # -- status -----------------------------------------------------------
    def _status_text(self):
        return self._status_cache

    def _refresh_status(self):
        vis = sum(1 for b in self.boxes.values() if b.visible)
        self._status_cache = (
            f"boxes={len(self.boxes)} visible={vis} "
            f"blackout={'on' if self.blackout_win else 'off'} "
            f"session={cc.session_type()} hotkeys=[{self.hotkeys.status}]")

    # -- boxes ------------------------------------------------------------
    def rebuild(self):
        for b in self.boxes.values():
            b.destroy()
        self.boxes = {}
        for bc in self.cfg["boxes"]:
            try:
                self.boxes[bc["id"]] = Box(self, dict(bc))
            except Exception as e:
                _log(f"box {bc.get('id')} failed: {e}")
        self.override = {k: v for k, v in self.override.items()
                         if k in self.boxes}
        self.apply_visibility()
        self.hotkeys.start(self.cfg)

    def apply_visibility(self):
        for bid, b in self.boxes.items():
            want = self.override.get(bid, self.shown)
            if want and not b.visible:
                b.show()
            elif not want and b.visible:
                b.hide()

    def set_box(self, bid, on):
        if bid in self.boxes:
            self.override[bid] = on
            self.apply_visibility()

    def toggle_box(self, bid):
        b = self.boxes.get(bid)
        if b:
            self.set_box(bid, not b.visible)

    def set_all(self, on):
        self.shown = on
        self.override.clear()
        self.apply_visibility()

    def save_geometry(self, bid, x, y, w, h):
        try:
            cfg = cc.load_config()
            for b in cfg["boxes"]:
                if b["id"] == bid:
                    b.update(x=x, y=y, w=w, h=h)
            cc.save_config(cfg)
            self._own_mtime = cc.config_mtime()
            self.cfg = cc.load_config()
        except Exception as e:
            _log(f"saving geometry failed: {e}")

    # -- blackout ---------------------------------------------------------
    def toggle_blackout(self):
        if self.blackout_win is not None:
            try:
                self.blackout_win.destroy()
            except Exception:
                pass
            self.blackout_win = None
            return
        tk = self.tk
        bo = self.cfg["blackout"]
        vx, vy, vw, vh = virtual_screen(self.root)
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.configure(bg=bo["color"], cursor="none")
        w.geometry(_geo(vx, vy, vw, vh))
        try:
            w.attributes("-topmost", True)
            w.attributes("-alpha", bo["opacity"])
        except Exception:
            pass
        w.bind("<Double-Button-1>", lambda e: self.toggle_blackout())
        w.bind("<Escape>", lambda e: self.toggle_blackout())
        w.lift()
        try:
            w.focus_force()
        except Exception:
            pass
        self.blackout_win = w
        if self.cfg.get("lock_after_blackout"):
            cc.lock_session()

    # -- region picker (draw a new box) -----------------------------------
    def start_picker(self):
        if self.picker is not None:
            return
        tk = self.tk
        vx, vy, vw, vh = virtual_screen(self.root)
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.configure(bg="black", cursor="crosshair")
        w.geometry(_geo(vx, vy, vw, vh))
        try:
            w.attributes("-topmost", True)
            w.attributes("-alpha", 0.25)
        except Exception:
            pass
        cv = tk.Canvas(w, bg="black", highlightthickness=0, cursor="crosshair")
        cv.pack(fill="both", expand=True)
        st = {"x0": 0, "y0": 0, "id": None}

        def close():
            try:
                w.destroy()
            except Exception:
                pass
            self.picker = None

        def press(e):
            st["x0"], st["y0"] = e.x_root, e.y_root
            st["id"] = cv.create_rectangle(
                e.x_root - vx, e.y_root - vy, e.x_root - vx, e.y_root - vy,
                outline="white", width=2)

        def motion(e):
            if st["id"] is not None:
                cv.coords(st["id"], st["x0"] - vx, st["y0"] - vy,
                          e.x_root - vx, e.y_root - vy)

        def release(e):
            x0, y0, x1, y1 = st["x0"], st["y0"], e.x_root, e.y_root
            close()
            x, y = min(x0, x1), min(y0, y1)
            bw, bh = abs(x1 - x0), abs(y1 - y0)
            if bw >= 8 and bh >= 8:
                self.add_box(x, y, bw, bh)

        cv.bind("<ButtonPress-1>", press)
        cv.bind("<B1-Motion>", motion)
        cv.bind("<ButtonRelease-1>", release)
        for ev in ("<ButtonPress-3>", "<Escape>"):
            w.bind(ev, lambda e: close())
            cv.bind(ev, lambda e: close())
        w.lift()
        try:
            w.focus_force()
        except Exception:
            pass
        self.picker = w

    def add_box(self, x, y, w, h):
        try:
            cfg = cc.load_config()
            bid, n = cc.new_box_id(cfg)
            nb = cc.default_box(n)
            nb.update(id=bid, x=int(x), y=int(y), w=int(w), h=int(h))
            cfg["boxes"].append(cc.normalize_box(nb, n))
            cc.save_config(cfg)
            self._own_mtime = cc.config_mtime()
            self._seen_mtime = self._own_mtime
            self.cfg = cc.load_config()
            self.override[bid] = True
            self.rebuild()
        except Exception as e:
            _log(f"add_box failed: {e}")

    # -- commands ---------------------------------------------------------
    def handle(self, item):
        cmd, arg = item
        if cmd == "toggle":
            anyvis = any(b.visible for b in self.boxes.values())
            self.set_all(not anyvis)
        elif cmd == "show":
            self.set_all(True)
        elif cmd == "hide":
            self.set_all(False)
        elif cmd == "toggle_box":
            self.toggle_box(arg)
        elif cmd == "blackout":
            self.toggle_blackout()
        elif cmd == "add_box":
            self.start_picker()
        elif cmd == "lock":
            cc.lock_session()
        elif cmd == "reload":
            self._reload()
        elif cmd == "quit":
            self.shutdown()

    def _reload(self):
        self.cfg = cc.load_config()
        self._seen_mtime = cc.config_mtime()
        self.rebuild()

    # -- loop -------------------------------------------------------------
    def _tick(self):
        try:
            while True:
                self.handle(self.q.get_nowait())
        except queue.Empty:
            pass
        self._refresh_status()
        self.root.after(TICK_MS, self._tick)

    def _poll_config(self):
        m = cc.config_mtime()
        if m != self._seen_mtime and m != self._own_mtime:
            self._reload()
        self._seen_mtime = m
        self.root.after(RELOAD_POLL_MS, self._poll_config)

    def _keep_top(self):
        for b in self.boxes.values():
            b.keep_on_top()
        if self.blackout_win is not None:
            try:
                self.blackout_win.lift()
            except Exception:
                pass
        self.root.after(TOPMOST_MS, self._keep_top)

    def shutdown(self):
        self.hotkeys.stop()
        self.server.stop()
        try:
            self.root.quit()
        except Exception:
            pass

    def run(self):
        try:
            self.server.start()
        except OSError:
            _log("already running (control port busy) — exiting")
            try:
                self.root.destroy()
            except Exception:
                pass
            return 1
        _log(f"started pid={os.getpid()} session={cc.session_type()}")
        self.rebuild()
        self.root.after(TICK_MS, self._tick)
        self.root.after(RELOAD_POLL_MS, self._poll_config)
        self.root.after(TOPMOST_MS, self._keep_top)
        try:
            self.root.mainloop()
        finally:
            self.hotkeys.stop()
            self.server.stop()
        _log("stopped")
        return 0


def run():
    """Entry for `Srboli --cover`. Returns an exit code."""
    if not cc.tk_available():
        print("Srboli cover: tkinter is not installed.\n"
              "  Fedora: sudo dnf install python3-tkinter\n"
              "  Debian/Ubuntu: sudo apt install python3-tk")
        return 2
    return CoverApp().run()


def run_cmd(argv):
    """Entry for `Srboli --cover-cmd <command> [arg]`. No Kivy, no tk."""
    if not argv:
        print("usage: --cover-cmd toggle|show|hide|blackout|add_box|lock|"
              "reload|quit|status|ping")
        return 2
    reply = cc.send_cover_command(argv[0].lower(),
                                  " ".join(argv[1:]))
    if reply is None:
        if argv[0].lower() in ("toggle", "show", "blackout", "add_box"):
            # Nothing running: start it, so a shortcut press is never a no-op.
            if cc.start_cover():
                for _ in range(30):
                    time.sleep(0.1)
                    if cc.is_running():
                        break
                if argv[0].lower() in ("toggle", "show"):
                    reply = "ok started"    # a fresh start already shows
                else:
                    reply = cc.send_cover_command(
                        argv[0].lower(), " ".join(argv[1:]))
    print(reply if reply is not None else "cover process not running")
    return 0 if (reply or "").startswith("ok") else 1
