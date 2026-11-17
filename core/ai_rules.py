# core/ai_rules.py - turn a plain-words description into a File Sorter rule.
# The model only proposes; every field, operator and value it sends is checked
# here against what File Sorter really supports, and the user sees the rule in
# the Rule Editor (and saves it, or not) before anything exists.

from core import ai_core
from core import file_sorter_core as fs

_ACTION_NOTE = {
    "move": 'move: {"type":"move","dest":"/full/path/of/folder"}',
    "copy": 'copy: {"type":"copy","dest":"/full/path/of/folder"}',
    "rename": 'rename: {"type":"rename","pattern":"{name}{ext}"} (tokens {name} {ext} {counter} {date})',
    "delete": 'delete: {"type":"delete"}',
}


def system_prompt():
    lines = []
    for key in fs.FIELD_ORDER:
        spec = fs.FIELDS[key]
        extra = ""
        if spec["kind"] == "category":
            extra = " value is one of: " + ", ".join(fs.FILE_TYPE_NAMES)
        elif spec["kind"] == "text_list":
            extra = " value is comma-separated extensions without dots, e.g. jpg,png"
        elif spec["kind"] == "size":
            extra = ' value like "500 MB" (units B KB MB GB)'
        elif spec["kind"] == "days":
            extra = " value is a number of days"
        elif spec["kind"] == "bool":
            extra = " no value"
        lines.append(f'- field "{key}" ({spec["label"]}), ops: '
                     f'{", ".join(spec["ops"])};{extra}')
    return (
        "You write one rule for a file-sorting app. A rule is: IF conditions "
        "THEN one action. Reply with ONLY a JSON object, no other text:\n"
        '{"logic":"AND" or "OR","conditions":[{"field":...,"op":...,"value":...}],'
        '"action":{...}}\n\nAllowed condition fields:\n' + "\n".join(lines)
        + "\n\nAllowed actions:\n" + "\n".join("- " + v for v in _ACTION_NOTE.values())
        + "\n\nUse only these fields, ops and actions. Never use the same field "
          "twice with the same op and value. Give folder paths in full. If the "
          "request can't be expressed with these, reply {\"error\":\"short reason\"}.")


def clean_rule(obj):
    """(rule, note) from the model's object; rule is None when unusable."""
    if not isinstance(obj, dict):
        return None, "The model's answer wasn't a rule."
    if obj.get("error"):
        return None, f"The model says it can't be done: {obj['error']}"
    notes = []
    conds = []
    for c in obj.get("conditions") or []:
        if not isinstance(c, dict):
            continue
        field, op = c.get("field"), c.get("op")
        spec = fs.FIELDS.get(field)
        if not spec or op not in spec["ops"]:
            notes.append(f"dropped an unsupported condition ({field} {op})")
            continue
        value = c.get("value", "")
        value = "" if value is None else str(value).strip()
        kind = spec["kind"]
        if kind == "category":
            match = next((n for n in fs.FILE_TYPE_NAMES
                          if n.lower() == value.lower()), None)
            if not match:
                notes.append(f"dropped a condition with unknown file type '{value}'")
                continue
            value = match
        elif kind == "text_list":
            value = ",".join(v.strip().lstrip(".").lower()
                             for v in value.split(",") if v.strip())
        if kind == "bool" or op == "is_missing":
            value = ""
        elif not value:
            notes.append(f"dropped a condition with no value ({field})")
            continue
        conds.append({"field": field, "op": op, "value": value})
    if not conds:
        return None, "No usable condition came back."
    logic = "OR" if str(obj.get("logic", "AND")).upper() == "OR" else "AND"
    act = obj.get("action")
    if not isinstance(act, dict) or act.get("type") not in fs.ACTION_TYPES:
        return None, "The model gave no usable action."
    kind = act["type"]
    if kind in ("move", "copy"):
        dest = str(act.get("dest") or "").strip()
        if not dest:
            return None, "The model gave no destination folder."
        action = {"type": kind, "dest": dest}
    elif kind == "rename":
        action = {"type": "rename",
                  "pattern": str(act.get("pattern") or "{name}{ext}").strip()}
    else:
        # A rule written by the AI never deletes behind your back: the
        # editor opens with "ask first" and it is you who saves it.
        action = {"type": "delete", "auto_delete": False}
        notes.append("delete will ask before each file")
    bad = fs.condition_problem(conds, logic)
    if bad:
        return None, "The model's rule doesn't work: " + bad
    return {"logic": logic, "conditions": conds, "action": action}, "; ".join(notes)


def rule_from_words(description, cfg=None):
    """Returns (rule, note). Raises ai_core.AIError when the model can't be reached."""
    description = (description or "").strip()
    if not description:
        raise ai_core.AIError("Describe the rule first.")
    text = ai_core.chat(system_prompt(), description, cfg, max_tokens=800)
    obj = ai_core.extract_json(text)
    if obj is None:
        return None, "The model didn't answer with a rule. Try again, or say it more simply."
    return clean_rule(obj)
