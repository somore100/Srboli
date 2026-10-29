# core/slides_core.py - slides built from the Full Editor outline, Kivy-free.
#
# Slides are not typed separately any more: they are DERIVED from the outline,
# so a section is written once. Two modes:
#   "separate" - every section (and sub-section) is its own slide
#   "bullets"  - every top-level section is one slide; its sub-sections are
#                bullets (title, with the sub-section's text under it)
# plus an optional title slide made from the document title.
#
# How a slide looks is a small override stored on its section:
#   node["slide"] = {"bg": "#RRGGBB", "fg": "#RRGGBB", "image": "path",
#                    "skip": True}
# (the title slide's overrides live in the document's slide options).
#
# A slide is a plain dict:
#   {"title", "body" (Markdown), "bg", "fg", "image", "tables": [table dicts],
#    "node": outline index or None, "skip": bool}
# [[table:Name]] lines in a body become slide["tables"]; the first standalone
# image line becomes slide["image"] (unless an override sets one).
#
# body_markup() turns a slide's Markdown into one Kivy-markup string for a Label.

import re

from core import outline_core as O
from core import table_core as T
from screens.md_parse import parse_markdown, inline_to_markup, kivy_escape

DEFAULT_BG = "#1A1A2E"
DEFAULT_FG = "#FFFFFF"
MODES = {"separate": "Sub-sections as separate slides",
         "bullets": "Sub-sections as bullets"}

_IMG_LINE_RE = re.compile(
    r"^[ \t]*!\[[^\]\n]*\]\(\s*<?([^()\s>]+)>?(?:\s+\"[^\"\n]*\")?\s*\)[ \t]*$", re.M)


def clean_style(style):
    """Validate a node's "slide" overrides (unknown keys and bad colours go)."""
    out = {}
    if not isinstance(style, dict):
        return out
    for key in ("bg", "fg"):
        c = T.norm_color(style.get(key))
        if c:
            out[key] = c
    if style.get("image"):
        out["image"] = str(style["image"])
    if style.get("skip"):
        out["skip"] = True
    return out


def _split_body(body, tables):
    """Markdown body -> (text without table lines, [table dicts], first image)."""
    found, parts = [], []
    for kind, val in O.split_tables(body):
        if kind == "text":
            parts.append(val)
        else:
            t = T.find(tables, val)
            if t is not None:
                found.append(t)
    text = "".join(parts)
    m = _IMG_LINE_RE.search(text)
    image = None
    if m:
        image = m.group(1)
        text = text[:m.start()] + text[m.end():]
    return text.strip("\n"), found, image


def _make(title, body, style, tables, node):
    style = clean_style(style)
    text, tbls, image = _split_body(body, tables)
    return {"title": title, "body": text, "bg": style.get("bg", DEFAULT_BG),
            "fg": style.get("fg", DEFAULT_FG),
            "image": style.get("image") or image, "tables": tbls,
            "node": node, "skip": bool(style.get("skip"))}


def _bullets(outline, i, end):
    """Sub-sections outline[i+1:end] as nested Markdown bullets."""
    lines = []
    base = outline[i]["depth"]
    for n in outline[i + 1:end]:
        if clean_style(n.get("slide")).get("skip"):
            continue
        ind = "  " * (n["depth"] - base - 1)
        lines.append(f"{ind}- {n['title']}")
        for ln in n["body"].strip().splitlines():
            lines.append(f"{ind}  {ln}" if ln.strip() else "")
    return "\n".join(lines)


def build_slides(title, outline, tables, mode="separate", title_slide=True,
                 title_style=None):
    """All slides, skipped ones included (flagged "skip"; filter for showing)."""
    tables = tables or []
    slides = []
    if title_slide:
        slides.append(_make(title, "", title_style, tables, None))
    if mode == "bullets":
        i = 0
        while i < len(outline):
            end = O.subtree_end(outline, i)
            node = outline[i]
            body = node["body"].strip("\n")
            more = _bullets(outline, i, end)
            if more:
                body = f"{body}\n\n{more}" if body.strip() else more
            slides.append(_make(node["title"], body, node.get("slide"), tables, i))
            i = end
    else:
        for i, node in enumerate(outline):
            slides.append(_make(node["title"], node["body"], node.get("slide"),
                                tables, i))
    return slides


_OLD_BLANK_TITLE = re.compile(r"^Slide \d+$")


def import_slides(old_slides):
    """Documents from before slides were derived held hand-written slides
    ({"title", "body", "color", "bg", "image"}). Return them as outline nodes
    (a "Slides (imported)" section with one sub-section per slide), or [] if
    none of them had any content."""
    kids = []
    for sl in old_slides if isinstance(old_slides, list) else []:
        if not isinstance(sl, dict):
            continue
        title, body = str(sl.get("title", "")), str(sl.get("body", ""))
        image = sl.get("image")
        if not body.strip() and not image and (
                not title.strip() or _OLD_BLANK_TITLE.match(title)):
            continue
        style = clean_style({"bg": sl.get("bg"), "fg": sl.get("color"),
                             "image": image})
        style = {k: v for k, v in style.items()
                 if not (k == "bg" and v == DEFAULT_BG)
                 and not (k == "fg" and v == DEFAULT_FG)}
        node = dict(O.blank_node(title or "Slide", 1), body=body)
        if style:
            node["slide"] = style
        kids.append(node)
    if not kids:
        return []
    return [O.blank_node("Slides (imported)", 0)] + kids


def visible(slides):
    return [s for s in slides if not s["skip"]]


# ── Markdown -> Kivy markup ──────────────────────────────────────────────────
HEAD_SCALE = {1: 1.6, 2: 1.4, 3: 1.25, 4: 1.15, 5: 1.1, 6: 1.0}
MUTED = "9aa0a6"


def _blocks_markup(blocks, fs, sep):
    out = []
    for b in blocks:
        t = b["type"]
        if t == "para":
            out.append(inline_to_markup(b["text"]))
        elif t == "heading":
            size = int(fs * HEAD_SCALE.get(b["level"], 1.0))
            out.append(f"[size={size}][b]{inline_to_markup(b['text'])}[/b][/size]")
        elif t == "list":
            lines = []
            for k, it in enumerate(b["items"]):
                if it["task"] is not None:
                    mark = "&bl;x&br;" if it["task"] else "&bl; &br;"
                else:
                    mark = f"{b['start'] + k}." if b["ordered"] else "•"
                inner = _blocks_markup(it["blocks"], fs, "\n").split("\n")
                lines.append(f"{mark} {inner[0]}")
                lines.extend("    " + ln for ln in inner[1:])
            out.append("\n".join(lines))
        elif t == "quote":
            out.append("[i]" + _blocks_markup(b["blocks"], fs, "\n") + "[/i]")
        elif t == "code":
            out.append("[font=RobotoMono-Regular]" + kivy_escape(b["text"])
                       + "[/font]")
        elif t == "hr":
            out.append(f"[color={MUTED}]----------[/color]")
        elif t == "image":
            out.append(f"[i][color={MUTED}]&bl;image: "
                       f"{kivy_escape(b['alt'] or 'image')}&br;[/color][/i]")
        elif t == "table":
            rows = [b["header"]] + b["rows"]
            lines = [" | ".join(inline_to_markup(c) for c in r) for r in rows]
            lines[0] = f"[b]{lines[0]}[/b]"
            out.append("\n".join(lines))
    return sep.join(out)


def body_markup(markdown, font_size=18):
    """A slide body (Markdown) as one Kivy-markup string."""
    return _blocks_markup(parse_markdown(markdown), font_size, "\n\n")
