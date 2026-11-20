# core/open_with_core.py - what Srboli does with a file (or text) another app
# hands it ("Open with Srboli", "Share to Srboli"). Pure Python, no Kivy or
# Android: the Android side is core/android_intent.py.
#
# An incoming item is a dict:
#   {"kind": "file", "path": <local copy>, "name": "song.mp3", "mime": "audio/mpeg"}
#   {"kind": "text", "text": "..."}            (shared text)
# plan(item) -> (route, action): which tool opens it and how.

import os

TEXT_EXT = {"txt", "md", "markdown", "log", "csv", "tsv", "json", "xml", "yml", "yaml",
            "ini", "cfg", "conf", "py", "js", "html", "css", "sh", "srt", "tex"}
MAX_TEXT_BYTES = 2_000_000          # bigger "text" goes to the inspector (hex/preview)


def _ext(name):
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def is_texty(name, mime=""):
    return (mime or "").startswith("text/") or _ext(name) in TEXT_EXT


def plan(item, size=None):
    """(route, action) for an incoming item.
    Shared text -> Text Workbench; text files -> Text Editor; anything else
    -> File Inspector (type, checksums, preview works for every file)."""
    if item.get("kind") == "text":
        return "text_workbench", "set_text"
    name, mime = item.get("name", ""), item.get("mime", "")
    if is_texty(name, mime) and (size is None or size <= MAX_TEXT_BYTES):
        return "text_editor", "open_path"
    return "file_inspector", "inspect"


def safe_name(name, default="shared_file"):
    """A file name that is safe to create in our cache folder."""
    name = os.path.basename((name or "").replace("\\", "/")).strip().strip(".")
    name = "".join(c for c in name if c not in '<>:"|?*\x00' and ord(c) >= 32)
    return name[:120] or default


def unique_path(folder, name):
    """folder/name, or folder/name (2).ext when that exists."""
    base, ext = os.path.splitext(safe_name(name))
    path = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path
