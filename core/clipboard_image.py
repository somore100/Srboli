# core/clipboard_image.py - copy an IMAGE (not text) to the system clipboard.
# Kivy-free. Kivy's Clipboard is text-only, so this shells out to the
# platform's own tool. Returns (ok, message) and never raises.
#
#   Windows : PowerShell + System.Windows.Forms.Clipboard.SetImage
#   macOS   : osascript (PNGf)
#   Linux   : wl-copy (Wayland)  or  xclip (X11)
#   Android : not supported (Android needs a content:// URI + FileProvider)

import io
import os
import shutil
import subprocess
import sys
import tempfile


def _to_png(raw):
    """Any image bytes -> PNG bytes (needs Pillow unless already PNG)."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(raw)).convert("RGBA").save(buf, "PNG")
    return buf.getvalue()


def is_android():
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


def copy_image(raw):
    if is_android():
        return False, ("Copying an image isn't supported on Android yet - "
                       "use Download, then share it from your gallery.")
    try:
        png = _to_png(raw)
    except Exception as e:
        return False, f"Not an image I can copy ({e})"
    try:
        if sys.platform.startswith("win"):
            return _win(png)
        if sys.platform == "darwin":
            return _mac(png)
        return _linux(png)
    except Exception as e:
        return False, f"Copy failed: {e}"


def _tmp_png(png):
    fd, path = tempfile.mkstemp(suffix=".png", prefix="srboli_clip_")
    with os.fdopen(fd, "wb") as f:
        f.write(png)
    return path


def _win(png):
    path = _tmp_png(png)
    script = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
              f"$i=[System.Drawing.Image]::FromFile('{path}');"
              "[System.Windows.Forms.Clipboard]::SetImage($i)")
    r = subprocess.run(["powershell", "-STA", "-NoProfile", "-Command",
                        script], capture_output=True, timeout=20)
    return (r.returncode == 0,
            "Image copied to clipboard." if r.returncode == 0
            else "PowerShell failed: " + r.stderr.decode(errors="replace")[:120])


def _mac(png):
    path = _tmp_png(png)
    r = subprocess.run(
        ["osascript", "-e",
         f'set the clipboard to (read (POSIX file "{path}") as «class PNGf»)'],
        capture_output=True, timeout=20)
    return (r.returncode == 0,
            "Image copied to clipboard." if r.returncode == 0
            else "osascript failed: " + r.stderr.decode(errors="replace")[:120])


def _linux(png):
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        r = subprocess.run(["wl-copy", "--type", "image/png"], input=png,
                           capture_output=True, timeout=20)
        return (r.returncode == 0, "Image copied to clipboard."
                if r.returncode == 0 else "wl-copy failed")
    if shutil.which("xclip"):
        r = subprocess.run(["xclip", "-selection", "clipboard", "-t",
                            "image/png", "-i"], input=png,
                           capture_output=True, timeout=20)
        return (r.returncode == 0, "Image copied to clipboard."
                if r.returncode == 0 else "xclip failed")
    if shutil.which("wl-copy"):
        r = subprocess.run(["wl-copy", "--type", "image/png"], input=png,
                           capture_output=True, timeout=20)
        return (r.returncode == 0, "Image copied to clipboard."
                if r.returncode == 0 else "wl-copy failed")
    return False, ("No clipboard tool found. Install wl-clipboard "
                   "(Wayland: sudo dnf install wl-clipboard) or xclip (X11).")
