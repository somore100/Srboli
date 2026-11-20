# core/folder_icons_core.py - coloured folders and folders with a picture.
# No Kivy. Makes a folder icon (a flat coloured folder, or a folder filled with
# one of your pictures) and tells the file manager to show it for a folder.
#
#   Linux    GNOME Files / Nemo / Caja: gio metadata::custom-icon
#            Dolphin / Thunar / others: a ".directory" file with Icon=
#   Windows  desktop.ini + an .ico, folder marked read-only so Explorer reads it
#   macOS    not supported (needs Apple's own icon API)
#
# Only the folder's own icon setting is touched; files inside are never
# changed. reset() removes exactly what apply() added. The icon images are kept
# in <user data>/Srboli/folder_icons (not the removable app data folder, so
# "Clear data" does not turn every folder back to plain).
import hashlib
import os
import shutil
import subprocess
import sys

MARK = "# made by Srboli"
SIZE = 256

COLORS = [
    ("Red", "#e5484d"), ("Orange", "#f76b15"), ("Yellow", "#f5c518"),
    ("Green", "#30a46c"), ("Teal", "#12a594"), ("Blue", "#3e63dd"),
    ("Purple", "#8e4ec6"), ("Pink", "#d6409f"), ("Brown", "#a2714b"),
    ("Grey", "#889096"), ("Black", "#2b2f33"), ("White", "#e8eaed"),
]


class IconError(Exception):
    pass


def icons_dir():
    import app_data
    p = os.path.join(app_data._user_data_root(), "folder_icons")
    os.makedirs(p, exist_ok=True)
    return p


def _rgb(hexs):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _shade(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def _folder_mask(size):
    """The silhouette of a folder (tab on top-left) as an 'L' mask."""
    from PIL import Image, ImageDraw
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    s = size / 256.0
    r = int(22 * s)
    d.rounded_rectangle((16 * s, 52 * s, 120 * s, 120 * s), r, fill=255)   # tab
    d.rounded_rectangle((16 * s, 76 * s, 240 * s, 220 * s), r, fill=255)   # body
    return m


def make_color_icon(color, dest, size=SIZE):
    """Flat coloured folder PNG. `color` is '#rrggbb'. Returns dest."""
    from PIL import Image, ImageDraw
    try:
        rgb = _rgb(color)
    except (ValueError, TypeError, IndexError):
        raise IconError(f"'{color}' is not a colour like #3e63dd")
    s = size / 256.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(22 * s)
    d.rounded_rectangle((16 * s, 52 * s, 120 * s, 120 * s), r, fill=_shade(rgb, 0.78))
    d.rounded_rectangle((16 * s, 76 * s, 240 * s, 220 * s), r, fill=_shade(rgb, 0.85))
    d.rounded_rectangle((16 * s, 100 * s, 240 * s, 220 * s), r, fill=rgb)  # front
    d.rectangle((16 * s, 100 * s, 240 * s, 130 * s), fill=rgb)
    d.line((30 * s, 106 * s, 226 * s, 106 * s), fill=_shade(rgb, 1.25), width=max(1, int(3 * s)))
    img.save(dest, "PNG")
    return dest


def make_image_icon(src, dest, size=SIZE):
    """A folder shape filled with the middle of the picture `src`."""
    from PIL import Image, ImageOps
    try:
        im = Image.open(src)
        im.load()
    except Exception as e:
        raise IconError(f"Can't read that picture: {e}")
    im = ImageOps.exif_transpose(im).convert("RGBA")
    im = ImageOps.fit(im, (size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), _folder_mask(size))
    out.save(dest, "PNG")
    return dest


def _icon_path(key, ext="png"):
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return os.path.join(icons_dir(), f"{h}.{ext}")


def color_icon(color):
    """Cached PNG for a colour."""
    p = _icon_path("c:" + color.lower())
    if not os.path.exists(p):
        make_color_icon(color, p)
    return p


def image_icon(src):
    """PNG for a picture (a copy lives in the icons folder)."""
    try:
        st = os.stat(src)
        key = f"i:{os.path.abspath(src)}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        raise IconError("That picture isn't there.")
    p = _icon_path(key)
    if not os.path.exists(p):
        make_image_icon(src, p)
    return p


def to_ico(png, dest):
    from PIL import Image
    Image.open(png).save(dest, format="ICO",
                         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return dest


def _run(runner, cmd):
    try:
        return runner(cmd, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None


def _plat(platform=None):
    p = platform or sys.platform
    return "windows" if p.startswith("win") else "mac" if p == "darwin" else "linux"


def supported(platform=None):
    return _plat(platform) in ("linux", "windows")


def _check_folder(folder):
    if not os.path.isdir(folder):
        raise IconError("That isn't a folder.")
    if not os.access(folder, os.W_OK):
        raise IconError("No permission to change that folder.")


def apply(folder, png, platform=None, runner=None):
    """Show `png` as the icon of `folder`. Returns a list of what was done."""
    runner = runner or subprocess.run
    plat = _plat(platform)
    _check_folder(folder)
    folder = os.path.abspath(folder)
    done = []
    if plat == "linux":
        dirfile = os.path.join(folder, ".directory")
        if not os.path.exists(dirfile) or MARK in open(dirfile, errors="replace").read():
            with open(dirfile, "w", encoding="utf-8") as f:
                f.write(f"[Desktop Entry]\nIcon={png}\n{MARK}\n")
            done.append("Dolphin / Thunar (.directory)")
        else:
            done.append("kept your own .directory file")
        if shutil.which("gio") or runner is not subprocess.run:
            r = _run(runner, ["gio", "set", "-t", "string", folder,
                              "metadata::custom-icon", "file://" + png])
            if r is not None and getattr(r, "returncode", 0) == 0:
                done.append("GNOME Files / Nemo / Caja (gio)")
        return done
    if plat == "windows":
        ico = to_ico(png, os.path.splitext(png)[0] + ".ico")
        ini = os.path.join(folder, "desktop.ini")
        if os.path.exists(ini):
            _run(runner, ["attrib", "-s", "-h", ini])
        with open(ini, "w", encoding="utf-8") as f:
            f.write(f"[.ShellClassInfo]\nIconResource={ico},0\n;{MARK}\n")
        _run(runner, ["attrib", "+s", "+h", ini])
        _run(runner, ["attrib", "+r", folder])
        return ["Explorer (desktop.ini)"]
    raise IconError("Folder icons aren't supported on macOS yet.")


def reset(folder, platform=None, runner=None):
    """Back to the normal icon. Only removes what apply() added."""
    runner = runner or subprocess.run
    plat = _plat(platform)
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise IconError("That isn't a folder.")
    removed = False
    if plat == "linux":
        dirfile = os.path.join(folder, ".directory")
        if os.path.isfile(dirfile) and MARK in open(dirfile, errors="replace").read():
            os.remove(dirfile)
            removed = True
        if shutil.which("gio") or runner is not subprocess.run:
            _run(runner, ["gio", "set", "-t", "unset", folder, "metadata::custom-icon"])
        return removed
    if plat == "windows":
        ini = os.path.join(folder, "desktop.ini")
        if os.path.isfile(ini) and MARK in open(ini, errors="replace").read():
            _run(runner, ["attrib", "-s", "-h", ini])
            os.remove(ini)
            _run(runner, ["attrib", "-r", folder])
            removed = True
        return removed
    return False


def current(folder):
    """True if Srboli set this folder's icon (Linux .directory / Windows ini)."""
    for name in (".directory", "desktop.ini"):
        p = os.path.join(folder, name)
        try:
            if os.path.isfile(p) and MARK in open(p, errors="replace").read():
                return True
        except OSError:
            pass
    return False


def targets(folder, include_sub=False):
    """The folder, plus its direct subfolders (not hidden ones) if asked."""
    out = [folder]
    if include_sub:
        try:
            for n in sorted(os.listdir(folder)):
                p = os.path.join(folder, n)
                if os.path.isdir(p) and not n.startswith(".") and not os.path.islink(p):
                    out.append(p)
        except OSError:
            pass
    return out
