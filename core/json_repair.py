# core/json_repair.py - read the JSON an AI chatbot pasted, fixing its usual slips.
#
# Chatbots wrap JSON in ``` fences or chatter, use curly quotes, leave trailing
# commas and put // comments in. loads_tolerant() fixes those, tells you what it
# changed, and when the text is still broken raises a ValueError that names the
# line and column and shows the bad spot - short enough to copy back to the AI.
import json
import re

FENCE = re.compile(r"```[a-zA-Z]*\s*(.*?)```", re.S)
TRAILING_COMMA = re.compile(r",(\s*[}\]])")
CURLY = {"“": '"', "”": '"', "‘": "'", "’": "'"}


def _fix_quotes(text):
    return text.replace("\u201c", '"').replace("\u201d", '"')


def _strip_comments(text):
    """Remove // line comments that sit outside strings."""
    out, i, in_str, esc = [], 0, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and text[i + 1:i + 2] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def describe_error(text, err):
    """'Line 5, column 3: Expecting ',' delimiter' plus the offending line."""
    line, col = getattr(err, "lineno", 0), getattr(err, "colno", 0)
    msg = getattr(err, "msg", str(err))
    if not line:
        return msg
    lines = text.splitlines() or [""]
    bad = lines[min(line, len(lines)) - 1]
    shown = bad if len(bad) <= 120 else bad[max(0, col - 60):col + 60]
    return f"Line {line}, column {col}: {msg}\n{shown.strip()}"


def loads_tolerant(text, openers=("{", "[")):
    """Return (data, notes). `notes` lists the repairs made. Raises ValueError."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to read - the text is empty.")
    notes = []
    m = FENCE.search(text)
    if m:
        text = m.group(1).strip()
        notes.append("removed the ``` code fence")
    try:
        return json.loads(text), notes
    except ValueError as first:
        err = first
    found = [(text.find(o), o) for o in openers if o in text]
    if found:                                 # drop chatter before / after the JSON
        a, op = min(found)
        b = text.rfind("}" if op == "{" else "]")
        if b > a and (a or b < len(text) - 1):
            text = text[a:b + 1]
            notes.append("cut the text around the JSON")
    for note, fn in (("replaced curly quotes", _fix_quotes),
                     ("removed // comments", _strip_comments),
                     ("removed trailing commas", lambda t: TRAILING_COMMA.sub(r"\1", t))):
        fixed = fn(text)
        if fixed == text:
            continue
        try:
            return json.loads(fixed), notes + [note]
        except ValueError:
            text, notes = fixed, notes + [note]
    try:
        return json.loads(text), notes
    except ValueError as e:
        if not any(o in text for o in openers):
            raise ValueError("That is not JSON (no { ... } found).")
        raise ValueError("That is not valid JSON.\n" + describe_error(text, e))
