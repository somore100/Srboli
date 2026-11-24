# core/studio_data.py - Srboli Studio data objects: tables, charts, images. No Kivy.
# Works on plain object dicts so studio_core can use it without a circular import.
#   table: o["cells"] = [[str]]  (text starting with "=" is a formula: =SUM(B2:B4), =B2*C2 ...)
#   chart: reads a table (o["source"] = that table object's id) or its own o["data"]
#   image: o["asset"] = file name of a picture stored in the document's assets
import csv
import io
import math
import os
import re
import struct

from core import table_core as tc

MAX_ROWS = tc.MAX_ROWS
MAX_COLS = tc.MAX_COLS
CHART_KINDS = ("bar", "line", "pie")
MAX_CATEGORIES = 60
MAX_SERIES = 8
CHART_COLORS = ["#4A7BD0", "#E0833A", "#4FA56B", "#C7515B", "#8D6BC8", "#3FA7B5", "#C9A227", "#7A7F87"]
MAX_ASSET = 20 * 1024 * 1024
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif")


def default_cells():
    return [["Category", "2024", "2025"], ["North", "12", "15"], ["South", "9", "11"],
            ["West", "14", "10"]]


def default_data():
    return {"labels": ["A", "B", "C", "D"], "names": ["Series 1"], "series": [[4.0, 7.0, 3.0, 6.0]]}


def clean_cells(raw):
    """Rectangular list of str, within the size limits (never empty)."""
    rows = []
    for r in (raw if isinstance(raw, list) else [])[:MAX_ROWS]:
        if isinstance(r, list):
            rows.append(["" if c is None else str(c)[:500] for c in r[:MAX_COLS]])
    width = max([len(r) for r in rows] or [0])
    if not rows or width == 0:
        return default_cells()
    return [r + [""] * (width - len(r)) for r in rows]


def col_name(c):
    return chr(65 + c)


def parse_col(text):
    t = str(text).strip().upper()
    if len(t) == 1 and "A" <= t <= "Z":
        return ord(t) - 65
    raise ValueError("Use a column letter like B.")


def num(text):
    try:
        v = float(str(text).strip().replace(",", "."))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------- tables
def display_grid(cells):
    """What the table shows: [[str]] with formulas worked out (errors show as #ERR)."""
    rows, cols = len(cells), len(cells[0])
    tab = {"cells": [[{"t": "" if str(c).startswith("=") else str(c)} for c in r] for r in cells]}
    formulas = [(r, c) for r in range(rows) for c in range(cols) if str(cells[r][c]).startswith("=")]
    bad = set()
    for _ in range(6):
        changed = False
        for r, c in formulas:
            try:
                v = tc.format_number(tc.eval_formula(tab, cells[r][c][1:]))
                bad.discard((r, c))
            except (ValueError, ZeroDivisionError, OverflowError, KeyError, SyntaxError):
                v = "#ERR"
                bad.add((r, c))
            if tab["cells"][r][c]["t"] != v:
                tab["cells"][r][c]["t"] = v
                changed = True
        if not changed:
            break
    return [[tab["cells"][r][c]["t"] for c in range(cols)] for r in range(rows)]


def visible_rows(o):
    """Row indexes that show: the header row always, the rest passing the filter."""
    n = len(o["cells"])
    start = 1 if o["header"] else 0
    keep = list(range(n))
    col, text = o.get("fcol", -1), str(o.get("ftext", "")).strip().lower()
    if 0 <= col < len(o["cells"][0]) and text:
        grid = display_grid(o["cells"])
        keep = [r for r in keep if r < start or text in grid[r][col].lower()]
    return keep


def _sort_key(v):
    n = num(v)
    return (0, n, "") if n is not None else (1, 0.0, v.lower())


def sort_rows(o, col, desc=False):
    """Sort the data rows by a column (numbers by value, text alphabetically). The header row
    stays on top. Formulas keep their text, so avoid sorting formulas that point at other rows."""
    cells = o["cells"]
    if not 0 <= col < len(cells[0]):
        return False
    start = 1 if o["header"] else 0
    grid = display_grid(cells)
    order = sorted(range(start, len(cells)), key=lambda r: _sort_key(grid[r][col]), reverse=desc)
    o["cells"] = cells[:start] + [cells[r] for r in order]
    return True


def add_row(o, after=None):
    n = len(o["cells"])
    if n >= MAX_ROWS:
        return False
    i = n if after is None else max(0, min(after + 1, n))
    o["cells"].insert(i, [""] * len(o["cells"][0]))
    o["h"] = o["h"] * (n + 1) / n
    return True


def delete_row(o, r):
    n = len(o["cells"])
    if n <= 1 or not 0 <= r < n:
        return False
    del o["cells"][r]
    o["h"] = max(4.0, o["h"] * (n - 1) / n)
    return True


def add_col(o, after=None):
    n = len(o["cells"][0])
    if n >= MAX_COLS:
        return False
    i = n if after is None else max(0, min(after + 1, n))
    for r in o["cells"]:
        r.insert(i, "")
    o["w"] = o["w"] * (n + 1) / n
    return True


def delete_col(o, c):
    n = len(o["cells"][0])
    if n <= 1 or not 0 <= c < n:
        return False
    for r in o["cells"]:
        del r[c]
    o["w"] = max(4.0, o["w"] * (n - 1) / n)
    return True


def set_cell(o, r, c, text):
    if not (0 <= r < len(o["cells"]) and 0 <= c < len(o["cells"][0])):
        return False
    o["cells"][r][c] = str(text)[:500]
    return True


def parse_table_text(text):
    """Turn pasted text (tab, semicolon or comma separated, or a Markdown table) into cells."""
    text = str(text).strip("\n")
    if not text.strip():
        raise ValueError("There is no text to read.")
    lines = [l for l in text.split("\n") if l.strip()]
    if sum(1 for l in lines if l.strip().startswith("|")) >= max(1, len(lines) // 2):
        rows = []
        for l in lines:
            l = l.strip().strip("|")
            parts = [p.strip() for p in l.split("|")]
            if all(re.fullmatch(r":?-{2,}:?", p) for p in parts if p) and any(parts):
                continue
            rows.append(parts)
    else:
        first = lines[0]
        delim = max(("\t", ";", ","), key=lambda d: first.count(d))
        if first.count(delim) == 0:
            delim = "\t"
        rows = [r for r in csv.reader(io.StringIO("\n".join(lines)), delimiter=delim)]
    cells = clean_cells(rows)
    if len(rows) > MAX_ROWS or max(len(r) for r in rows) > MAX_COLS:
        raise ValueError(f"Tables can have at most {MAX_ROWS} rows and {MAX_COLS} columns.")
    return cells


def to_csv(cells, display=True):
    grid = display_grid(cells) if display else cells
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(grid)
    return out.getvalue()


# ---------------------------------------------------------------- charts
def clean_chart_data(raw):
    try:
        labels = [str(x)[:60] for x in raw["labels"]][:MAX_CATEGORIES]
        names = [str(x)[:60] for x in raw["names"]][:MAX_SERIES]
        series = []
        for s in raw["series"][:MAX_SERIES]:
            vals = [float(v) if isinstance(v, (int, float)) and math.isfinite(v) else 0.0 for v in s][:len(labels)]
            series.append(vals + [0.0] * (len(labels) - len(vals)))
        names = (names + [f"Series {i + 1}" for i in range(len(names), len(series))])[:len(series)]
        if labels and series:
            return {"labels": labels, "names": names, "series": series}
    except (TypeError, KeyError, ValueError):
        pass
    return default_data()


def chart_data(o, table=None):
    """{"labels", "names", "series"} for a chart: from its linked table when there is one
    (header row gives series names, the filter applies), else its own data."""
    if table is None or table.get("type") != "table":
        return clean_chart_data(o.get("data"))
    grid = display_grid(table["cells"])
    ncols = len(grid[0])
    lc = min(max(o.get("label_col", 0), 0), ncols - 1)
    vcs = [c for c in o.get("value_cols", [1]) if 0 <= c < ncols and c != lc][:MAX_SERIES]
    if not vcs:
        vcs = [c for c in range(ncols) if c != lc][:1]
    rows = [r for r in visible_rows(table) if not (table["header"] and r == 0)][:MAX_CATEGORIES]
    if not rows or not vcs:
        return clean_chart_data(o.get("data"))
    names = [(grid[0][c] if table["header"] and grid[0][c] else f"Series {k + 1}")
             for k, c in enumerate(vcs)]
    return {"labels": [grid[r][lc] for r in rows], "names": names,
            "series": [[num(grid[r][c]) or 0.0 for r in rows] for c in vcs]}


def nice_ticks(lo, hi, n=5):
    """Round axis values covering [lo, hi]."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.floor(lo / step + 1e-9) * step
    out, v = [], first
    while v < hi + step * 0.999 and len(out) < 40:
        out.append(round(v, 10))
        v += step
    if out[-1] < hi - 1e-9:
        out.append(round(out[-1] + step, 10))
    return out


def fmt_axis(v):
    return tc.format_number(round(v, 6)) if abs(v) < 1e6 else f"{v:.3g}"


def chart_layout(o, data, w, h):
    """Everything needed to paint a chart, in the chart's own box (origin top-left, y down)."""
    kind = o["kind"]
    names, labels, series = data["names"], data["labels"], data["series"]
    nser, ncat = len(series), len(labels)
    title_h = 30.0 if o.get("title") else 6.0
    legend_w = min(130.0, w * 0.3) if o.get("legend") and (nser > 1 or kind == "pie") else 0.0
    left = 6.0 if kind == "pie" else 48.0
    px, py = left, title_h + 4
    pw = max(w - px - 10 - legend_w, 10.0)
    ph = max(h - py - (6.0 if kind == "pie" else 30.0), 10.0)
    out = {"kind": kind, "title_h": title_h, "plot": (px, py, pw, ph), "ticks": [], "cats": [],
           "bars": [], "lines": [], "slices": [], "legend": []}
    if kind == "pie":
        vals = [max(v, 0.0) for v in series[0]]
        total = sum(vals)
        a = 0.0
        if total > 0:
            for i, v in enumerate(vals):
                if v > 0:
                    out["slices"].append((a, v / total * 360.0, i))
                    a += v / total * 360.0
        out["pie"] = (px + pw / 2, py + ph / 2, min(pw, ph) / 2 * 0.92)
        items = [(lab, i) for i, lab in enumerate(labels)]
    else:
        allv = [v for s in series for v in s]
        lo, hi = min(0.0, min(allv)), max(0.0, max(allv))
        ticks = nice_ticks(lo, hi)
        t0, t1 = ticks[0], ticks[-1]

        def Y(v):
            return py + ph - (v - t0) / (t1 - t0) * ph
        out["ticks"] = [(t, Y(t)) for t in ticks]
        out["zero_y"] = Y(0.0)
        gw = pw / ncat
        for i, lab in enumerate(labels):
            out["cats"].append((lab, px + (i + 0.5) * gw))
        if kind == "bar":
            bw = gw * 0.72 / nser
            for si, s in enumerate(series):
                for i, v in enumerate(s):
                    x = px + i * gw + gw * 0.14 + si * bw
                    y, y0 = Y(v), Y(0.0)
                    out["bars"].append((x, min(y, y0), bw, abs(y - y0), si))
        else:
            for s in series:
                out["lines"].append([(px + (i + 0.5) * gw, Y(v)) for i, v in enumerate(s)])
        items = [(n, i) for i, n in enumerate(names)]
    if legend_w:
        lx = w - legend_w
        for k, (name, ci) in enumerate(items[:12]):
            out["legend"].append((name, ci % len(CHART_COLORS), lx, py + k * 18.0))
    return out


# ---------------------------------------------------------------- images
def image_size(data):
    """(width, height) of a PNG, JPEG or GIF from its header, or None for anything else."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                m = data[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                ln = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + ln
    except struct.error:
        pass
    return None


def safe_asset_name(name, taken=()):
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(str(name))).strip("._") or "image"
    stem, ext = os.path.splitext(base)
    if ext.lower() not in IMAGE_EXT:
        ext = ".png"
    stem = stem[:60] or "image"
    cand, n = stem + ext.lower(), 2
    while cand in taken:
        cand = f"{stem}_{n}{ext.lower()}"
        n += 1
    return cand
