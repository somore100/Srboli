# core/logs.py - app logs live in <data dir>/logs, size-capped.
import os
import subprocess
import sys

MAX_BYTES = 512_000


def logs_dir():
    import app_data
    return app_data.subdir("logs")


def append_capped(name, text, max_bytes=MAX_BYTES, folder=None):
    """Append text to logs/<name>; past max_bytes the file becomes <name>.prev
    (one old copy kept), so a log can't grow without limit."""
    path = os.path.join(folder or logs_dir(), name)
    try:
        if os.path.getsize(path) > max_bytes:
            os.replace(path, path + ".prev")
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)
    return path


def open_folder(path):
    """Show a folder in the file manager. Returns False if that's not possible
    here (e.g. Android), so the caller can show the path instead."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif "ANDROID_ARGUMENT" in os.environ:
            return False
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False
