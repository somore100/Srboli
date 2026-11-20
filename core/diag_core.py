# core/diag_core.py - one zip with everything needed to debug a problem on a
# phone: versions, device, touch settings, the boot logs and any other logs.
# Standard library only. Contains no documents, passwords or API keys: only
# the log files and the facts listed in report().

import glob
import os
import platform
import sys
import time


def report(extra=None):
    """The facts as plain text. `extra` is a dict of more lines (screen state...)."""
    lines = [f"Srboli diagnostic report {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    try:
        from core.version import VERSION
        lines.append(f"Srboli version: {VERSION}")
    except Exception:
        pass
    lines.append(f"Python: {sys.version.split()[0]}  Platform: {platform.platform()}")
    try:
        import kivy
        lines.append(f"Kivy: {kivy.__version__}")
    except Exception:
        pass
    for k in ("ANDROID_ARGUMENT", "ANDROID_ROOT", "SDL_TOUCH_MOUSE_EVENTS"):
        lines.append(f"env {k}: {os.environ.get(k, '(unset)')}")
    try:
        from core import touch_dedupe as td
        lines.append(f"touch filter settings: {td.load_cfg()}")
        lines.append(f"touch ghost fix active: {td.source_fix_active()}")
        lines.append(f"duplicates dropped this run: {td.stats()}")
    except Exception as e:
        lines.append(f"touch info unavailable: {e}")
    try:
        from core import android_storage as a
        lines.append(f"full file access granted: {a.has_full_storage_access()}")
    except Exception:
        pass
    try:
        import app_data
        lines.append(f"data folder: {app_data.get_data_dir()}")
    except Exception:
        pass
    try:
        from kivy.config import Config
        lines.append(f"input config: {dict(Config.items('input'))}")
    except Exception:
        pass
    for k, v in (extra or {}).items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


def log_files():
    """Every log file worth sending."""
    found = []
    try:
        import app_data
        base = app_data.get_data_dir()
        found += glob.glob(os.path.join(base, "Srboli_*.log"))
        found += glob.glob(os.path.join(base, "logs", "*"))
        found += glob.glob(os.path.join(base, "touch", "*.json"))
    except Exception:
        pass
    return [p for p in dict.fromkeys(found) if os.path.isfile(p)]


def make_zip(dest_dir, extra=None):
    """Write Srboli_diagnostic_<time>.zip into dest_dir; returns (path, file_count)."""
    import zipfile
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, f"Srboli_diagnostic_{time.strftime('%Y%m%d_%H%M%S')}.zip")
    files = log_files()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("diagnostic.txt", report(extra))
        for p in files:
            try:
                z.write(p, os.path.join("files", os.path.basename(p)))
            except OSError:
                pass
    return out, len(files) + 1
