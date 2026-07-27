# app_data.py — Central data directory manager
# Default: srboli_data/ next to main.py (Linux/Mac) or %APPDATA%/Srboli (Windows)
# Remembers choice in .srboli_config.json next to main.py
# MOVES data (not copies) when changing location

import os, json, shutil, sys

_APP_ROOT    = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_APP_ROOT, ".srboli_config.json")
_APP_DIR     = None


def _default_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", _APP_ROOT)
        return os.path.join(base, "Srboli", "data")
    return os.path.join(_APP_ROOT, "srboli_data")


def get_data_dir() -> str:
    global _APP_DIR
    if _APP_DIR:
        return _APP_DIR
    cfg  = _load_config()
    path = cfg.get("data_dir") or _default_dir()
    os.makedirs(path, exist_ok=True)
    _APP_DIR = path
    return path


def set_data_dir(new_base: str, move_old: bool = True) -> str:
    """Change data dir to new_base/srboli_data. MOVES existing data."""
    global _APP_DIR
    old  = get_data_dir()
    new  = os.path.join(os.path.abspath(new_base), "srboli_data")
    if os.path.abspath(old) == os.path.abspath(new):
        return new
    os.makedirs(new, exist_ok=True)
    if move_old and os.path.isdir(old):
        for item in os.listdir(old):
            src = os.path.join(old, item)
            dst = os.path.join(new, item)
            try:
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.move(src, dst)
                else:
                    shutil.move(src, dst)
            except Exception as e:
                print(f"Move warning: {e}")
        # remove old folder if empty
        try:
            if not os.listdir(old):
                os.rmdir(old)
        except Exception:
            pass
    _APP_DIR = new
    _save_config({"data_dir": new})
    return new


def is_configured() -> bool:
    """True if user has explicitly set a data dir before."""
    return os.path.exists(_CONFIG_FILE) and bool(_load_config().get("data_dir"))


def clear_cache() -> int:
    freed = 0
    d = get_data_dir()
    for root, dirs, files in os.walk(d):
        for f in files:
            if "thumb" in f or f.endswith(".tmp"):
                p = os.path.join(root, f)
                try:
                    freed += os.path.getsize(p)
                    os.remove(p)
                except Exception:
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
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(data: dict):
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Config save error: {e}")
