"""Never-clobber helpers for screens that change the user's own files.

Gallery Sorter, Text Editor and Metadata used to move, rename and write files
directly (shutil.move / os.rename / open("w")), which silently replaces an
existing file or truncates the original when a write fails. Everything here
refuses to overwrite and writes through a temporary name.  No Kivy.
"""
import os

from core import file_safety


def unique_path(folder, filename):
    """folder/filename, or 'name (1).ext', 'name (2).ext'... — never an existing path."""
    base, ext = os.path.splitext(filename)
    candidate, n = os.path.join(folder, filename), 1
    while os.path.lexists(candidate):
        candidate = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return candidate


def move_keep_both(src, dst_folder):
    """Move src into dst_folder under a name nobody else has. Returns the new path."""
    os.makedirs(dst_folder, exist_ok=True)
    while True:
        dst = unique_path(dst_folder, os.path.basename(src))
        try:
            file_safety.safe_move(src, dst)
            return dst
        except FileExistsError:
            continue                      # lost a race for the name: pick the next


def check_new_name(name):
    """None if `name` is an acceptable bare file name, else a message."""
    name = (name or "").strip()
    if not name:
        return "Type a name first."
    if name in (".", "..") or any(c in name for c in ("/", "\\", "\0")):
        return "A name can't contain / or \\."
    return None


def rename_no_overwrite(old, new_name_no_ext):
    """Rename old (keeping its extension). Raises FileExistsError / ValueError
    instead of replacing another file. Returns the new path."""
    bad = check_new_name(new_name_no_ext)
    if bad:
        raise ValueError(bad)
    ext = os.path.splitext(old)[1]
    new = os.path.join(os.path.dirname(old), new_name_no_ext.strip() + ext)
    if os.path.lexists(new) and not _same_file(old, new):
        raise FileExistsError(f"'{os.path.basename(new)}' already exists.")
    os.rename(old, new)
    return new


def _same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def write_text_atomic(path, text, encoding="utf-8"):
    """Write text via a temp file + os.replace, so a failed write keeps the old file."""
    folder = os.path.dirname(path) or "."
    tmp = os.path.join(folder, f".{os.path.basename(path)}.srboli-part")
    try:
        with open(tmp, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_image_atomic(img, path, format_hint=None, **kwargs):
    """img.save() through a temp file. JPEGs keep their quality tables,
    subsampling and ICC profile unless the caller overrides them.
    format_hint names the format for images built from pixels (no .format)."""
    fmt = (format_hint or img.format
           or os.path.splitext(path)[1].lstrip(".").upper() or "PNG")
    fmt = {"JPG": "JPEG"}.get(fmt.upper(), fmt.upper())
    opts = dict(kwargs)
    if fmt == "JPEG":
        if "quality" not in opts and getattr(img, "format", None) == "JPEG":
            opts["quality"] = "keep"
            opts.setdefault("subsampling", "keep")
        icc = img.info.get("icc_profile")
        if icc and "icc_profile" not in opts:
            opts["icc_profile"] = icc
    elif fmt == "PNG":
        icc = img.info.get("icc_profile")
        if icc and "icc_profile" not in opts:
            opts["icc_profile"] = icc
    folder = os.path.dirname(path) or "."
    tmp = os.path.join(folder, f".{os.path.basename(path)}.srboli-part")
    try:
        img.save(tmp, format=fmt, **opts)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
