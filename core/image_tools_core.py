# core/image_tools_core.py - batch image work for the Image Tools screen. Needs Pillow.
#
#   process_file: shrink / compress / convert one picture
#   resize_file:  make a picture bigger or smaller (percent, longest side, exact size)
#   combine:      stitch several pictures into one (vertical, horizontal, grid)
# Originals are never changed: results go to a "srboli_images" folder next to the
# first picture, with names that never overwrite anything.
import os

from PIL import Image, ImageFilter, ImageOps

OUT_DIR_NAME = "srboli_images"
FORMATS = {"keep": None, "JPG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}
EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
LAYOUTS = ("vertical", "horizontal", "grid")
MAX_SIDE_LIMIT = 16000            # a result bigger than this would run out of memory
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def is_image(path):
    return path.lower().endswith(IMAGE_EXTS)


def load(path):
    """Open a picture upright (honours the camera's rotation flag)."""
    img = Image.open(path)
    img.load()
    return ImageOps.exif_transpose(img)


def out_dir_for(first_path):
    return os.path.join(os.path.dirname(os.path.abspath(first_path)), OUT_DIR_NAME)


def unique_path(folder, stem, ext):
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, stem + ext)
    n = 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(folder, f"{stem}-{n}{ext}")
    return p


def fit_max_side(img, max_side):
    """Shrink (never enlarge) so the longer side is at most max_side; 0 = keep."""
    if not max_side or max(img.size) <= max_side:
        return img
    k = max_side / max(img.size)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))),
                      Image.LANCZOS)


def save_image(img, path, fmt, quality=85):
    """Save as fmt ('JPEG'/'PNG'/'WEBP'). JPEG has no transparency: flatten on white."""
    if fmt == "JPEG":
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[3])
            img = flat
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img.save(path, "JPEG", quality=quality, optimize=True)
    elif fmt == "PNG":
        img.save(path, "PNG", optimize=True)
    else:
        img.save(path, "WEBP", quality=quality)


def _target_format(src_path, choice):
    f = FORMATS.get(choice)
    if f:
        return f
    e = os.path.splitext(src_path)[1].lower()
    return {".png": "PNG", ".webp": "WEBP"}.get(e, "JPEG")


def process_file(src, out_dir, max_side=0, fmt_choice="keep", quality=85):
    """Returns (out_path, bytes_before, bytes_after)."""
    img = fit_max_side(load(src), max_side)
    fmt = _target_format(src, fmt_choice)
    stem = os.path.splitext(os.path.basename(src))[0]
    out = unique_path(out_dir, stem, EXT[fmt])
    save_image(img, out, fmt, quality)
    return out, os.path.getsize(src), os.path.getsize(out)


# ---- resize / upscale -------------------------------------------------------------
RESIZE_MODES = ("percent", "longest", "exact")
FITS = ("fit", "fill", "stretch")
MAX_PIXELS = 100_000_000          # about 100 megapixels: more would run out of memory


def image_size(path):
    """(width, height) as the picture is shown upright, without decoding all of it."""
    with Image.open(path) as im:
        w, h = im.size
        try:
            if im.getexif().get(274) in (5, 6, 7, 8):
                w, h = h, w
        except Exception:
            pass
    return w, h


def plan_size(w, h, mode, value=100, width=0, height=0, fit="fit"):
    """Output (w, h) for an input of w x h. Raises ValueError for unusable settings.

    percent:  value is a percentage of the original size (200 = twice as big)
    longest:  the longer side becomes `value` px (up or down), ratio kept
    exact:    width x height; fit = inside the box, fill = covers the box (cropped),
              stretch = exactly the box, ratio ignored. One of width/height may be 0
              (then the other decides and the ratio is kept)."""
    if w < 1 or h < 1:
        raise ValueError("The picture has no size.")
    if mode == "percent":
        k = float(value) / 100.0
        if k <= 0:
            raise ValueError("Percent must be more than 0.")
        nw, nh = max(1, round(w * k)), max(1, round(h * k))
    elif mode == "longest":
        if not value or value < 1:
            raise ValueError("Give the length in pixels.")
        k = float(value) / max(w, h)
        nw, nh = max(1, round(w * k)), max(1, round(h * k))
    elif mode == "exact":
        width, height = int(width or 0), int(height or 0)
        if width < 1 and height < 1:
            raise ValueError("Give a width or a height.")
        if width < 1:
            width = max(1, round(w * height / h))
        elif height < 1:
            height = max(1, round(h * width / w))
        if fit == "stretch" or fit == "fill":
            nw, nh = width, height
        else:
            k = min(width / w, height / h)
            nw, nh = max(1, round(w * k)), max(1, round(h * k))
    else:
        raise ValueError("Unknown resize mode.")
    if max(nw, nh) > MAX_SIDE_LIMIT or nw * nh > MAX_PIXELS:
        raise ValueError(f"{nw} x {nh} px is too big for this device "
                         f"(limit {MAX_SIDE_LIMIT} px a side, 100 megapixels).")
    return nw, nh


def resize_image(img, mode, value=100, width=0, height=0, fit="fit", sharpen=0):
    """A resized copy. sharpen 0 (off) to 3 (strong) crispens an enlarged picture; it adds no
    new detail, it only makes edges look cleaner."""
    w, h = img.size
    nw, nh = plan_size(w, h, mode, value, width, height, fit)
    if mode == "exact" and fit == "fill":
        k = max(nw / w, nh / h)
        sw, sh = max(nw, round(w * k)), max(nh, round(h * k))
        out = img.resize((sw, sh), Image.LANCZOS)
        left, top = (sw - nw) // 2, (sh - nh) // 2
        out = out.crop((left, top, left + nw, top + nh))
    elif (nw, nh) == (w, h):
        out = img.copy()
    else:
        out = img.resize((nw, nh), Image.LANCZOS)
    if sharpen and 1 <= int(sharpen) <= 3:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.4, percent=int(sharpen) * 55, threshold=2))
    return out


def describe_resize(w, h, nw, nh):
    k = (nw * nh) / float(w * h)
    kind = "bigger" if k > 1.0001 else "smaller" if k < 0.9999 else "same size"
    return f"{w} x {h} -> {nw} x {nh} px ({kind})"


def resize_file(src, out_dir, mode, value=100, width=0, height=0, fit="fit", sharpen=0,
                fmt_choice="keep", quality=85):
    """Returns (out_path, bytes_before, bytes_after, (new_w, new_h))."""
    img = resize_image(load(src), mode, value, width, height, fit, sharpen)
    fmt = _target_format(src, fmt_choice)
    stem = os.path.splitext(os.path.basename(src))[0]
    out = unique_path(out_dir, f"{stem}-{img.width}x{img.height}", EXT[fmt])
    save_image(img, out, fmt, quality)
    return out, os.path.getsize(src), os.path.getsize(out), img.size


def _parse_bg(bg):
    return tuple(bg) if bg else (255, 255, 255)


def combine(images, layout="vertical", cols=2, gap=0, bg=(255, 255, 255), size=1600):
    """One picture made of all `images`.
    vertical:   all scaled to the same width (`size`), stacked
    horizontal: all scaled to the same height (`size`), side by side
    grid:       `cols` columns of equal square-ish cells `size` px wide, pictures fitted inside
    """
    if not images:
        raise ValueError("No pictures to combine.")
    if layout not in LAYOUTS:
        raise ValueError("Unknown layout.")
    size = max(16, min(int(size), MAX_SIDE_LIMIT))
    gap = max(0, int(gap))
    bg = _parse_bg(bg)
    imgs = [i.convert("RGBA") if i.mode in ("P", "LA") else i for i in images]

    def check(w, h):
        if max(w, h) > MAX_SIDE_LIMIT:
            raise ValueError(f"The result would be {w} x {h} px, too big. "
                             "Use fewer pictures or a smaller size.")

    if layout == "vertical":
        scaled = [i.resize((size, max(1, round(i.height * size / i.width))), Image.LANCZOS)
                  for i in imgs]
        w, h = size, sum(i.height for i in scaled) + gap * (len(scaled) - 1)
        check(w, h)
        canvas = Image.new("RGB", (w, h), bg)
        y = 0
        for i in scaled:
            _paste(canvas, i, 0, y)
            y += i.height + gap
    elif layout == "horizontal":
        scaled = [i.resize((max(1, round(i.width * size / i.height)), size), Image.LANCZOS)
                  for i in imgs]
        w, h = sum(i.width for i in scaled) + gap * (len(scaled) - 1), size
        check(w, h)
        canvas = Image.new("RGB", (w, h), bg)
        x = 0
        for i in scaled:
            _paste(canvas, i, x, 0)
            x += i.width + gap
    else:
        cols = max(1, min(int(cols), len(imgs)))
        rows = -(-len(imgs) // cols)
        cell = max(16, size // cols)
        w, h = cols * cell + gap * (cols - 1), rows * cell + gap * (rows - 1)
        check(w, h)
        canvas = Image.new("RGB", (w, h), bg)
        for n, i in enumerate(imgs):
            fitted = ImageOps.contain(i, (cell, cell), Image.LANCZOS)
            r, c = divmod(n, cols)
            _paste(canvas, fitted, c * (cell + gap) + (cell - fitted.width) // 2,
                   r * (cell + gap) + (cell - fitted.height) // 2)
    return canvas


def _paste(canvas, img, x, y):
    if img.mode == "RGBA":
        canvas.paste(img, (x, y), img)
    else:
        canvas.paste(img.convert("RGB"), (x, y))


def combine_files(paths, out_dir, layout="vertical", cols=2, gap=0, bg=(255, 255, 255),
                  size=1600, fmt_choice="JPG", quality=88):
    """Load, combine and save. Returns (out_path, bytes_after)."""
    images = [load(p) for p in paths]
    result = combine(images, layout, cols, gap, bg, size)
    fmt = FORMATS.get(fmt_choice) or "JPEG"
    out = unique_path(out_dir, "combined", EXT[fmt])
    save_image(result, out, fmt, quality)
    return out, os.path.getsize(out)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
