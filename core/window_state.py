# core/window_state.py - remember the desktop window's size and position.
# restore() runs before the window exists (it only sets Kivy Config values);
# save() runs when the app stops. Never raises; nothing happens on Android.
import os

from core.jsonio import read_json, write_json_atomic

MIN_W, MIN_H, MAX_SIZE = 320, 400, 10000


def _path():
    import app_data
    return os.path.join(app_data.subdir("config"), "window.json")


def valid(state):
    """The saved dict if it holds a sane size, else None."""
    try:
        w, h = int(state["width"]), int(state["height"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (MIN_W <= w <= MAX_SIZE and MIN_H <= h <= MAX_SIZE):
        return None
    out = {"width": w, "height": h}
    try:
        x, y = int(state["left"]), int(state["top"])
        if -MAX_SIZE < x < MAX_SIZE and -MAX_SIZE < y < MAX_SIZE:
            out["left"], out["top"] = x, y
    except (TypeError, ValueError, KeyError):
        pass
    return out


def restore(Config, on_android):
    if on_android:
        return
    try:
        st = valid(read_json(_path(), None))
        if not st:
            return
        Config.set("graphics", "width", str(st["width"]))
        Config.set("graphics", "height", str(st["height"]))
        if "left" in st:
            Config.set("graphics", "position", "custom")
            Config.set("graphics", "left", str(st["left"]))
            Config.set("graphics", "top", str(st["top"]))
    except Exception as e:
        print(f"window state not restored: {e}")


def save(Window, on_android):
    if on_android:
        return
    try:
        st = {"width": int(Window.width), "height": int(Window.height)}
        if getattr(Window, "left", None) is not None:
            st["left"], st["top"] = int(Window.left), int(Window.top)
        if valid(st):
            write_json_atomic(_path(), st)
    except Exception as e:
        print(f"window state not saved: {e}")
