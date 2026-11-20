# core/clean_env.py - run system programs without Srboli's own libraries.
#
# A PyInstaller / AppImage build starts Srboli with LD_LIBRARY_PATH pointing at
# the libraries bundled inside it. Every program Srboli launches (ffmpeg,
# xdg-open, gio...) inherits that, loads the bundled libraries instead of the
# system's own and dies with errors like "version GLIBC_2.42 not found".
# PyInstaller keeps the user's original value in LD_LIBRARY_PATH_ORIG; this
# restores it. install() makes subprocess.Popen use the clean environment
# whenever the caller does not pass its own env.
import os
import subprocess

_LIB_VARS = ("LD_LIBRARY_PATH", "LD_PRELOAD", "DYLD_LIBRARY_PATH")
_APPIMAGE_VARS = ("PYTHONHOME", "PYTHONPATH", "APPDIR", "APPIMAGE",
                  "ARGV0", "OWD", "PYINSTALLER_RESET_ENVIRONMENT")
_installed = False


def clean_env(env=None):
    """A copy of `env` (default os.environ) as the user's shell had it."""
    out = dict(os.environ if env is None else env)
    for var in _LIB_VARS:
        orig = out.pop(var + "_ORIG", None)
        if orig is not None:
            out[var] = orig
        elif out.get(var) is not None and _bundled():
            out.pop(var, None)
    if _bundled():
        for var in _APPIMAGE_VARS:
            out.pop(var, None)
    return out


def _bundled():
    import sys
    return bool(getattr(sys, "frozen", False)) or "APPIMAGE" in os.environ


def install():
    """Make subprocess.Popen default to clean_env() (once)."""
    global _installed
    if _installed:
        return
    _installed = True
    orig_init = subprocess.Popen.__init__

    def __init__(self, *a, **kw):
        if kw.get("env") is None:
            kw["env"] = clean_env()
        orig_init(self, *a, **kw)

    subprocess.Popen.__init__ = __init__
