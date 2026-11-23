# core/startup_core.py - list and switch off the apps that start at login.
#
# Kivy-free. Nothing is ever deleted: "disable" only flips a switch the system
# itself understands, so "enable" brings the entry back exactly as it was.
#   Linux:   XDG autostart .desktop files (~/.config/autostart and, read-only,
#            /etc/xdg/autostart). Disabling writes Hidden=true and
#            X-GNOME-Autostart-enabled=false into a copy in the user folder.
#   Windows: the Run keys (HKCU and HKLM) and the Startup folder. Disabling
#            sets the same "StartupApproved" flag Task Manager uses.
# Android and macOS have no such list an app may edit: is_supported() is False.
import os
import platform

SYSTEM_DIRS = ["/etc/xdg/autostart"]
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"


def _platform():
    if "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ:
        return "Android"
    return platform.system()


def is_supported():
    return _platform() in ("Linux", "Windows")


def why_unsupported():
    p = _platform()
    if p == "Android":
        return ("Android does not let an app see or change which apps start "
                "at boot. Check Settings > Apps on your phone.")
    return "This system is not supported yet (Linux and Windows are)."


def user_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, "autostart")


# ---------- .desktop parsing (pure, testable) ----------

def parse_desktop(text):
    """The keys of the [Desktop Entry] group as a dict (first value wins)."""
    out, inside = {}, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            inside = line == "[Desktop Entry]"
            continue
        if inside and "=" in line:
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def desktop_disabled(keys):
    return (keys.get("Hidden", "").lower() == "true"
            or keys.get("X-GNOME-Autostart-enabled", "").lower() == "false")


def set_desktop_flags(text, disabled):
    """`text` with the disable keys added (disabled) or removed (enabled)."""
    drop = ("Hidden", "X-GNOME-Autostart-enabled")
    lines, out, inside, placed = text.splitlines(), [], False, False
    for raw in lines:
        s = raw.strip()
        if s.startswith("["):
            if inside and disabled and not placed:
                out += ["Hidden=true", "X-GNOME-Autostart-enabled=false"]
                placed = True
            inside = s == "[Desktop Entry]"
            out.append(raw)
            continue
        if inside and "=" in s and s.split("=", 1)[0].strip() in drop:
            continue
        out.append(raw)
    if disabled and not placed:
        if not inside and "[Desktop Entry]" not in text:
            out.append("[Desktop Entry]")
        out += ["Hidden=true", "X-GNOME-Autostart-enabled=false"]
    return "\n".join(out).rstrip("\n") + "\n"


def _entry(source, ident, name, command, enabled, writable, where):
    return {"source": source, "id": ident, "name": name or ident,
            "command": command or "", "enabled": enabled,
            "writable": writable, "where": where}


# ---------- Linux ----------

def _linux_list(udir=None, sdirs=None):
    udir = udir or user_dir()
    sdirs = SYSTEM_DIRS if sdirs is None else sdirs
    found = {}
    for d, writable, label in [(s, False, "System") for s in sdirs] + [(udir, True, "You")]:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".desktop"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
                    keys = parse_desktop(f.read())
            except OSError:
                continue
            prev = found.get(fn)
            # a user file overrides the system file of the same name
            name = keys.get("Name") or (prev or {}).get("name")
            cmd = keys.get("Exec") or (prev or {}).get("command")
            found[fn] = _entry("xdg", fn, name, cmd,
                               not desktop_disabled(keys), True, label)
    return sorted(found.values(), key=lambda e: e["name"].lower())


def _linux_set(ident, enable, udir=None, sdirs=None):
    udir = udir or user_dir()
    sdirs = SYSTEM_DIRS if sdirs is None else sdirs
    if "/" in ident or not ident.endswith(".desktop"):
        return False, "Bad entry name."
    path = os.path.join(udir, ident)
    src = path if os.path.isfile(path) else None
    if src is None:
        for d in sdirs:
            if os.path.isfile(os.path.join(d, ident)):
                src = os.path.join(d, ident)
                break
    if src is None:
        return False, "Entry not found."
    try:
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
        os.makedirs(udir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(set_desktop_flags(text, not enable))
    except OSError as e:
        return False, str(e)
    return True, ""


# ---------- Windows ----------

def approved_flag(data):
    """True if a StartupApproved binary value means 'enabled'."""
    return not data or (data[0] & 1) == 0 or data[0] == 0x02


def _win_list():
    import winreg
    out = []
    for hive, hname, writable in ((winreg.HKEY_CURRENT_USER, "HKCU", True),
                                  (winreg.HKEY_LOCAL_MACHINE, "HKLM", True)):
        approved = {}
        try:
            with winreg.OpenKey(hive, _APPROVED + r"\Run") as k:
                i = 0
                while True:
                    n, d, _ = winreg.EnumValue(k, i)
                    approved[n] = d
                    i += 1
        except OSError:
            pass
        try:
            with winreg.OpenKey(hive, _RUN_KEY) as k:
                i = 0
                while True:
                    n, v, _ = winreg.EnumValue(k, i)
                    i += 1
                    d = approved.get(n)
                    out.append(_entry("run" + hname, n, n, str(v),
                                      True if d is None else approved_flag(d),
                                      writable, "You" if hname == "HKCU" else "All users"))
        except OSError:
            pass
    folder = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                          "Start Menu", "Programs", "Startup")
    if os.path.isdir(folder):
        approved = {}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                _APPROVED + r"\StartupFolder") as k:
                i = 0
                while True:
                    n, d, _ = winreg.EnumValue(k, i)
                    approved[n] = d
                    i += 1
        except OSError:
            pass
        for fn in sorted(os.listdir(folder)):
            if fn.lower() == "desktop.ini":
                continue
            d = approved.get(fn)
            out.append(_entry("folder", fn, os.path.splitext(fn)[0],
                              os.path.join(folder, fn),
                              True if d is None else approved_flag(d), True, "You"))
    return sorted(out, key=lambda e: e["name"].lower())


def _win_set(source, ident, enable):
    import winreg
    if source == "runHKCU":
        hive, sub = winreg.HKEY_CURRENT_USER, r"\Run"
    elif source == "runHKLM":
        hive, sub = winreg.HKEY_LOCAL_MACHINE, r"\Run"
    else:
        hive, sub = winreg.HKEY_CURRENT_USER, r"\StartupFolder"
    data = bytes([2 if enable else 3]) + bytes(11)
    try:
        with winreg.CreateKeyEx(hive, _APPROVED + sub, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, ident, 0, winreg.REG_BINARY, data)
    except OSError as e:
        hint = " (this one needs administrator rights)" if source == "runHKLM" else ""
        return False, str(e) + hint
    return True, ""


# ---------- public ----------

def list_entries():
    s = _platform()
    if s == "Linux":
        return _linux_list()
    if s == "Windows":
        return _win_list()
    return []


def set_enabled(entry, enable):
    """Switch one entry on/off. Returns (ok, error)."""
    s = _platform()
    if s == "Linux":
        return _linux_set(entry["id"], enable)
    if s == "Windows":
        return _win_set(entry["source"], entry["id"], enable)
    return False, why_unsupported()
