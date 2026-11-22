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
    r, action, _label = choices(item, size)[0]
    return r, action


AUDIO_EXT = {"mp3", "wav", "ogg", "flac", "m4a", "aac", "opus", "oga"}

ROUTE_LABELS = {
    "music": ("play", "Play in Music Player"),
    "text_editor": ("open_path", "Open in Text Editor"),
    "text_workbench": ("set_text", "Open in Text Workbench"),
    "file_inspector": ("inspect", "Inspect the file (type, size, checksums)"),
}


def choices(item, size=None):
    """What Srboli can do with an incoming item, best first:
    [(route, action, button text), ...]. The first is what plan() picks."""
    if item.get("kind") == "text":
        routes = ["text_workbench"]
    else:
        name, mime = item.get("name", ""), item.get("mime", "")
        routes = []
        if _ext(name) in AUDIO_EXT or (mime or "").startswith("audio/"):
            routes.append("music")
        if is_texty(name, mime) and (size is None or size <= MAX_TEXT_BYTES):
            routes.append("text_editor")
        routes.append("file_inspector")
    return [(r,) + ROUTE_LABELS[r] for r in routes]


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
