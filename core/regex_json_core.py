# core/regex_json_core.py - the logic of the Regex / JSON screen. Pure Python.
import json
import re

MAX_MATCHES = 200
MAX_ROWS = 600

FLAGS = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}


def _flags(letters):
    f = 0
    for ch in letters or "":
        f |= FLAGS.get(ch, 0)
    return f


# ---------------- regex ----------------
def compile_pattern(pattern, flags=""):
    """(compiled, error). The error text says where the pattern is wrong."""
    if pattern == "":
        return None, ""
    try:
        return re.compile(pattern, _flags(flags)), ""
    except re.error as e:
        pos = f" (at character {e.pos + 1})" if e.pos is not None else ""
        return None, f"{e.msg}{pos}"


def find_matches(pattern, flags, text, limit=MAX_MATCHES):
    """{"error", "count", "truncated", "matches": [{"start","end","text","groups","named"}]}"""
    rx, err = compile_pattern(pattern, flags)
    out = {"error": err, "count": 0, "truncated": False, "matches": []}
    if rx is None:
        return out
    for m in rx.finditer(text):
        out["count"] += 1
        if len(out["matches"]) < limit:
            out["matches"].append({"start": m.start(), "end": m.end(), "text": m.group(0),
                                   "groups": list(m.groups()), "named": m.groupdict()})
        else:
            out["truncated"] = True
            if out["count"] > limit * 50:        # stop counting forever on huge inputs
                break
    return out


def replace_all(pattern, flags, replacement, text):
    """(result_text, count, error)."""
    rx, err = compile_pattern(pattern, flags)
    if rx is None:
        return text, 0, err
    try:
        result, n = rx.subn(replacement, text)
    except (re.error, IndexError) as e:
        return text, 0, f"Bad replacement: {e}"
    return result, n, ""


def highlight_markup(text, matches, esc=None):
    """`text` with each match wrapped in [color=..][b]..[/b][/color] for a markup Label."""
    esc = esc or (lambda s: s.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;"))
    out, pos = [], 0
    for m in matches:
        if m["start"] < pos or m["end"] == m["start"]:
            continue
        out.append(esc(text[pos:m["start"]]))
        out.append("[color=ffcc33][b]" + esc(text[m["start"]:m["end"]]) + "[/b][/color]")
        pos = m["end"]
    out.append(esc(text[pos:]))
    return "".join(out)


# ---------------- json ----------------
def parse(text):
    """(value, error). The error names the line and column."""
    if not text.strip():
        return None, "Nothing to read."
    try:
        return json.loads(text), ""
    except json.JSONDecodeError as e:
        return None, f"{e.msg} (line {e.lineno}, column {e.colno})"
    except RecursionError:
        return None, "Nested too deeply."


def pretty(value, indent=2, sort_keys=False):
    return json.dumps(value, indent=indent, sort_keys=sort_keys, ensure_ascii=False)


def minify(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def kind(v):
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    if isinstance(v, str):
        return "string"
    if isinstance(v, bool):
        return "bool"
    if v is None:
        return "null"
    return "number"


def preview(v, n=60):
    k = kind(v)
    if k == "object":
        return "{%d}" % len(v)
    if k == "array":
        return "[%d]" % len(v)
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n - 1] + "..."


def path_text(path):
    out = ""
    for p in path:
        if isinstance(p, int):
            out += f"[{p}]"
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p):
            out += ("." if out else "") + p
        else:
            out += "[" + json.dumps(p, ensure_ascii=False) + "]"
    return out or "$"


def rows(value, expanded, max_rows=MAX_ROWS):
    """Flat list of visible tree rows: (depth, label, preview, path, kind, expandable, is_open).
    `expanded` is a set of paths (tuples) that are open; the root is always open."""
    out = []

    def walk(v, label, path, depth):
        if len(out) >= max_rows:
            return
        k = kind(v)
        expandable = k in ("object", "array") and len(v) > 0
        is_open = expandable and (path in expanded or path == ())
        out.append((depth, label, preview(v), path, k, expandable, is_open))
        if is_open:
            items = v.items() if k == "object" else enumerate(v)
            for key, child in items:
                walk(child, str(key) if k == "object" else f"[{key}]", path + (key,), depth + 1)

    walk(value, "$", (), 0)
    return out


def parse_path(text):
    """'a.b[0]["x y"]' -> ('a', 'b', 0, 'x y'). Raises ValueError for a bad path."""
    t = text.strip()
    if t in ("", "$"):
        return ()
    if t.startswith("$"):
        t = t[1:]
    out, i = [], 0
    while i < len(t):
        c = t[i]
        if c == ".":
            i += 1
            m = re.match(r"[^.\[\]]+", t[i:])
            if not m:
                raise ValueError("Bad path near '.'")
            out.append(m.group(0))
            i += m.end()
        elif c == "[":
            j = t.find("]", i)
            if j < 0:
                raise ValueError("Missing ]")
            inner = t[i + 1:j].strip()
            if re.fullmatch(r"\d+", inner):
                out.append(int(inner))
            elif len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "\"'":
                out.append(inner[1:-1])
            else:
                raise ValueError(f"Bad index [{inner}]")
            i = j + 1
        elif i == 0:
            m = re.match(r"[^.\[\]]+", t)
            out.append(m.group(0))
            i = m.end()
        else:
            raise ValueError(f"Bad path near '{c}'")
    return tuple(out)


def get_path(value, path_str):
    """(found_value, error)."""
    try:
        path = parse_path(path_str)
    except ValueError as e:
        return None, str(e)
    cur = value
    for p in path:
        try:
            cur = cur[p]
        except (KeyError, IndexError, TypeError):
            return None, f"Nothing at {path_text(path)} (stopped at {p!r})"
    return cur, ""
