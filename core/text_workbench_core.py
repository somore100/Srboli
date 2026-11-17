# core/text_workbench_core.py - the text tools behind the Text Workbench screen.
# Pure Python, no Kivy. Every function takes text and returns text (or a small
# result), so each one is tested on its own.
#
#   lines     sort, reverse, shuffle, dedupe, trim, filter, number, join, ...
#   extract   emails, links, IP addresses, numbers, dates out of a text
#   regex     test a pattern (matches + groups) and replace with it
#   diff      compare two texts line by line
#   stats     counts, reading time, most used words

import difflib
import random
import re
from collections import Counter

MAX_CHARS = 400_000          # bigger than this and the screen refuses (keeps it responsive)


class TextError(Exception):
    """A problem worded for the user (bad regex, too much text...)."""


def check_size(*texts):
    for t in texts:
        if len(t) > MAX_CHARS:
            raise TextError(f"That is a lot of text ({len(t):,} characters). "
                            f"The limit here is {MAX_CHARS:,}.")


def split_lines(text):
    """Lines without their line endings (a final newline does not add an empty line)."""
    lines = text.splitlines()
    return lines


def join_lines(lines):
    return "\n".join(lines)


# ── lines ───────────────────────────────────────────────────────────────────
def _natural_key(s):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


# key -> (label, what the option box means or None)
LINE_OPS = {
    "sort":      ("Sort A-Z", None),
    "sort_desc": ("Sort Z-A", None),
    "natural":   ("Sort naturally (file2 before file10)", None),
    "numeric":   ("Sort by number at the start", None),
    "by_length": ("Sort by length", None),
    "reverse":   ("Reverse the order", None),
    "shuffle":   ("Shuffle", None),
    "dedupe":    ("Remove duplicate lines", None),
    "dupes":     ("Keep only the duplicated lines", None),
    "blank":     ("Remove blank lines", None),
    "trim":      ("Trim spaces at both ends", None),
    "squeeze":   ("Collapse runs of spaces", None),
    "keep":      ("Keep lines containing...", "text to look for"),
    "drop":      ("Remove lines containing...", "text to look for"),
    "keep_re":   ("Keep lines matching regex...", "regular expression"),
    "drop_re":   ("Remove lines matching regex...", "regular expression"),
    "prefix":    ("Add text at the start of each line...", "text to add"),
    "suffix":    ("Add text at the end of each line...", "text to add"),
    "number":    ("Number the lines", None),
    "upper":     ("UPPERCASE", None),
    "lower":     ("lowercase", None),
    "title":     ("Title Case", None),
    "join":      ("Join all lines into one...", "separator (e.g. , )"),
    "split":     ("Split into lines at...", "separator (e.g. , )"),
    "wrap":      ("Wrap long lines at...", "width in characters"),
}


def _first_number(s):
    m = re.match(r"\s*(-?\d+(?:[.,]\d+)?)", s)
    return float(m.group(1).replace(",", ".")) if m else float("inf")


def _regex(pattern, ignore_case=False):
    try:
        return re.compile(pattern, re.I if ignore_case else 0)
    except re.error as e:
        raise TextError(f"That regular expression isn't valid: {e}")


def apply_lines(op, text, arg="", ignore_case=False, seed=None):
    """Run one line operation. Returns the new text."""
    check_size(text)
    if op not in LINE_OPS:
        raise TextError("Unknown operation.")
    if LINE_OPS[op][1] and not arg and op not in ("prefix", "suffix", "join"):
        raise TextError("Fill in the option box first (" + LINE_OPS[op][1] + ").")
    if op == "split":
        return join_lines(text.split(arg)) if arg else text
    lines = split_lines(text)
    fold = (lambda s: s.lower()) if ignore_case else (lambda s: s)
    if op == "sort":
        lines.sort(key=lambda s: fold(s))
    elif op == "sort_desc":
        lines.sort(key=lambda s: fold(s), reverse=True)
    elif op == "natural":
        lines.sort(key=_natural_key)
    elif op == "numeric":
        lines.sort(key=_first_number)
    elif op == "by_length":
        lines.sort(key=len)
    elif op == "reverse":
        lines.reverse()
    elif op == "shuffle":
        random.Random(seed).shuffle(lines)
    elif op == "dedupe":
        seen, out = set(), []
        for ln in lines:
            k = fold(ln)
            if k not in seen:
                seen.add(k)
                out.append(ln)
        lines = out
    elif op == "dupes":
        count = Counter(fold(ln) for ln in lines)
        seen, out = set(), []
        for ln in lines:
            k = fold(ln)
            if count[k] > 1 and k not in seen:
                seen.add(k)
                out.append(ln)
        lines = out
    elif op == "blank":
        lines = [ln for ln in lines if ln.strip()]
    elif op == "trim":
        lines = [ln.strip() for ln in lines]
    elif op == "squeeze":
        lines = [re.sub(r"[ \t]{2,}", " ", ln) for ln in lines]
    elif op in ("keep", "drop"):
        needle = fold(arg)
        hit = [needle in fold(ln) for ln in lines]
        lines = [ln for ln, h in zip(lines, hit) if h == (op == "keep")]
    elif op in ("keep_re", "drop_re"):
        rx = _regex(arg, ignore_case)
        lines = [ln for ln in lines if bool(rx.search(ln)) == (op == "keep_re")]
    elif op == "prefix":
        lines = [arg + ln for ln in lines]
    elif op == "suffix":
        lines = [ln + arg for ln in lines]
    elif op == "number":
        width = len(str(len(lines)))
        lines = [f"{i:>{width}}. {ln}" for i, ln in enumerate(lines, 1)]
    elif op == "upper":
        lines = [ln.upper() for ln in lines]
    elif op == "lower":
        lines = [ln.lower() for ln in lines]
    elif op == "title":
        lines = [ln.title() for ln in lines]
    elif op == "join":
        return (arg if arg else " ").join(lines)
    elif op == "wrap":
        try:
            width = int(arg)
        except ValueError:
            raise TextError("The width must be a whole number.")
        if width < 5:
            raise TextError("The width must be at least 5.")
        import textwrap
        out = []
        for ln in lines:
            out.extend(textwrap.wrap(ln, width) or [""])
        lines = out
    return join_lines(lines)


# ── extract ─────────────────────────────────────────────────────────────────
EXTRACTORS = {
    "emails":  ("Email addresses", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "urls":    ("Links (http, https, www)", r"(?:https?://|www\.)[^\s<>\"')\]]+"),
    "ipv4":    ("IPv4 addresses", r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    "numbers": ("Numbers", r"-?\d+(?:[.,]\d+)?"),
    "dates":   ("Dates (2026-11-17, 17.11.2026, 17/11/2026)",
                r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"),
    "hashtags": ("#hashtags", r"(?<!\w)#\w+"),
    "quoted":  ("Text in \"quotes\"", r"\"([^\"\n]+)\""),
    "words":   ("Words", r"[^\W\d_]+(?:['’-][^\W\d_]+)*"),
}


def extract(kind, text, unique=True, sort=False):
    """(matches, text) for one kind of thing in a text."""
    check_size(text)
    if kind not in EXTRACTORS:
        raise TextError("Unknown kind.")
    rx = re.compile(EXTRACTORS[kind][1])
    found = [m.group(1) if rx.groups else m.group(0) for m in rx.finditer(text)]
    if kind == "urls":
        found = [u.rstrip(".,;:!?") for u in found]
    if unique:
        found = list(dict.fromkeys(found))
    if sort:
        found.sort(key=str.lower)
    return found, "\n".join(found)


# ── regex ───────────────────────────────────────────────────────────────────
def _flags(ignore_case, multiline, dotall):
    return ((re.I if ignore_case else 0) | (re.M if multiline else 0)
            | (re.S if dotall else 0))


def regex_matches(pattern, text, ignore_case=False, multiline=False,
                  dotall=False, limit=500):
    """[(start, end, matched text, [groups], {named})] - at most `limit`."""
    check_size(text)
    if not pattern:
        raise TextError("Type a pattern first.")
    try:
        rx = re.compile(pattern, _flags(ignore_case, multiline, dotall))
    except re.error as e:
        raise TextError(f"That regular expression isn't valid: {e}")
    out = []
    for m in rx.finditer(text):
        out.append((m.start(), m.end(), m.group(0), list(m.groups()),
                    m.groupdict()))
        if len(out) >= limit:
            break
    return out


def regex_report(pattern, text, **flags):
    """Readable description of the matches."""
    ms = regex_matches(pattern, text, **flags)
    if not ms:
        return "No match."
    lines = [f"{len(ms)} match{'es' if len(ms) != 1 else ''}"
             + (" (showing the first 500)" if len(ms) >= 500 else "")]
    for i, (a, b, s, groups, named) in enumerate(ms, 1):
        lines.append(f"{i}. [{a}-{b}] {s!r}")
        for gi, g in enumerate(groups, 1):
            lines.append(f"     group {gi}: {g!r}")
        for k, v in named.items():
            lines.append(f"     {k}: {v!r}")
    return "\n".join(lines)


def regex_replace(pattern, replacement, text, ignore_case=False,
                  multiline=False, dotall=False):
    """(new text, number of replacements). \\1 and \\g<name> work in the replacement."""
    check_size(text)
    if not pattern:
        raise TextError("Type a pattern first.")
    try:
        rx = re.compile(pattern, _flags(ignore_case, multiline, dotall))
        return rx.subn(replacement, text)
    except re.error as e:
        raise TextError(f"That didn't work: {e}")


# ── diff ────────────────────────────────────────────────────────────────────
def diff_texts(a, b, ignore_space=False, ignore_case=False, context=None):
    """(report text, (added, removed, changed_blocks)). Lines only in A start
    with "- ", only in B with "+ ", equal lines with two spaces. `context`
    (a number) shows only that many equal lines around each change."""
    check_size(a, b)
    la, lb = split_lines(a), split_lines(b)

    def norm(s):
        if ignore_space:
            s = " ".join(s.split())
        return s.lower() if ignore_case else s

    na, nb = [norm(s) for s in la], [norm(s) for s in lb]
    sm = difflib.SequenceMatcher(None, na, nb, autojunk=False)
    out, added, removed, blocks = [], 0, 0, 0
    ops = sm.get_opcodes()
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            out.extend(("  ", ln) for ln in la[i1:i2])
            continue
        blocks += 1
        for ln in la[i1:i2]:
            out.append(("- ", ln))
            removed += 1
        for ln in lb[j1:j2]:
            out.append(("+ ", ln))
            added += 1
    if context is not None:
        keep = set()
        for i, (mark, _ln) in enumerate(out):
            if mark != "  ":
                keep.update(range(max(0, i - context), min(len(out), i + context + 1)))
        shown, last = [], -1
        for i in sorted(keep):
            if i != last + 1:
                shown.append(("  ", "..."))
            shown.append(out[i])
            last = i
        if last != len(out) - 1:
            shown.append(("  ", "..."))
        out = shown
    if not blocks:
        return "The two texts are the same" + (
            " (ignoring the chosen differences)." if ignore_space or ignore_case else "."), (0, 0, 0)
    return "\n".join(m + ln for m, ln in out), (added, removed, blocks)


# ── stats ───────────────────────────────────────────────────────────────────
def stats(text, top=10):
    """A dict of counts for a text."""
    check_size(text)
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", text)
    lines = text.splitlines()
    nonblank = [ln for ln in lines if ln.strip()]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    sentences = [s for s in re.split(r"[.!?]+(?:\s+|$)", text) if s.strip()]
    lower = [w.lower() for w in words]
    common = Counter(w for w in lower if len(w) > 2).most_common(top)
    n = len(words)
    return {
        "characters": len(text),
        "characters_no_spaces": len(re.sub(r"\s", "", text)),
        "words": n,
        "unique_words": len(set(lower)),
        "lines": len(lines),
        "non_blank_lines": len(nonblank),
        "paragraphs": len(paras),
        "sentences": len(sentences),
        "longest_line": max((len(ln) for ln in lines), default=0),
        "avg_word_length": round(sum(len(w) for w in words) / n, 1) if n else 0.0,
        "reading_minutes": round(n / 220.0, 1),
        "speaking_minutes": round(n / 130.0, 1),
        "common": common,
    }


def stats_report(text):
    s = stats(text)
    rows = [("Characters", s["characters"]),
            ("Characters without spaces", s["characters_no_spaces"]),
            ("Words", s["words"]), ("Different words", s["unique_words"]),
            ("Lines", s["lines"]), ("Lines that are not blank", s["non_blank_lines"]),
            ("Paragraphs", s["paragraphs"]), ("Sentences", s["sentences"]),
            ("Longest line", f"{s['longest_line']} characters"),
            ("Average word length", s["avg_word_length"]),
            ("Reading time", f"about {s['reading_minutes']} min"),
            ("Speaking time", f"about {s['speaking_minutes']} min")]
    out = [f"{k}: {v}" for k, v in rows]
    if s["common"]:
        out.append("")
        out.append("Most used words (3+ letters):")
        out.extend(f"  {w}  x{c}" for w, c in s["common"])
    return "\n".join(out)
