# core/pdf_tools_core.py - merge and split PDFs for the PDF Tools screen.
#
# Uses pypdf (pure Python), imported only when a PDF is actually opened, so the rest of
# the app works without it. Originals are never changed: results go to a "srboli_pdf"
# folder next to the first file, with names that never overwrite anything.
import os
import re

OUT_DIR_NAME = "srboli_pdf"


class PDFError(Exception):
    """A problem worth showing to the user as it is."""


def _pypdf():
    try:
        import pypdf
        return pypdf
    except Exception:
        raise PDFError("PDF support is missing (the pypdf library is not installed).")


def is_pdf(path):
    return path.lower().endswith(".pdf")


def out_dir_for(first_path):
    return os.path.join(os.path.dirname(os.path.abspath(first_path)), OUT_DIR_NAME)


def unique_path(folder, stem, ext=".pdf"):
    os.makedirs(folder, exist_ok=True)
    p = os.path.join(folder, stem + ext)
    n = 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(folder, f"{stem}-{n}{ext}")
    return p


# ---------- page ranges (pure) ----------
def parse_ranges(text, total):
    """'1-3, 5, 8-' -> [0, 1, 2, 4, 7, ...] (0-based, in the order written).
    Raises PDFError for anything outside 1..total or unreadable."""
    if total < 1:
        raise PDFError("The PDF has no pages.")
    out = []
    parts = [p.strip() for p in (text or "").replace(";", ",").split(",") if p.strip()]
    if not parts:
        raise PDFError("Type the pages to keep, for example 1-3, 5, 8-")
    for part in parts:
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m and (m.group(1) or m.group(2)):
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else total
        elif re.fullmatch(r"\d+", part):
            a = b = int(part)
        else:
            raise PDFError(f"Can't read '{part}'. Use numbers and ranges like 1-3, 5, 8-")
        if a < 1 or b > total or a > b:
            raise PDFError(f"Pages {part} are outside 1-{total}.")
        out.extend(range(a - 1, b))
    return out


def chunk_ranges(total, size):
    """[[0..size-1], [size..], ...] - the page groups for 'N pages per file'."""
    size = max(1, int(size))
    return [list(range(i, min(i + size, total))) for i in range(0, total, size)]


# ---------- files ----------
def _open(path, password=""):
    pypdf = _pypdf()
    try:
        r = pypdf.PdfReader(path)
        if r.is_encrypted:
            if not r.decrypt(password or ""):
                raise PDFError(f"{os.path.basename(path)} is password protected.")
        len(r.pages)                       # force the page tree to be read
        return r
    except PDFError:
        raise
    except Exception as e:
        raise PDFError(f"Can't read {os.path.basename(path)}: {e}")


def page_count(path):
    return len(_open(path).pages)


def merge(paths, out_dir):
    """All pages of all files, in order, into one new PDF. Returns (out_path, pages)."""
    if len(paths) < 2:
        raise PDFError("Pick at least two PDFs to merge.")
    pypdf = _pypdf()
    w = pypdf.PdfWriter()
    n = 0
    for p in paths:
        r = _open(p)
        for page in r.pages:
            w.add_page(page)
            n += 1
    out = unique_path(out_dir, "merged")
    with open(out, "wb") as f:
        w.write(f)
    return out, n


def _write_pages(reader, indices, out):
    pypdf = _pypdf()
    w = pypdf.PdfWriter()
    for i in indices:
        w.add_page(reader.pages[i])
    with open(out, "wb") as f:
        w.write(f)


def extract(path, ranges_text, out_dir):
    """The chosen pages as one new PDF. Returns (out_path, pages)."""
    r = _open(path)
    idx = parse_ranges(ranges_text, len(r.pages))
    stem = os.path.splitext(os.path.basename(path))[0]
    out = unique_path(out_dir, f"{stem}-pages")
    _write_pages(r, idx, out)
    return out, len(idx)


def split(path, out_dir, per_file=1):
    """One new PDF per `per_file` pages. Returns the list of output paths."""
    r = _open(path)
    total = len(r.pages)
    stem = os.path.splitext(os.path.basename(path))[0]
    outs = []
    width = len(str(len(chunk_ranges(total, per_file))))
    for n, idx in enumerate(chunk_ranges(total, per_file), 1):
        out = unique_path(out_dir, f"{stem}-part{str(n).zfill(width)}")
        _write_pages(r, idx, out)
        outs.append(out)
    return outs
