# core/outline_core.py - the Full Editor's document outline, Kivy-free.
#
# An outline is a FLAT list in reading order; the tree is implied by "depth":
#     [{"title": "Plan",  "body": "markdown", "depth": 0, "collapsed": False},
#      {"title": "Goals", "body": "...",      "depth": 1, ...}, ...]
# A node may also carry "slide": {...} - how its slide looks (core/slides_core.py).
# A node's subtree is the nodes right after it that are deeper than it.
# A flat list is trivial to save, reorder and indent, and it can never hold an
# impossible tree (every function here keeps depths valid: the first node is
# depth 0 and a node is at most one level deeper than the node before it).
#
# Bodies are Markdown (screens/md_parse.py); this module also turns the whole
# outline into one Markdown text or one HTML page. A body line that is only
# [[table:Name]] stands for the document's table of that name (core/table_core.py).

import html as _html
import re
from pathlib import Path

from core import table_core
from screens.md_parse import parse_markdown, inline_to_markup

MAX_DEPTH = 5            # depth 0 is "#" under the document title -> h2..h6


def blank_node(title="New section", depth=0):
    return {"title": title, "body": "", "depth": depth, "collapsed": False}


def normalize(raw):
    """Clean an outline loaded from a file; never returns an empty list."""
    out = []
    for n in raw if isinstance(raw, list) else []:
        if not isinstance(n, dict):
            continue
        try:
            depth = int(n.get("depth", 0))
        except (TypeError, ValueError):
            depth = 0
        prev = out[-1]["depth"] + 1 if out else 0
        node = {"title": str(n.get("title", "")),
                "body": str(n.get("body", "")),
                "depth": max(0, min(depth, prev, MAX_DEPTH)),
                "collapsed": bool(n.get("collapsed", False))}
        if isinstance(n.get("slide"), dict):
            node["slide"] = n["slide"]        # cleaned by core/slides_core.py
        out.append(node)
    return out or [blank_node("Section 1")]


# ── tree queries ─────────────────────────────────────────────────────────────
def subtree_end(outline, i):
    """Index just after node i's last descendant."""
    j, d = i + 1, outline[i]["depth"]
    while j < len(outline) and outline[j]["depth"] > d:
        j += 1
    return j


def has_children(outline, i):
    return i + 1 < len(outline) and outline[i + 1]["depth"] > outline[i]["depth"]


def visible_indices(outline):
    """Indices to show in the tree: everything except inside collapsed nodes."""
    out, hide_below = [], None
    for i, n in enumerate(outline):
        if hide_below is not None and n["depth"] > hide_below:
            continue
        hide_below = n["depth"] if n["collapsed"] else None
        out.append(i)
    return out


def parent_index(outline, i):
    d = outline[i]["depth"]
    for j in range(i - 1, -1, -1):
        if outline[j]["depth"] < d:
            return j
    return None


_MARKUP_RE = re.compile(r"\[/?color[^\]]*\]|!?\[([^\]]*)\]\([^)]*\)|[*_~`#>]+|^\s*(?:[-+]|\d+[.)])\s+")


def snippet(body, limit=48):
    """One short plain-text line saying what a section contains: the first
    non-empty line of its Markdown body, without the markup."""
    for line in str(body).splitlines():
        text = _MARKUP_RE.sub(lambda m: m.group(1) or "", line).strip()
        if text and not re.fullmatch(r"[-=\s|:]*", text):
            text = " ".join(text.split())
            return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."
    return ""


# ── edits (each returns the index of the node to select afterwards) ──────────
def add_sibling(outline, i, title="New section"):
    j = subtree_end(outline, i)
    outline.insert(j, blank_node(title, outline[i]["depth"]))
    return j


def add_child(outline, i, title="New section"):
    if outline[i]["depth"] >= MAX_DEPTH:
        return add_sibling(outline, i, title)
    outline[i]["collapsed"] = False
    j = subtree_end(outline, i)
    outline.insert(j, blank_node(title, outline[i]["depth"] + 1))
    return j


def delete_subtree(outline, i):
    """Remove node i and its descendants (the last remaining node is kept)."""
    end = subtree_end(outline, i)
    if end - i >= len(outline):
        return i
    del outline[i:end]
    if not outline:
        outline.append(blank_node("Section 1"))
    return min(i, len(outline) - 1)


def move(outline, i, step):
    """Swap node i's subtree with the neighbouring sibling subtree above
    (step=-1) or below (step=+1). Returns the new index (i if it can't)."""
    d = outline[i]["depth"]
    end = subtree_end(outline, i)
    block = outline[i:end]
    if step < 0:
        j = i - 1
        while j >= 0 and outline[j]["depth"] > d:
            j -= 1
        if j < 0 or outline[j]["depth"] < d:
            return i
        outline[j:end] = block + outline[j:i]
        return j
    if end >= len(outline) or outline[end]["depth"] < d:
        return i
    nend = subtree_end(outline, end)
    outline[i:nend] = outline[end:nend] + block
    return i + (nend - end)


def indent(outline, i):
    """Make node i (and its subtree) a child of the node above it."""
    if i == 0 or outline[i]["depth"] > outline[i - 1]["depth"]:
        return False
    end = subtree_end(outline, i)
    if max(n["depth"] for n in outline[i:end]) >= MAX_DEPTH:
        return False
    for n in outline[i:end]:
        n["depth"] += 1
    outline[i - 1]["collapsed"] = False
    return True


def outdent(outline, i):
    """Promote node i (and its subtree) one level. Like Word's outline view:
    the siblings after it keep their level, so they become its children."""
    if outline[i]["depth"] == 0:
        return False
    for n in outline[i:subtree_end(outline, i)]:
        n["depth"] -= 1
    return True


# ── import from the old paragraph-based documents ────────────────────────────
def paragraphs_to_markdown(paragraphs):
    parts = []
    for p in paragraphs if isinstance(paragraphs, list) else []:
        if not isinstance(p, dict):
            continue
        if p.get("image"):
            parts.append(f"![image]({p['image']})")
            continue
        text = str(p.get("text", ""))
        if not text.strip():
            continue
        if p.get("bold"):
            text = f"**{text}**"
        color = str(p.get("color", "")).upper()
        if re.fullmatch(r"#[0-9A-F]{6}", color) and color != "#FFFFFF":
            text = f"[color={color}]{text}[/color]"
        parts.append(text)
    return "\n\n".join(parts)


# ── whole-document output ────────────────────────────────────────────────────
_TABLE_LINE_RE = re.compile(r"^[ \t]*\[\[table:([^\]\n]+)\]\][ \t]*$", re.M)


def table_placeholder(name):
    return f"[[table:{name}]]"


def referenced_tables(outline):
    """Names of the tables placed into section bodies."""
    return {m.group(1) for n in outline for m in _TABLE_LINE_RE.finditer(n["body"])}


def split_tables(text):
    """Body text -> [("text", str) | ("table", name), ...] in order."""
    parts, pos = [], 0
    for m in _TABLE_LINE_RE.finditer(text):
        parts.append(("text", text[pos:m.start()]))
        parts.append(("table", m.group(1)))
        pos = m.end()
    parts.append(("text", text[pos:]))
    return parts


def to_markdown(title, outline, tables=None):
    """The outline as one Markdown text. Placed tables become plain Markdown
    tables (no colours) when `tables` is given."""
    parts = [f"# {title}"]
    for n in outline:
        parts.append("#" * min(6, n["depth"] + 2) + f" {n['title']}")
        body = n["body"].strip("\n")
        if tables is not None:
            def sub(m):
                t = table_core.find(tables, m.group(1))
                return (table_core.to_markdown(t) if t
                        else f"(missing table: {m.group(1)})")
            body = _TABLE_LINE_RE.sub(sub, body)
        if body.strip():
            parts.append(body)
    return "\n\n".join(parts) + "\n"


_TAG_SUBS = [
    (re.compile(r"\[(/?)(b|i|s|u)\]"), lambda m: f"<{m.group(1)}{m.group(2)}>"),
    (re.compile(r"\[color=([0-9a-fA-F]{3,8})\]"),
     lambda m: f'<span style="color:#{m.group(1)}">'),
    (re.compile(r"\[/color\]"), lambda m: "</span>"),
    (re.compile(r"\[font=[^\]]*\]"), lambda m: "<code>"),
    (re.compile(r"\[/font\]"), lambda m: "</code>"),
    (re.compile(r"\[ref=([^\]]*)\]"),
     lambda m: f'<a href="{_html.escape(m.group(1), quote=True)}">'),
    (re.compile(r"\[/ref\]"), lambda m: "</a>"),
]


def _inline_html(text):
    """One run of inline Markdown -> HTML (via the Kivy markup the viewer uses)."""
    s = inline_to_markup(text).replace("<", "&lt;").replace(">", "&gt;")
    for rx, fn in _TAG_SUBS:
        s = rx.sub(fn, s)
    return s.replace("&bl;", "&#91;").replace("&br;", "&#93;").replace("\n", "<br>")


def _img_url(url):
    if re.match(r"(?i)https?://", url):
        return _html.escape(url, quote=True)
    try:
        return _html.escape(Path(url).resolve().as_uri(), quote=True)
    except Exception:
        return _html.escape(url, quote=True)


def _blocks_html(blocks, base):
    out = []
    for b in blocks:
        t = b["type"]
        if t == "para":
            out.append(f"<p>{_inline_html(b['text'])}</p>")
        elif t == "heading":
            lvl = min(6, base + b["level"])
            out.append(f"<h{lvl}>{_inline_html(b['text'])}</h{lvl}>")
        elif t == "hr":
            out.append("<hr>")
        elif t == "code":
            out.append(f"<pre><code>{_html.escape(b['text'])}</code></pre>")
        elif t == "image":
            out.append(f'<img src="{_img_url(b["url"])}" '
                       f'alt="{_html.escape(b["alt"], quote=True)}" '
                       'style="max-width:100%">')
        elif t == "quote":
            out.append("<blockquote>" + _blocks_html(b["blocks"], base)
                       + "</blockquote>")
        elif t == "list":
            tag = "ol" if b["ordered"] else "ul"
            items = []
            for it in b["items"]:
                mark = ("" if it["task"] is None
                        else ("[x] " if it["task"] else "[ ] "))
                items.append(f"<li>{mark}{_blocks_html(it['blocks'], base)}</li>")
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
        elif t == "table":
            def cell(tag, txt, al):
                return f'<{tag} style="text-align:{al}">{_inline_html(txt)}</{tag}>'
            al = (b["aligns"] + ["left"] * len(b["header"]))[:len(b["header"])]
            head = "".join(cell("th", c, a) for c, a in zip(b["header"], al))
            rows = "".join(
                "<tr>" + "".join(cell("td", c, a) for c, a in zip(r, al)) + "</tr>"
                for r in b["rows"])
            out.append("<table border='1' cellpadding='4' "
                       "style='border-collapse:collapse'>"
                       f"<tr>{head}</tr>{rows}</table>")
    return "".join(out)


def markdown_to_html(text, base_level=2, tables=None):
    """Markdown body -> HTML fragment. Headings inside it start at base_level.
    With `tables`, [[table:Name]] lines become coloured HTML tables."""
    if tables is None:
        return _blocks_html(parse_markdown(text), base_level)
    out = []
    for kind, val in split_tables(text):
        if kind == "text":
            out.append(_blocks_html(parse_markdown(val), base_level))
            continue
        t = table_core.find(tables, val)
        out.append(table_core.to_html(t) if t else
                   f"<p><i>(missing table: {_html.escape(val)})</i></p>")
    return "".join(out)


def to_html(title, outline, tables=None):
    """The whole outline as an HTML fragment (title as h1, nodes as h2..h6)."""
    esc = _html.escape
    out = [f"<h1>{esc(title)}</h1>"]
    for n in outline:
        lvl = min(6, n["depth"] + 2)
        out.append(f"<h{lvl}>{esc(n['title'])}</h{lvl}>")
        out.append(markdown_to_html(n["body"], lvl, tables))
    return "\n".join(out)
