# core/cursor_app.py - the Cursor Overlay process (`Srboli --cursor`). Windows.
#
# Runs with tkinter, not Kivy (Kivy allows one window per process). One small borderless,
# always-on-top window whose background is a colour key (fully see-through) and which is made
# click-through with WS_EX_TRANSPARENT, so it never steals a click. It follows the real pointer
# (GetCursorPos) and flashes bigger while a mouse button is held. Settings come from
# cursor.json and are re-read when the file changes; the process ends when "quit" is set
# (or the heartbeat file can no longer be written).
import os
import sys
import time

from core import cursor_core as cc

TICK_MS = 15
RELOAD_MS = 400
KEY = "#010203"                     # the see-through colour key
VK_LBUTTON, VK_RBUTTON = 0x01, 0x02


def _log(msg):
    try:
        import app_data
        with open(os.path.join(app_data.subdir("cursor"), "cursor.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _pointer(win32):
    class POINT(win32.Structure):
        _fields_ = [("x", win32.c_long), ("y", win32.c_long)]
    p = POINT()
    win32.windll.user32.GetCursorPos(win32.byref(p))
    return p.x, p.y


def _buttons_down(ctypes):
    u = ctypes.windll.user32
    return bool(u.GetAsyncKeyState(VK_LBUTTON) & 0x8000 or u.GetAsyncKeyState(VK_RBUTTON) & 0x8000)


def _click_through(ctypes, win):
    """Let every click pass through the window and keep it out of Alt-Tab."""
    win.update_idletasks()
    hwnd = ctypes.windll.user32.GetAncestor(win.winfo_id(), 2)
    GWL_EXSTYLE = -20
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= 0x80000 | 0x20 | 0x80 | 0x08000000    # LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def run():
    if os.name != "nt":
        print("The cursor overlay works on Windows only.")
        return 1
    import ctypes
    import tkinter as tk
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg=KEY)
    root.attributes("-transparentcolor", KEY)
    canvas = tk.Canvas(root, bg=KEY, highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)
    state = {"cfg": cc.load(), "mtime": 0.0, "size": 0, "flash": False, "shown": True, "drawn": None}

    def redraw(flash):
        cfg = state["cfg"]
        key = (cfg["shape"], cfg["size"], cfg["thickness"], cfg["color"], flash)
        if state["drawn"] == key:
            return
        state["drawn"] = key
        c = dict(cfg)
        if flash:
            c["size"] = int(cfg["size"] * 1.35)
        n = cc.canvas_size(c)
        root.geometry(f"{n}x{n}")
        canvas.config(width=n, height=n)
        canvas.delete("all")
        color, t = c["color"], c["thickness"] + (2 if flash else 0)
        for it in cc.shape_items(c):
            kind = it[0]
            if kind in ("oval", "rect"):
                _, x0, y0, x1, y1, filled = it
                fn = canvas.create_oval if kind == "oval" else canvas.create_rectangle
                fn(x0, y0, x1, y1, outline=color, width=t, fill=color if filled else "")
            elif kind == "line":
                canvas.create_line(*it[1:5], fill=color, width=t, capstyle="round")
            else:
                canvas.create_polygon(*[v for pt in it[1] for v in pt], fill=color,
                                      outline="black", width=1)
        root.attributes("-alpha", c["opacity"])
        state["size"] = n
        _click_through(ctypes, root)

    def reload_cfg():
        try:
            m = os.path.getmtime(cc.config_path())
        except OSError:
            m = 0.0
        if m != state["mtime"]:
            state["mtime"] = m
            state["cfg"] = cc.load()
            state["drawn"] = None
        root.after(RELOAD_MS, reload_cfg)

    def beat():
        cc.touch_alive()
        root.after(1000, beat)

    def tick():
        cfg = state["cfg"]
        if cfg["quit"]:
            root.destroy()
            return
        if not cfg["visible"]:
            if state["shown"]:
                root.withdraw()
                state["shown"] = False
        else:
            if not state["shown"]:
                root.deiconify()
                state["shown"] = True
                state["drawn"] = None
            flash = bool(cfg["click_flash"] and _buttons_down(ctypes))
            redraw(flash)
            c = dict(cfg)
            if flash:
                c["size"] = int(cfg["size"] * 1.35)
            hx, hy = cc.hotspot(c)
            x, y = _pointer(ctypes)
            root.geometry(f"+{x - hx}+{y - hy}")
            root.attributes("-topmost", True)
        root.after(TICK_MS, tick)

    reload_cfg()
    beat()
    tick()
    _log("started")
    try:
        root.mainloop()
    finally:
        try:
            os.remove(cc.alive_path())
        except OSError:
            pass
        _log("stopped")
    return 0
