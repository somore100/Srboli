# core/export_core.py - copy logs or data into one zip in a folder the user can
# reach (on a phone: the Download folder), because the app's own folders are
# private to the app there. Standard library only; never changes the source.

import os
import time
import zipfile


def export_dir():
    """Where exports go: Download on a phone, Downloads/home on a computer."""
    from core.android_storage import shared_storage_root
    root = shared_storage_root()
    for name in ("Download", "Downloads"):
        p = os.path.join(root, name)
        if os.path.isdir(p):
            return p
    return root


def zip_folders(folders, dest_dir, prefix):
    """Zip every file under `folders` (a list) into dest_dir/<prefix>_<time>.zip.
    Returns (zip_path, file_count). Raises OSError if nothing can be written or
    there is nothing to export."""
    files = []
    for f in folders:
        for base, _d, names in os.walk(f):
            for n in names:
                files.append((os.path.join(base, n), f))
    if not files:
        raise OSError("There is nothing to export yet.")
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.zip")
    seen = set()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, root in files:
            arc = os.path.join(os.path.basename(root), os.path.relpath(path, root))
            if arc in seen:
                continue
            seen.add(arc)
            try:
                z.write(path, arc)
            except OSError:
                pass
    return out, len(seen)
