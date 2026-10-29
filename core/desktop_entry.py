# core/desktop_entry.py - build, install, list and remove Linux .desktop
# launchers (the "shortcut creator" screen). Kivy-free.
#
# A .desktop file is what makes an app show up in the application menu and
# lets a file manager launch it. Two places matter:
#   ~/.local/share/applications   the menu (and search) - always written
#   ~/Desktop                     an icon on the desktop - optional
#
# The format has two layers of escaping that are easy to get wrong:
#   1. Exec= has its own quoting: an argument with a space or shell character
#      is wrapped in double quotes, and inside them  " ` $ \  need a backslash;
#      a literal % is written %% (single % codes are placeholders for files).
#   2. The whole value is then string-escaped: \ becomes \\ and newline \n.
# build_exec()/parse_exec() do both, so a command typed like in a terminal
# (with quotes) comes out right and reads back to the same arguments.
#
# Every file written here carries X-Srboli-Created=true. list_created() and
# delete() only touch files with that key, so removing a shortcut can never
# delete some other program's launcher.

import os
import re
import shutil
import subprocess

CATEGORIES = ["Utility", "Development", "Game", "Graphics", "Network",
              "Office", "AudioVideo", "Education", "Science", "System",
              "Settings"]
MARKER_KEY = "X-Srboli-Created"

_EXEC_SPECIAL = set(" \t\n\"'\\><~|&;$*?#()`")


# ── value escaping ───────────────────────────────────────────────────────────
def escape_value(v):
    return (v.replace("\\", "\\\\").replace("\n", "\\n")
             .replace("\r", "\\r").replace("\t", "\\t"))


_UNESC = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


def unescape_value(v):
    return re.sub(r"\\(.)", lambda m: _UNESC.get(m.group(1), m.group(1)), v)


def _quote_arg(arg):
    arg = arg.replace("%", "%%")
    if arg == "" or any(ch in _EXEC_SPECIAL for ch in arg):
        arg = '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'
    return arg


def build_exec(argv):
    """argv list -> the (not yet string-escaped) Exec= value."""
    return " ".join(_quote_arg(a) for a in argv)


def parse_exec(value):
    """Exec= value -> argv list. Raises ValueError on an unterminated quote."""
    args, cur, quoted, started, i = [], [], False, False, 0
    while i < len(value):
        ch = value[i]
        if ch == "%" and value[i + 1:i + 2] == "%":
            cur.append("%")
            i += 2
            continue
        if quoted:
            if ch == "\\" and i + 1 < len(value):
                cur.append(value[i + 1])
                i += 2
                continue
            if ch == '"':
                quoted = False
            else:
                cur.append(ch)
        elif ch == '"':
            quoted = started = True
        elif ch in " \t":
            if cur or started:
                args.append("".join(cur))
                cur, started = [], False
        else:
            cur.append(ch)
        i += 1
    if quoted:
        raise ValueError("unterminated quote")
    if cur or started:
        args.append("".join(cur))
    return args


# ── building and reading ─────────────────────────────────────────────────────
def build_entry(name, argv, comment="", icon="", terminal=False,
                categories=(), path=""):
    """The text of a .desktop file."""
    cats = [c for c in categories if c in CATEGORIES]
    lines = ["[Desktop Entry]", "Type=Application", "Version=1.0",
             f"Name={escape_value(name.strip())}"]
    if comment.strip():
        lines.append(f"Comment={escape_value(comment.strip())}")
    lines.append(f"Exec={escape_value(build_exec(argv))}")
    if icon.strip():
        lines.append(f"Icon={escape_value(icon.strip())}")
    if path.strip():
        lines.append(f"Path={escape_value(path.strip())}")
    lines.append(f"Terminal={'true' if terminal else 'false'}")
    if cats:
        lines.append("Categories=" + ";".join(cats) + ";")
    lines.append(f"{MARKER_KEY}=true")
    return "\n".join(lines) + "\n"


def parse_entry(text):
    """Read the [Desktop Entry] section. Localised keys (Name[de]) are skipped."""
    d, inside = {}, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            inside = line == "[Desktop Entry]"
            continue
        if not inside or not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if "[" not in key:
            d[key] = unescape_value(val.strip())
    try:
        argv = parse_exec(d.get("Exec", ""))
    except ValueError:
        argv = []
    return {"name": d.get("Name", ""), "comment": d.get("Comment", ""),
            "argv": argv, "icon": d.get("Icon", ""),
            "path": d.get("Path", ""),
            "terminal": d.get("Terminal", "").lower() == "true",
            "categories": [c for c in d.get("Categories", "").split(";") if c],
            "ours": d.get(MARKER_KEY, "").lower() == "true"}


def validate(name, argv, icon="", path=""):
    """-> (errors, warnings). Errors block creating the file; warnings don't."""
    errors, warnings = [], []
    if not name.strip():
        errors.append("Give the shortcut a name.")
    if not argv:
        errors.append("Enter the command to run.")
    else:
        exe = argv[0]
        if not (shutil.which(exe) or os.path.isfile(os.path.expanduser(exe))):
            warnings.append(f"'{exe}' wasn't found - check the spelling or "
                            "use the full path.")
    if icon.strip().startswith("/") and not os.path.isfile(icon.strip()):
        warnings.append("The icon file doesn't exist.")
    if path.strip() and not os.path.isdir(os.path.expanduser(path.strip())):
        warnings.append("The working folder doesn't exist.")
    return errors, warnings


def filename_for(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug or 'shortcut'}.desktop"


# ── where files go ───────────────────────────────────────────────────────────
def is_supported():
    """.desktop launchers are a Linux desktop thing (not Android / Windows)."""
    import platform
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ:
        return False
    return platform.system() == "Linux"


def applications_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "applications")


def desktop_dir():
    """The user's Desktop folder, or None if there isn't one."""
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        if out and os.path.isdir(out) and out != os.path.expanduser("~"):
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    fallback = os.path.join(os.path.expanduser("~"), "Desktop")
    return fallback if os.path.isdir(fallback) else None


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o755)               # file managers only launch executables
    os.replace(tmp, path)


def _trust(path):
    """GNOME shows a desktop launcher as 'untrusted' until told otherwise."""
    if shutil.which("gio"):
        try:
            subprocess.run(["gio", "set", path, "metadata::trusted", "true"],
                           capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass


def exists(filename):
    return os.path.isfile(os.path.join(applications_dir(), filename))


def install(text, filename, on_desktop=False):
    """Write the launcher to the applications menu folder (and the Desktop).
    Returns (paths written, error or None)."""
    written = []
    try:
        path = os.path.join(applications_dir(), filename)
        _write(path, text)
        written.append(path)
        if on_desktop:
            d = desktop_dir()
            if d is None:
                return written, "Saved to the menu, but there is no Desktop folder."
            dpath = os.path.join(d, filename)
            _write(dpath, text)
            _trust(dpath)
            written.append(dpath)
    except OSError as e:
        return written, str(e)
    return written, None


def list_created():
    """[(path, entry dict)] of the launchers Srboli made, by name."""
    out = []
    folder = applications_dir()
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".desktop"):
            continue
        path = os.path.join(folder, fn)
        try:
            with open(path, encoding="utf-8") as f:
                entry = parse_entry(f.read())
        except (OSError, UnicodeDecodeError):
            continue
        if entry["ours"]:
            out.append((path, entry))
    return sorted(out, key=lambda pe: pe[1]["name"].lower())


def _is_ours(path):
    try:
        with open(path, encoding="utf-8") as f:
            return parse_entry(f.read())["ours"]
    except (OSError, UnicodeDecodeError):
        return False


def delete(filename):
    """Remove a launcher Srboli made (menu entry and Desktop copy).
    Files without the Srboli marker are never touched. Returns (ok, error)."""
    if os.path.basename(filename) != filename or not filename.endswith(".desktop"):
        return False, "Not a launcher file name."
    paths = [os.path.join(applications_dir(), filename)]
    d = desktop_dir()
    if d:
        paths.append(os.path.join(d, filename))
    removed = False
    try:
        for p in paths:
            if os.path.isfile(p) and _is_ours(p):
                os.remove(p)
                removed = True
    except OSError as e:
        return False, str(e)
    if not removed:
        return False, "That launcher wasn't made by Srboli, so it was left alone."
    return True, None
