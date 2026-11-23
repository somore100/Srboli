# core/cleanup_core.py - find and remove junk files safely, and list memory-hungry programs.
# No Kivy.
#
# Safety rules (all enforced here, not only in the screen):
#  * Scan first: nothing is deleted that the scan did not list, and the list can be previewed.
#  * Only regular files inside a category's own folder; symlinks are never followed or removed.
#  * Files changed recently (min_age) are left alone: they may be in use.
#  * Every path is checked again against its folder right before removal.
#  * Only your own files; no system folders; no Documents, Downloads or Desktop.
#  * "Free memory" never kills anything by itself: closing a program is a separate, confirmed
#    step that asks it to quit politely and refuses system programs and Srboli itself.
import fnmatch
import gc
import os
import platform
import time

MAX_FILES = 300_000
HOUR = 3600


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class Category:
    def __init__(self, key, label, root, note="", min_age_hours=24, pattern="*",
                 default_on=True, own_files_only=False, exclude=()):
        self.key, self.label, self.root, self.note = key, label, root, note
        self.min_age = min_age_hours * HOUR
        self.pattern = pattern
        self.default_on = default_on
        self.own_files_only = own_files_only
        self.exclude = tuple(os.path.realpath(e) for e in exclude)


def system_name():
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ:
        return "Android"
    return platform.system()


def categories(system=None, home=None, env=None, own_cache_dirs=()):
    """The folders that are safe to tidy on this system."""
    system = system or system_name()
    home = home or os.path.expanduser("~")
    env = os.environ if env is None else env
    out = []
    own = [os.path.realpath(d) for d in own_cache_dirs]
    if system == "Linux":
        cache = os.path.join(home, ".cache")
        out += [
            Category("thumbs", "Thumbnail cache", os.path.join(cache, "thumbnails"),
                     "Picture previews. They are rebuilt when needed.", 0),
            Category("cache", "Application caches (~/.cache)", cache,
                     "Files programs can download or rebuild. Files from the last day are kept.",
                     24, exclude=[os.path.join(cache, "thumbnails")] + own),
            Category("tmp", "Old temporary files (/tmp)", "/tmp",
                     "Your own files older than 3 days.", 72, own_files_only=True),
            Category("trash", "Trash", os.path.join(home, ".local", "share", "Trash"),
                     "Permanently deletes what is in the Trash. Cannot be undone.", 0,
                     default_on=False),
        ]
    elif system == "Windows":
        local = env.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        out += [
            Category("temp", "Temporary files", env.get("TEMP") or os.path.join(local, "Temp"),
                     "Files older than a day in your Temp folder.", 24),
            Category("thumbs", "Thumbnail cache",
                     os.path.join(local, "Microsoft", "Windows", "Explorer"),
                     "Picture previews, rebuilt by Windows when needed.", 0,
                     pattern="thumbcache_*.db"),
            Category("crash", "Crash dumps", os.path.join(local, "CrashDumps"),
                     "Memory dumps left by crashed programs.", 0),
        ]
    elif system == "Darwin":
        out += [
            Category("cache", "Application caches", os.path.join(home, "Library", "Caches"),
                     "Files programs can rebuild. Files from the last day are kept.", 24,
                     exclude=own),
            Category("logs", "Old log files", os.path.join(home, "Library", "Logs"),
                     "Logs older than a week.", 168),
            Category("trash", "Trash", os.path.join(home, ".Trash"),
                     "Permanently deletes what is in the Trash. Cannot be undone.", 0,
                     default_on=False),
        ]
    for i, d in enumerate(own_cache_dirs):
        out.append(Category(f"srboli{i}", "Srboli's own cache: " + os.path.basename(d.rstrip("/\\")),
                            d, "Temporary data Srboli can rebuild.", 0))
    return out


# ---------- scanning ----------
def _walk_files(root, cancel=None):
    """Yield DirEntry for regular files under root, never following symlinks."""
    stack = [root]
    while stack:
        if cancel and cancel():
            return
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            yield e
                    except OSError:
                        continue
        except OSError:
            continue


def scan_category(cat, now=None, cancel=None, uid=None):
    now = now or time.time()
    uid = os.getuid() if (uid is None and hasattr(os, "getuid")) else uid
    res = {"key": cat.key, "label": cat.label, "note": cat.note, "root": cat.root,
           "default_on": cat.default_on, "files": [], "total": 0, "truncated": False,
           "min_age": cat.min_age, "pattern": cat.pattern, "own_files_only": cat.own_files_only}
    if not os.path.isdir(cat.root) or os.path.islink(cat.root):
        return res
    for e in _walk_files(cat.root, cancel):
        if cat.exclude and any(e.path.startswith(x + os.sep) for x in cat.exclude):
            continue
        if not fnmatch.fnmatch(e.name, cat.pattern):
            continue
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if cat.own_files_only and uid is not None and st.st_uid != uid:
            continue
        if cat.min_age and now - st.st_mtime < cat.min_age:
            continue
        res["files"].append((e.path, st.st_size))
        res["total"] += st.st_size
        if len(res["files"]) >= MAX_FILES:
            res["truncated"] = True
            break
    return res


def scan(cats, now=None, cancel=None, progress=None):
    out = []
    for i, c in enumerate(cats):
        if cancel and cancel():
            break
        if progress:
            progress(i, len(cats), c.label)
        out.append(scan_category(c, now, cancel))
    return out


# ---------- cleaning ----------
def _inside(path, root):
    r = os.path.realpath(root)
    p = os.path.realpath(os.path.dirname(path))
    return p == r or p.startswith(r + os.sep)


def clean(results, now=None, cancel=None):
    """Remove the files the scan listed. Returns {"freed", "deleted", "failed", "skipped"}."""
    now = now or time.time()
    out = {"freed": 0, "deleted": 0, "failed": 0, "skipped": 0}
    for res in results:
        root = res["root"]
        for path, size in res["files"]:
            if cancel and cancel():
                return out
            try:
                if os.path.islink(path) or not os.path.isfile(path) or not _inside(path, root):
                    out["skipped"] += 1
                    continue
                if res["min_age"] and now - os.lstat(path).st_mtime < res["min_age"]:
                    out["skipped"] += 1               # touched since the scan: leave it
                    continue
                os.remove(path)
                out["freed"] += size
                out["deleted"] += 1
            except OSError:
                out["failed"] += 1
        _remove_empty_dirs(root)
    return out


def _remove_empty_dirs(root):
    """Delete folders left empty under root (never root itself)."""
    for d, dirs, files in os.walk(root, topdown=False, followlinks=False):
        if d == root or os.path.islink(d):
            continue
        try:
            os.rmdir(d)                               # only succeeds when empty
        except OSError:
            pass


# ---------- memory ----------
PROTECTED = {"systemd", "init", "launchd", "kernel_task", "explorer.exe", "dwm.exe", "csrss.exe",
             "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
             "xorg", "xwayland", "gnome-shell", "plasmashell", "kwin_x11", "kwin_wayland",
             "mutter", "sddm", "gdm", "lightdm", "dbus-daemon", "pipewire", "pulseaudio",
             "wireplumber", "finder", "windowserver", "loginwindow", "dock"}


def is_protected(name):
    return (name or "").lower() in PROTECTED


def top_processes(psutil_mod, limit=15, own_pid=None):
    """The biggest programs of the current user: [{"pid", "name", "rss"}]."""
    own_pid = own_pid if own_pid is not None else os.getpid()
    try:
        me = psutil_mod.Process().username()
    except Exception:
        me = None
    out = []
    for p in psutil_mod.process_iter(["pid", "name", "memory_info", "username"]):
        try:
            info = p.info
            mi = info.get("memory_info")
            if mi is None or (me and info.get("username") != me):
                continue
            out.append({"pid": info["pid"], "name": info.get("name") or "?", "rss": mi.rss,
                        "protected": is_protected(info.get("name")) or info["pid"] == own_pid})
        except Exception:
            continue
    out.sort(key=lambda d: d["rss"], reverse=True)
    return out[:limit]


def close_process(psutil_mod, pid, own_pid=None):
    """Politely ask a program to quit. Returns (ok, message)."""
    own_pid = own_pid if own_pid is not None else os.getpid()
    if pid == own_pid:
        return False, "That is Srboli itself."
    try:
        p = psutil_mod.Process(pid)
        name = p.name()
        if is_protected(name):
            return False, f"{name} is part of the system and is not closed here."
        if p.username() != psutil_mod.Process().username():
            return False, "That program belongs to another user."
        p.terminate()
        return True, f"Asked {name} to close."
    except Exception as e:
        return False, f"Could not close it: {e}"


def free_own_memory():
    """Let Python give back what it no longer uses. Returns the number of objects freed."""
    return gc.collect()
