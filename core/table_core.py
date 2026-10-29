# core/table_core.py - the Full Editor's coloured tables, Kivy-free.
#
# A document holds a list of named tables:
#   {"name": "Timetable",
#    "cells": [[{"t": "Mon", "bg": "#3DDC84", "fg": ""}, ...], ...]}
# "t" is the cell text; "bg" / "fg" are "#RRGGBB" or "" for the default look.
# cells is always a full rectangle (every row has the same number of cells).
#
# Besides colours and add/remove of rows and columns, a cell can be given a
# formula by the editor (=SUM(A1:A5), =AVG, =COUNT, =MAX, =MIN or plain
# arithmetic that may use cell references like =A1*2+B3); only the result is
# stored. Nothing here calls eval().

import ast
import html as _html
import operator
import re

MAX_ROWS = 100
MAX_COLS = 26                  # column headers are single letters A-Z

_COLOR_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def norm_color(value):
    """'#RGB' / 'rrggbb' / '#RRGGBB' -> '#RRGGBB'; anything else -> ''."""
    m = _COLOR_RE.match(str(value or "").strip())
    if not m:
        return ""
    h = m.group(1).upper()
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return "#" + h


def col_letter(c):
    return chr(65 + c)


def blank_cell():
    return {"t": "", "bg": "", "fg": ""}


def blank_table(name="Table 1", rows=8, cols=6):
    rows = max(1, min(rows, MAX_ROWS))
    cols = max(1, min(cols, MAX_COLS))
    return {"name": name,
            "cells": [[blank_cell() for _ in range(cols)] for _ in range(rows)]}


def size(table):
    return len(table["cells"]), len(table["cells"][0])


def normalize(raw):
    """Clean tables loaded from a file: valid, rectangular, unique names."""
    out = []
    for t in raw if isinstance(raw, list) else []:
        if not isinstance(t, dict) or not isinstance(t.get("cells"), list):
            continue
        rows = []
        for row in t["cells"][:MAX_ROWS]:
            if not isinstance(row, list):
                continue
            cells = []
            for c in row[:MAX_COLS]:
                if isinstance(c, dict):
                    cells.append({"t": str(c.get("t", "")),
                                  "bg": norm_color(c.get("bg")),
                                  "fg": norm_color(c.get("fg"))})
                else:
                    cells.append({"t": "" if c is None else str(c),
                                  "bg": "", "fg": ""})
            rows.append(cells)
        if not rows or not max(len(r) for r in rows):
            continue
        width = max(len(r) for r in rows)
        for r in rows:
            r.extend(blank_cell() for _ in range(width - len(r)))
        out.append({"name": unique_name(out, str(t.get("name") or "Table")),
                    "cells": rows})
    return out


def from_sheet(sheet):
    """Old documents had one plain grid of strings ('sheet'). Return it as a
    table trimmed to the used area, or None when it was empty."""
    rows = [[("" if v is None else str(v)) for v in r]
            for r in sheet if isinstance(r, list)] if isinstance(sheet, list) else []
    used_r = [i for i, r in enumerate(rows) if any(c.strip() for c in r)]
    used_c = [j for r in rows for j, c in enumerate(r) if c.strip()]
    if not used_r:
        return None
    nr, nc = max(used_r) + 1, max(used_c) + 1
    return normalize([{"name": "Sheet 1",
                       "cells": [r[:nc] + [""] * (nc - len(r[:nc]))
                                 for r in rows[:nr]]}])[0]


# ── names ────────────────────────────────────────────────────────────────────
def unique_name(tables, wanted, skip=None):
    """`wanted`, or `wanted 2`, `wanted 3`... if another table has the name."""
    base = re.sub(r"[\[\]\n]", "", wanted).strip() or "Table"
    taken = {t["name"] for i, t in enumerate(tables) if i != skip}
    name, n = base, 2
    while name in taken:
        name = f"{base} {n}"
        n += 1
    return name


def find(tables, name):
    for t in tables:
        if t["name"] == name:
            return t
    return None


# ── structure (each returns False when it can't) ─────────────────────────────
def add_row(table, after=None):
    rows, cols = size(table)
    if rows >= MAX_ROWS:
        return False
    at = rows if after is None else max(0, min(after + 1, rows))
    table["cells"].insert(at, [blank_cell() for _ in range(cols)])
    return True


def delete_row(table, r):
    if size(table)[0] <= 1 or not 0 <= r < size(table)[0]:
        return False
    del table["cells"][r]
    return True


def add_col(table, after=None):
    rows, cols = size(table)
    if cols >= MAX_COLS:
        return False
    at = cols if after is None else max(0, min(after + 1, cols))
    for row in table["cells"]:
        row.insert(at, blank_cell())
    return True


def delete_col(table, c):
    if size(table)[1] <= 1 or not 0 <= c < size(table)[1]:
        return False
    for row in table["cells"]:
        del row[c]
    return True


def cells_in_scope(table, r, c, scope):
    """(row, col) pairs for scope 'cell' | 'row' | 'col' | 'all'."""
    rows, cols = size(table)
    if scope == "row":
        return [(r, j) for j in range(cols)]
    if scope == "col":
        return [(i, c) for i in range(rows)]
    if scope == "all":
        return [(i, j) for i in range(rows) for j in range(cols)]
    return [(r, c)]


def set_color(table, r, c, key, value, scope="cell"):
    """Set the "bg" or "fg" colour ("" clears it). Returns the cells changed."""
    if key not in ("bg", "fg"):
        raise ValueError(key)
    value = norm_color(value)
    changed = []
    for i, j in cells_in_scope(table, r, c, scope):
        if table["cells"][i][j][key] != value:
            table["cells"][i][j][key] = value
            changed.append((i, j))
    return changed


# ── formulas ─────────────────────────────────────────────────────────────────
_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv}


def safe_arith(expr):
    """Evaluate + - * / and parentheses on plain numbers. No eval()."""
    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            return _BINOPS[type(n.op)](walk(n.left), walk(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
            v = walk(n.operand)
            return v if isinstance(n.op, ast.UAdd) else -v
        raise ValueError("unsupported expression")
    return walk(ast.parse(expr.strip(), mode="eval"))


_REF_RE = re.compile(r"^([A-Z])(\d+)$")
_RANGE_RE = re.compile(r"^([A-Z])(\d+):([A-Z])(\d+)$")


def _number(table, r, c):
    """Cell value as a float, or None when empty / not a number."""
    rows, cols = size(table)
    if not (0 <= r < rows and 0 <= c < cols):
        return None
    try:
        return float(table["cells"][r][c]["t"])
    except ValueError:
        return None


def range_values(table, ref):
    """Numbers in an 'A1:B3' range (empty / text cells are skipped)."""
    m = _RANGE_RE.match(ref.strip().upper())
    if not m:
        raise ValueError(f"bad range {ref}")
    c1, r1 = ord(m.group(1)) - 65, int(m.group(2)) - 1
    c2, r2 = ord(m.group(3)) - 65, int(m.group(4)) - 1
    vals = []
    for r in range(min(r1, r2), max(r1, r2) + 1):
        for c in range(min(c1, c2), max(c1, c2) + 1):
            v = _number(table, r, c)
            if v is not None:
                vals.append(v)
    return vals


def eval_formula(table, expr):
    """Value of a formula (without the leading '=')."""
    e = expr.strip().upper()
    m = re.fullmatch(r"(SUM|AVG|AVERAGE|COUNT|MAX|MIN)\((.+)\)", e)
    if m:
        fn, vals = m.group(1), range_values(table, m.group(2))
        if fn == "SUM":
            return sum(vals)
        if fn in ("AVG", "AVERAGE"):
            return sum(vals) / len(vals) if vals else 0
        if fn == "COUNT":
            return len(vals)
        if not vals:
            return 0
        return max(vals) if fn == "MAX" else min(vals)

    def ref(mm):
        v = _number(table, int(mm.group(2)) - 1, ord(mm.group(1)) - 65)
        return repr(v if v is not None else 0)
    return safe_arith(re.sub(r"\b([A-Z])(\d+)\b", ref, e))


def format_number(v):
    """3.0 -> '3', 0.1+0.2 -> '0.3' (so results look like a spreadsheet's)."""
    if isinstance(v, float):
        v = round(v, 10)
        if v == int(v):
            return str(int(v))
    return str(v)


# ── output ───────────────────────────────────────────────────────────────────
def to_markdown(table):
    """A plain Markdown table (colours can't be expressed); first row = header."""
    def cell(c):
        return c["t"].replace("|", "\\|").replace("\n", " ") or " "
    rows = table["cells"]
    lines = ["| " + " | ".join(cell(c) for c in rows[0]) + " |",
             "|" + "|".join(" --- " for _ in rows[0]) + "|"]
    lines += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def to_html(table):
    esc = _html.escape
    out = ["<table border='1' cellpadding='6' style='border-collapse:collapse'>"]
    for r in table["cells"]:
        tds = []
        for c in r:
            style = ""
            if c["bg"]:
                style += f"background:{c['bg']};"
            if c["fg"]:
                style += f"color:{c['fg']};"
            tds.append(f'<td style="{style}">{esc(c["t"]).replace(chr(10), "<br>")}</td>')
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</table>")
    return "".join(out)
