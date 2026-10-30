# app_data.py — Central data directory manager
#
# Dev mode (python3 main.py): srboli_data/ next to main.py, same as before.
#
# Packaged builds (AppImage / .exe / .app): writing next to the executable
# doesn't work reliably —
#   - AppImages mount themselves read-only at /tmp/.mount_XXXXXX/, so
#     anything "next to the exe" can NEVER be written there, ever.
#   - Program Files (Windows) and /Applications (macOS) both typically
#     require admin/elevated rights to write into.
# So frozen builds use the platform's real user-data location instead:
#   Linux:   ~/.local/share/Srboli/          (XDG_DATA_HOME if set)
#   Windows: %APPDATA%/Srboli/
#   macOS:   ~/Library/Application Support/Srboli/
#
# Remembers choice in .srboli_config.json (same directory logic as above).
# MOVES data (not copies) when changing location.

import os, shutil, sys

from core.jsonio import read_json, write_json_atomic

_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_FROZEN   = getattr(sys, "frozen", False)


def _user_data_root():
    """Platform-appropriate, always-writable location for app data.
    Only used for frozen/packaged builds — see module docstring."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Srboli")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"),
                             "Library", "Application Support", "Srboli")
    # Linux and other unix-likes
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "Srboli")


def _android_root():
    """App-private storage that survives app updates, or None off Android.
    p4a unpacks the app's code into <files>/app and replaces that folder
    whenever the version changes; <files> itself (ANDROID_PRIVATE) is kept,
    so config and the default data folder live beside it, not inside it."""
    if os.environ.get("ANDROID_ARGUMENT") and os.environ.get("ANDROID_PRIVATE"):
        return os.path.join(os.environ["ANDROID_PRIVATE"], "srboli_userdata")
    return None


_ANDROID = _android_root()

if _ANDROID:
    _CONFIG_FILE = os.path.join(_ANDROID, ".srboli_config.json")
elif _FROZEN:
    _CONFIG_FILE = os.path.join(_user_data_root(), ".srboli_config.json")
else:
    _CONFIG_FILE = os.path.join(_APP_ROOT, ".srboli_config.json")

_APP_DIR = None


def _default_dir():
    if _ANDROID:
        return os.path.join(_ANDROID, "data")
    if _FROZEN:
        return os.path.join(_user_data_root(), "data")
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", _APP_ROOT)
        return os.path.join(base, "Srboli", "data")
    return os.path.join(_APP_ROOT, "srboli_data")


def _migrate_android():
    """One time: bring config + data from next to main.py (where older builds
    kept them, and where an update wipes them) into the persistent folder."""
    old_cfg = os.path.join(_APP_ROOT, ".srboli_config.json")
    old_data = os.path.join(_APP_ROOT, "srboli_data")
    new_data = _default_dir()
    try:
        os.makedirs(_ANDROID, exist_ok=True)
        if os.path.isdir(old_data) and not os.path.exists(new_data):
            shutil.move(old_data, new_data)
        if os.path.exists(old_cfg) and not os.path.exists(_CONFIG_FILE):
            cfg = read_json(old_cfg, {})
            if isinstance(cfg, dict):
                d = cfg.get("data_dir")
                if d and os.path.realpath(d) == os.path.realpath(old_data):
                    cfg["data_dir"] = new_data          # it moved with the data
                write_json_atomic(_CONFIG_FILE, cfg)
                os.remove(old_cfg)
    except OSError as e:
        print(f"Android migration skipped: {e}")


def get_data_dir() -> str:
    global _APP_DIR
    if _APP_DIR:
        return _APP_DIR
    if _ANDROID:
        _migrate_android()
    cfg  = _load_config()
    path = cfg.get("data_dir") or _default_dir()
    os.makedirs(path, exist_ok=True)
    _APP_DIR = path
    return path


class DataDirError(Exception):
    """The chosen folder can't be used (e.g. inside the current data)."""


class DataDirExists(DataDirError):
    """The target already holds data; nothing was changed."""
    def __init__(self, path):
        super().__init__(f"{path} already contains data")
        self.path = path


class MoveFailed(DataDirError):
    """Some files could not be copied; the app stays on the old location."""
    def __init__(self, failures):
        super().__init__(f"{len(failures)} file(s) could not be copied")
        self.failures = failures        # [(path, reason)]


def _nested(a, b):
    """True if a is b, or one lies inside the other (different drives: no)."""
    a, b = os.path.realpath(a), os.path.realpath(b)
    try:
        return os.path.commonpath([a, b]) in (a, b)
    except ValueError:
        return False


def _tree(root):
    """(dirs, files) below root as relative paths; symlinks count as files."""
    dirs, files = [], []
    for cur, dnames, fnames in os.walk(root):
        rel = os.path.relpath(cur, root)
        rel = "" if rel == "." else rel
        for d in list(dnames):
            full = os.path.join(cur, d)
            (files if os.path.islink(full) else dirs).append(os.path.join(rel, d))
            if os.path.islink(full):
                dnames.remove(d)
        files += [os.path.join(rel, f) for f in fnames]
    return dirs, files


def set_data_dir(new_base: str, move_old: bool = True, use_existing: bool = False,
                 progress=None) -> str:
    """Change the data dir to new_base/srboli_data.

    Existing data is copied with verification (core.file_safety) and the
    originals are deleted only after EVERY file is verified; the config
    switches only then. On any failure the app stays on the old location with
    all data intact and MoveFailed lists what went wrong. A target that
    already holds data raises DataDirExists; call again with use_existing=True
    to switch to it without moving anything. progress(done, total) is optional.
    """
    global _APP_DIR
    from core import file_safety
    old = get_data_dir()
    new = os.path.join(os.path.abspath(new_base), "srboli_data")
    if os.path.abspath(old) == new:
        return new
    has_old = move_old and os.path.isdir(old) and not use_existing
    if has_old:
        if _nested(old, new):
            raise DataDirError("Pick a folder outside the current data folder "
                               "(and not one that contains it).")
        if os.path.isdir(new) and os.listdir(new):
            raise DataDirExists(new)
    created_dir = not os.path.exists(new)
    os.makedirs(new, exist_ok=True)
    if has_old:
        dirs, files = _tree(old)
        done, failures, copied = 0, [], []
        for d in dirs:
            os.makedirs(os.path.join(new, d), exist_ok=True)
        for rel in files:
            src, dst = os.path.join(old, rel), os.path.join(new, rel)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.islink(src):
                    os.symlink(os.readlink(src), dst)
                else:
                    file_safety.safe_copy(src, dst)
                copied.append(rel)
            except Exception as e:
                failures.append((src, str(e)))
            done += 1
            if progress:
                progress(done, len(files))
        if failures:
            for rel in copied:          # target was empty: remove only our copies
                try:
                    os.remove(os.path.join(new, rel))
                except OSError:
                    pass
            for d in sorted(dirs, reverse=True):
                try:
                    os.rmdir(os.path.join(new, d))
                except OSError:
                    pass
            if created_dir:
                try:
                    os.rmdir(new)
                except OSError:
                    pass
            raise MoveFailed(failures)
    _save_config({"data_dir": new})
    _APP_DIR = new
    if has_old:                         # everything is verified in the new place
        for rel in files:
            try:
                os.remove(os.path.join(old, rel))
            except OSError:
                pass
        for d in sorted(dirs, reverse=True) + [""]:
            try:
                os.rmdir(os.path.join(old, d) if d else old)
            except OSError:
                pass
    return new


def is_configured() -> bool:
    """True if user has explicitly set a data dir before."""
    return os.path.exists(_CONFIG_FILE) and bool(_load_config().get("data_dir"))


CACHE_DIRS = ("gallery_cache", "metadata_cache")


def clear_cache() -> int:
    """Delete only the cache folders' contents (never other data)."""
    freed = 0
    for name in CACHE_DIRS:
        folder = os.path.join(get_data_dir(), name)
        for root, _dirs, files in os.walk(folder):
            for f in files:
                p = os.path.join(root, f)
                try:
                    size = os.path.getsize(p)
                    os.remove(p)
                    freed += size
                except OSError:
                    pass
    return freed


def clear_all_data():
    d = get_data_dir()
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d, exist_ok=True)


def subdir(name: str) -> str:
    p = os.path.join(get_data_dir(), name)
    os.makedirs(p, exist_ok=True)
    return p


def _load_config():
    data = read_json(_CONFIG_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_config(data: dict):
    """Read-modify-write, so other keys in the file are kept."""
    try:
        cfg = _load_config()
        cfg.update(data)
        write_json_atomic(_CONFIG_FILE, cfg)
    except Exception as e:
        print(f"Config save error: {e}")
