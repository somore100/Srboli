# screens/md_parse.py — Markdown-ish parser for the Text Editor's Styled view.
#
# Deliberately Kivy-free: it turns text into plain-data "blocks" and turns
# inline syntax into Kivy label markup strings. That keeps it unit-testable
# without a window, and reusable by anything else that needs it later
# (e.g. an HTML exporter, or the background daemon).
#
# Supported (GitHub-flavoured subset):
#   blocks : # headings (needs a space after the #s, like GitHub),
#            setext headings, fenced code (``` / ~~~), > quotes (nested),
#            - * + and 1. lists (nested), - [ ] / - [x] task items,
#            --- *** ___ rules, | pipe | tables |, images on their own line
#   inline : `code`, **bold**, __bold__, *italic*, _italic_, ~~strike~~,
#            [text](url), <url>, bare http(s) URLs, ![alt](url),
#            \* backslash escapes, and the editor's own
#            [color=#hex]text[/color] tags.
#
# Newlines inside a paragraph are KEPT as line breaks (like GitHub issue
# comments, not like a .md file's soft wrap) — this is a note editor, and
# people expect "Enter" to mean a new line.

import re

# ── colours used inside inline markup (Kivy wants rrggbb, no '#') ───────────
LINK_COLOR = "5aa9ff"
CODE_COLOR = "ffb86c"
MUTED_COLOR = "9aa0a6"

_NAMED_COLORS = {
    "red": "ff4d4d", "green": "3ddc84", "blue": "4d94ff",
    "yellow": "ffd93d", "orange": "ff9f43", "purple": "b07cff",
    "pink": "ff7eb6", "white": "ffffff", "black": "000000",
    "gray": "9aa0a6", "grey": "9aa0a6", "cyan": "3de0ff",
    "magenta": "ff4dff", "teal": "2ec4b6", "lime": "9aff3d",
}

_PH0, _PH1 = "\ue000", "\ue001"      # private-use placeholder brackets


def kivy_escape(s):
    """Escape text for a Kivy markup Label."""
    return s.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def safe_url(url):
    """Only these schemes may be opened from a click in the rendered view."""
    u = url.strip()
    low = u.lower()
    return u if low.startswith(("http://", "https://", "mailto:")) else None


def _norm_color(value):
    v = value.strip().lower().lstrip("#")
    if v in _NAMED_COLORS:
        return _NAMED_COLORS[v]
    if re.fullmatch(r"[0-9a-f]{3}", v):
        return "".join(c * 2 for c in v)
    if re.fullmatch(r"[0-9a-f]{6}([0-9a-f]{2})?", v):
        return v
    return None


# ── inline ───────────────────────────────────────────────────────────────────
_CODE_RE = re.compile(r"(?<!\\)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
_ESC_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~<>])")
_COLOR_OPEN_RE = re.compile(r"\[color=([^\]\s]+)\]", re.I)
_COLOR_CLOSE_RE = re.compile(r"\[/color\]", re.I)
_URL_PART = r"<?((?:[^()\s>]|\([^()\s]*\))+)>?"
_IMG_RE = re.compile(
    r"!\[([^\]]*)\]\(\s*" + _URL_PART + r"(?:\s+\"[^\"]*\")?\s*\)")
_LINK_RE = re.compile(
    r"\[((?:[^\[\]]|\[[^\]]*\])+)\]\(\s*" + _URL_PART +
    r"(?:\s+\"[^\"]*\")?\s*\)")
_AUTOLINK_RE = re.compile(r"<((?:https?://|mailto:)[^\s<>]+)>")
_BAREURL_RE = re.compile(r"(?<![\w/(\"'=])(https?://[^\s<>\]]+)")
_PH_RE = re.compile(_PH0 + r"(\d+)" + _PH1)

_EMPH = [
    (re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*", re.S), "[b][i]", "[/i][/b]"),
    (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S), "[b]", "[/b]"),
    (re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)", re.S), "[b]", "[/b]"),
    (re.compile(r"\*(?=[^\s*])(.+?)(?<=[^\s*])\*", re.S), "[i]", "[/i]"),
    (re.compile(r"(?<!\w)_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)", re.S),
     "[i]", "[/i]"),
    (re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S), "[s]", "[/s]"),
]


def _link_markup(inner_markup, url):
    ok = safe_url(url)
    if not ok:
        return inner_markup
    return (f"[ref={ok}][color={LINK_COLOR}][u]{inner_markup}[/u]"
            f"[/color][/ref]")


def inline_to_markup(text, mono_font="RobotoMono-Regular"):
    """Convert one run of inline Markdown to Kivy markup."""
    slots = []

    def stash(markup):
        slots.append(markup)
        return f"{_PH0}{len(slots) - 1}{_PH1}"

    s = text

    # 1. code spans (before escapes: backslashes are literal inside code)
    def _code(m):
        code = m.group(2)
        if len(code) > 1 and code.startswith(" ") and code.endswith(" "):
            code = code[1:-1]
        return stash(f"[font={mono_font}][color={CODE_COLOR}]"
                     f"{kivy_escape(code)}[/color][/font]")
    s = _CODE_RE.sub(_code, s)

    # 2. backslash escapes
    s = _ESC_RE.sub(lambda m: stash(kivy_escape(m.group(1))), s)

    # 3. editor colour tags (opening and closing stashed separately so
    #    emphasis can wrap across them)
    def _copen(m):
        c = _norm_color(m.group(1))
        return stash(f"[color={c}]") if c else stash("")
    s = _COLOR_OPEN_RE.sub(_copen, s)
    s = _COLOR_CLOSE_RE.sub(lambda m: stash("[/color]"), s)

    # 4. images and links
    def _img(m):
        alt = m.group(1) or "image"
        return stash(f"[i][color={MUTED_COLOR}]&bl;image: "
                     f"{kivy_escape(alt)}&br;[/color][/i]")
    s = _IMG_RE.sub(_img, s)

    def _link(m):
        return stash(_link_markup(inline_to_markup(m.group(1), mono_font),
                                  m.group(2)))
    s = _LINK_RE.sub(_link, s)

    def _auto(m):
        return stash(_link_markup(kivy_escape(m.group(1)), m.group(1)))
    s = _AUTOLINK_RE.sub(_auto, s)

    def _bare(m):
        url = m.group(1)
        trail = ""
        while url and url[-1] in ".,;:!?)'\"":
            if url[-1] == ")" and url.count("(") >= url.count(")"):
                break
            trail = url[-1] + trail
            url = url[:-1]
        return stash(_link_markup(kivy_escape(url), url)) + trail
    s = _BAREURL_RE.sub(_bare, s)

    # 5. escape what's left, then emphasis
    s = kivy_escape(s)
    for rx, o, c in _EMPH:
        s = rx.sub(lambda m, o=o, c=c: f"{o}{m.group(1)}{c}", s)

    # 6. put stashed pieces back
    out = _PH_RE.sub(lambda m: slots[int(m.group(1))], s)
    return _balance_colors(out)


def _balance_colors(markup):
    """Kivy leaks a colour if an opener has no closer (and can misbehave on
    a stray closer). Drop unmatched [color=...] / [/color] pieces."""
    tokens = re.split(r"(\[color=[0-9a-f]+\]|\[/color\])", markup)
    # first pass: find which openers/closers pair up
    stack, keep = [], set()
    for i, t in enumerate(tokens):
        if t.startswith("[color="):
            stack.append(i)
        elif t == "[/color]":
            if stack:
                keep.add(stack.pop())
                keep.add(i)
    out = []
    for i, t in enumerate(tokens):
        if (t.startswith("[color=") or t == "[/color]") and i not in keep:
            # link colour tags are always balanced by construction, so an
            # unmatched tag can only be a user colour tag
            continue
        out.append(t)
    return "".join(out)


# ── block parser ─────────────────────────────────────────────────────────────
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([^\s`]*)")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_HEADING_EMPTY_RE = re.compile(r"^\s{0,3}(#{1,6})[ \t]*$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_QUOTE_RE = re.compile(r"^\s{0,3}>[ ]?(.*)$")
_BULLET_RE = re.compile(r"^(\s*)([-*+])[ \t]+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)(\d{1,9})([.)])[ \t]+(.*)$")
_BARE_MARKER_RE = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])[ \t]*$")
_SETEXT1_RE = re.compile(r"^\s{0,3}=+[ \t]*$")
_SETEXT2_RE = re.compile(r"^\s{0,3}-{2,}[ \t]*$")
_TABLE_DELIM_RE = re.compile(
    r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_TASK_RE = re.compile(r"^\[([ xX])\][ \t]+(.*)$", re.S)
_STANDALONE_IMG_RE = re.compile(
    r"^!\[([^\]]*)\]\(\s*" + _URL_PART + r"(?:\s+\"[^\"]*\")?\s*\)\s*$")


def _indent_of(line):
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip(" "))


def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells, cur, i = [], "", 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if s[i] == "|":
            cells.append(cur.strip())
            cur = ""
        else:
            cur += s[i]
        i += 1
    cells.append(cur.strip())
    return cells


def _is_table_start(lines, i):
    if i + 1 >= len(lines):
        return False
    head, delim = lines[i], lines[i + 1]
    if "|" not in head or "-" not in delim:
        return False
    if not _TABLE_DELIM_RE.match(delim):
        return False
    return len(_split_row(head)) == len(_split_row(delim))


def _starts_block(line):
    """True if `line` begins something other than a paragraph line
    (used to let a list/heading/etc. interrupt a running paragraph)."""
    return bool(_FENCE_RE.match(line) or _HEADING_RE.match(line)
                or _HR_RE.match(line) or _QUOTE_RE.match(line)
                or _BULLET_RE.match(line) or _ORDERED_RE.match(line))


def parse_blocks(lines):
    blocks, para = [], []
    i, n = 0, len(lines)

    def flush():
        if para:
            text = "\n".join(p.strip() for p in para)
            m = _STANDALONE_IMG_RE.match(text)
            if m:
                blocks.append({"type": "image", "alt": m.group(1),
                               "url": m.group(2)})
            else:
                blocks.append({"type": "para", "text": text})
            para.clear()

    while i < n:
        line = lines[i]
        if not line.strip():
            flush()
            i += 1
            continue

        # fenced code
        m = _FENCE_RE.match(line)
        if m:
            flush()
            fence, lang = m.group(1), m.group(2)
            body, i = [], i + 1
            while i < n:
                cm = re.match(r"^\s{0,3}(" + re.escape(fence[0]) +
                              r"{" + str(len(fence)) + r",})\s*$", lines[i])
                if cm:
                    i += 1
                    break
                body.append(lines[i])
                i += 1
            blocks.append({"type": "code", "lang": lang,
                           "text": "\n".join(body)})
            continue

        # setext heading (only directly under paragraph text)
        if para and _SETEXT1_RE.match(line):
            blocks.append({"type": "heading", "level": 1,
                           "text": " ".join(p.strip() for p in para)})
            para.clear()
            i += 1
            continue
        if para and _SETEXT2_RE.match(line) and not _BULLET_RE.match(line):
            blocks.append({"type": "heading", "level": 2,
                           "text": " ".join(p.strip() for p in para)})
            para.clear()
            i += 1
            continue

        # ATX heading
        m = _HEADING_RE.match(line)
        if m:
            flush()
            blocks.append({"type": "heading", "level": len(m.group(1)),
                           "text": m.group(2).strip()})
            i += 1
            continue
        m = _HEADING_EMPTY_RE.match(line)
        if m:
            flush()
            blocks.append({"type": "heading", "level": len(m.group(1)),
                           "text": ""})
            i += 1
            continue

        # horizontal rule
        if _HR_RE.match(line):
            flush()
            blocks.append({"type": "hr"})
            i += 1
            continue

        # blockquote
        if _QUOTE_RE.match(line):
            flush()
            qlines = []
            while i < n and _QUOTE_RE.match(lines[i]):
                qlines.append(_QUOTE_RE.match(lines[i]).group(1))
                i += 1
            blocks.append({"type": "quote", "blocks": parse_blocks(qlines)})
            continue

        # table
        if _is_table_start(lines, i):
            flush()
            header = _split_row(lines[i])
            aligns = []
            for d in _split_row(lines[i + 1]):
                d = d.strip()
                if d.startswith(":") and d.endswith(":"):
                    aligns.append("center")
                elif d.endswith(":"):
                    aligns.append("right")
                else:
                    aligns.append("left")
            i += 2
            rows = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                cells = _split_row(lines[i])
                cells = (cells + [""] * len(header))[:len(header)]
                rows.append(cells)
                i += 1
            blocks.append({"type": "table", "aligns": aligns,
                           "header": header, "rows": rows})
            continue

        # list
        bm, om = _BULLET_RE.match(line), _ORDERED_RE.match(line)
        if bm or om:
            flush()
            block, i = _parse_list(lines, i)
            blocks.append(block)
            continue

        para.append(line)
        i += 1

    flush()
    return blocks


def _marker_info(line):
    """-> (indent, ordered, number, content_indent, text) or None"""
    bm = _BULLET_RE.match(line)
    if bm:
        ind = _indent_of(line)
        head = len(bm.group(1)) + 1
        gap = len(line) - len(bm.group(3)) - head
        return ind, False, 0, head + max(1, gap), bm.group(3)
    om = _ORDERED_RE.match(line)
    if om:
        ind = _indent_of(line)
        head = len(om.group(1)) + len(om.group(2)) + 1
        gap = len(line) - len(om.group(4)) - head
        return ind, True, int(om.group(2)), head + max(1, gap), om.group(4)
    return None


def _strip_indent(line, k):
    line = line.expandtabs(4)
    cut = 0
    while cut < k and cut < len(line) and line[cut] == " ":
        cut += 1
    return line[cut:]


def _parse_list(lines, i):
    """Parse one list starting at lines[i]. Returns (block, next_index).

    Leniency notes: an item's nested content may be indented by any amount
    deeper than its bullet (2 spaces under "1. " works, unlike strict
    CommonMark), and a sibling bullet may be off by one space.
    """
    n = len(lines)
    base_ind, ordered, start, _, _ = _marker_info(lines[i])
    items = []

    while i < n:
        info = _marker_info(lines[i])
        if (not info or info[1] != ordered
                or not (base_ind <= info[0] <= base_ind + 1)):
            break
        cindent, text = info[3], info[4]
        body = [text]
        i += 1
        blank_run = 0
        while i < n:
            ln = lines[i]
            if not ln.strip():
                blank_run += 1
                body.append("")
                i += 1
                continue
            m2 = _marker_info(ln)
            if m2 and base_ind <= m2[0] <= base_ind + 1:
                break                       # sibling (or a new list kind)
            if _indent_of(ln) > base_ind:   # nested / continuation content
                blank_run = 0
                body.append(_strip_indent(ln, cindent))
                i += 1
                continue
            if blank_run == 0 and not _starts_block(ln):
                body.append(ln.strip())     # lazy paragraph continuation
                i += 1
                continue
            break
        while body and not body[-1].strip():
            body.pop()

        task = None
        tm = _TASK_RE.match(body[0])
        if tm:
            task = tm.group(1).lower() == "x"
            body[0] = tm.group(2)
        items.append({"blocks": parse_blocks(body), "task": task})

        # blank lines only continue the list if another sibling follows
        j = i
        while j < n and not lines[j].strip():
            j += 1
        nxt = _marker_info(lines[j]) if j < n else None
        if nxt and nxt[1] == ordered and base_ind <= nxt[0] <= base_ind + 1:
            i = j
        else:
            break

    return {"type": "list", "ordered": ordered, "start": start,
            "items": items}, i


def parse_markdown(text):
    """Text -> list of block dicts."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return parse_blocks(lines)
