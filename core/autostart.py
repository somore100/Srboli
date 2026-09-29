# core/autostart.py — "start the background service at login" toggle.
#
# Kivy-free. Two mechanisms, chosen by platform:
#   Linux:   an XDG autostart .desktop file in ~/.config/autostart
#   Windows: a value under HKCU\...\CurrentVersion\Run
# macOS isn't wired up yet (a LaunchAgent plist would be the equivalent)
# — matches the project's general "macOS is an open gap" scope. is_enabled()
# and disable() are harmless no-ops there; enable() reports it plainly
# rather than silently doing nothing.

import os
import shlex
import platform

_DESKTOP_NAME = "srboli-daemon.desktop"
_RUN_VALUE_NAME = "SrboliDaemon"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _platform():
    return platform.system()


def _desktop_path():
    return os.path.join(os.path.expanduser("~"), ".config", "autostart",
                        _DESKTOP_NAME)


def _cmd_str(cmd):
    return " ".join(shlex.quote(c) for c in cmd)


def is_supported():
    return _platform() in ("Linux", "Windows")


def is_enabled():
    system = _platform()
    if system == "Windows":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, _RUN_VALUE_NAME)
            return True
        except OSError:
            return False
    if system == "Linux":
        return os.path.isfile(_desktop_path())
    return False


def enable(cmd):
    """Make `cmd` (an argv list) run at login. Returns (ok, error)."""
    system = _platform()
    if system == "Windows":
        import winreg
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.SetValueEx(k, _RUN_VALUE_NAME, 0, winreg.REG_SZ,
                                  _cmd_str(cmd))
            return True, None
        except OSError as e:
            return False, str(e)

    if system == "Linux":
        path = _desktop_path()
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Srboli background service\n"
            f"Exec={_cmd_str(cmd)}\n"
            "Terminal=false\n"
            "Hidden=false\n"
            "NoDisplay=false\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Comment=Reminders and background tasks for Srboli\n"
        )
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, path)
            return True, None
        except OSError as e:
            return False, str(e)

    return False, f"Autostart isn't supported on {system} yet."


def disable():
    """Undo enable(). Returns (ok, error). Fine to call when already off."""
    system = _platform()
    if system == "Windows":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, _RUN_VALUE_NAME)
        except FileNotFoundError:
            pass
        except OSError as e:
            return False, str(e)
        return True, None

    if system == "Linux":
        try:
            if os.path.isfile(_desktop_path()):
                os.remove(_desktop_path())
        except OSError as e:
            return False, str(e)
        return True, None

    return True, None      # nothing was ever enabled on an unsupported OS
