# core/learn_core.py - "Learn" engine: import an AI-written course (JSON),
# run lessons, keep XP / streak / per-lesson progress. No Kivy in here.
#
# Files, both under app_data.subdir("learn"):
#   plans/<plan_id>.json   the imported courses, normalized
#   progress.json          {"xp", "streak", "last_day", "plans": {id: {...}}}
#
# Course format (what the AI is asked to produce, see PROMPT):
#   {"title", "topic", "level", "description",
#    "units": [{"title", "lessons": [{"title", "intro",
#       "items": [ {"type": "choice"|"multi"|"type"|"tf"|"info", ...} ]}]}]}
import datetime
import hashlib
import json
import os
import re

import app_data

LEARN_DIR = "learn"
PROGRESS_FILE = "progress.json"
ITEM_TYPES = ("choice", "multi", "type", "tf", "info")
XP_PER_CORRECT = 10
XP_LESSON_BONUS = 20

PROMPT = """\
You are a course author. Make a step-by-step course that teaches: {topic}
My level: {level}. Reply with ONLY one JSON object (no markdown fences, no
commentary) in exactly this shape:

{{
  "title": "Course title",
  "topic": "{topic}",
  "level": "{level}",
  "description": "One or two sentences.",
  "units": [
    {{
      "title": "Unit title",
      "lessons": [
        {{
          "title": "Lesson title",
          "intro": "Short explanation of the idea (3-8 sentences, plain text).",
          "items": [
            {{"type": "info", "text": "A worked example or tip."}},
            {{"type": "choice", "q": "Question?", "options": ["A", "B", "C"],
              "answer": 1, "explain": "Why B is right."}},
            {{"type": "multi", "q": "Pick all that apply", "options": ["A", "B", "C"],
              "answer": [0, 2], "explain": "..."}},
            {{"type": "tf", "q": "A statement.", "answer": true, "explain": "..."}},
            {{"type": "type", "q": "What does print(2+3) show?",
              "answer": ["5"], "explain": "..."}}
          ]
        }}
      ]
    }}
  ]
}}

Rules: "answer" for choice is the 0-based index of the right option; for multi
a list of indexes; for tf true/false; for type a list of accepted answers
(short, lowercase-insensitive). Every lesson needs an "intro" and 4-8 items
with at least 3 questions. 3-6 units, 3-6 lessons each, easy to hard.
Questions must be answerable from the intro and earlier lessons.
"""


def build_prompt(topic, level="beginner"):
    topic = (topic or "").strip() or "<your topic>"
    level = (level or "").strip() or "beginner"
    return PROMPT.format(topic=topic, level=level)


# ---- parsing / validation ------------------------------------------------
def _extract_json(text):
    """Accept raw JSON, or JSON wrapped in ``` fences / chatter."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to import - the text is empty.")
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except ValueError as e:
                raise ValueError(f"That is not valid JSON: {e}")
        raise ValueError("That is not JSON (no { ... } found).")


def _s(v, default=""):
    return v.strip() if isinstance(v, str) else default


def _norm_item(it, where, errors):
    if not isinstance(it, dict):
        errors.append(f"{where}: item is not an object")
        return None
    t = _s(it.get("type")).lower()
    if t == "fill":
        t = "type"
    if t not in ITEM_TYPES:
        errors.append(f"{where}: unknown type {it.get('type')!r}")
        return None
    if t == "info":
        text = _s(it.get("text")) or _s(it.get("q"))
        if not text:
            errors.append(f"{where}: info item has no text")
            return None
        return {"type": "info", "text": text}
    q = _s(it.get("q")) or _s(it.get("question"))
    if not q:
        errors.append(f"{where}: question text missing")
        return None
    out = {"type": t, "q": q, "explain": _s(it.get("explain"))}
    if t in ("choice", "multi"):
        opts = it.get("options")
        if not (isinstance(opts, list) and 2 <= len(opts) <= 8
                and all(isinstance(o, (str, int, float)) for o in opts)):
            errors.append(f"{where}: needs 2-8 options")
            return None
        opts = [str(o) for o in opts]
        ans = it.get("answer")
        if t == "choice":
            if isinstance(ans, list) and len(ans) == 1:
                ans = ans[0]
            if not (isinstance(ans, int) and not isinstance(ans, bool)
                    and 0 <= ans < len(opts)):
                errors.append(f"{where}: answer must be an option index")
                return None
        else:
            if isinstance(ans, int) and not isinstance(ans, bool):
                ans = [ans]
            if not (isinstance(ans, list) and ans and all(
                    isinstance(a, int) and 0 <= a < len(opts) for a in ans)):
                errors.append(f"{where}: answer must be a list of indexes")
                return None
            ans = sorted(set(ans))
        out.update(options=opts, answer=ans)
    elif t == "tf":
        ans = it.get("answer")
        if isinstance(ans, str) and ans.strip().lower() in ("true", "false"):
            ans = ans.strip().lower() == "true"
        if not isinstance(ans, bool):
            errors.append(f"{where}: answer must be true or false")
            return None
        out["answer"] = ans
    else:  # type
        ans = it.get("answer")
        if isinstance(ans, (str, int, float)) and not isinstance(ans, bool):
            ans = [ans]
        if not (isinstance(ans, list) and ans):
            errors.append(f"{where}: answer must be a text or list of texts")
            return None
        out["answer"] = [str(a) for a in ans if str(a).strip()]
        if not out["answer"]:
            errors.append(f"{where}: answer is empty")
            return None
    return out


def parse_plan(text):
    """Return (plan, warnings). Raises ValueError with a readable message."""
    data = _extract_json(text)
    if not isinstance(data, dict):
        raise ValueError("The top level must be an object { ... }.")
    units_in = data.get("units")
    if not isinstance(units_in, list) or not units_in:
        raise ValueError('Missing "units" (a list of units with lessons).')
    warnings = []
    units = []
    for ui, u in enumerate(units_in, 1):
        if not isinstance(u, dict):
            warnings.append(f"unit {ui}: not an object, skipped")
            continue
        lessons = []
        for li, l in enumerate(u.get("lessons") or [], 1):
            where = f"unit {ui} lesson {li}"
            if not isinstance(l, dict):
                warnings.append(f"{where}: not an object, skipped")
                continue
            items = []
            for ii, it in enumerate(l.get("items") or [], 1):
                n = _norm_item(it, f"{where} item {ii}", warnings)
                if n:
                    items.append(n)
            if not any(i["type"] != "info" for i in items):
                warnings.append(f"{where}: no usable questions, skipped")
                continue
            lessons.append({"title": _s(l.get("title")) or f"Lesson {li}",
                            "intro": _s(l.get("intro")), "items": items})
        if lessons:
            units.append({"title": _s(u.get("title")) or f"Unit {ui}",
                          "lessons": lessons})
        else:
            warnings.append(f"unit {ui}: no usable lessons, skipped")
    if not units:
        raise ValueError("No usable lessons found." + (
            "\n" + "\n".join(warnings[:6]) if warnings else ""))
    plan = {"title": _s(data.get("title")) or "Untitled course",
            "topic": _s(data.get("topic")), "level": _s(data.get("level")),
            "description": _s(data.get("description")), "units": units}
    plan["id"] = plan_id(plan)
    return plan, warnings


def plan_id(plan):
    body = json.dumps(plan.get("units"), sort_keys=True, ensure_ascii=False)
    h = hashlib.sha1((plan.get("title", "") + body).encode("utf-8"))
    return "p_" + h.hexdigest()[:10]


# ---- answers --------------------------------------------------------------
def _norm_text(s):
    s = re.sub(r"\s+", " ", str(s).strip().lower())
    return s.strip(" .!;")


def check_answer(item, given):
    """given: int (choice) / list of int (multi) / bool (tf) / str (type)."""
    t = item["type"]
    if t == "choice":
        return given == item["answer"]
    if t == "multi":
        return sorted(set(given or [])) == item["answer"]
    if t == "tf":
        return given is item["answer"]
    if t == "type":
        g = _norm_text(given or "")
        return bool(g) and any(g == _norm_text(a) for a in item["answer"])
    return True


def answer_text(item):
    t = item["type"]
    if t == "choice":
        return item["options"][item["answer"]]
    if t == "multi":
        return ", ".join(item["options"][i] for i in item["answer"])
    if t == "tf":
        return "True" if item["answer"] else "False"
    if t == "type":
        return " / ".join(item["answer"])
    return ""


# ---- storage --------------------------------------------------------------
def _dir():
    return app_data.subdir(LEARN_DIR)


def _plans_dir():
    p = os.path.join(_dir(), "plans")
    os.makedirs(p, exist_ok=True)
    return p


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def save_plan(plan):
    _atomic_write_json(os.path.join(_plans_dir(), plan["id"] + ".json"), plan)
    return plan["id"]


def load_plan(pid):
    try:
        with open(os.path.join(_plans_dir(), pid + ".json"),
                  encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def list_plans():
    out = []
    for fn in sorted(os.listdir(_plans_dir())):
        if fn.endswith(".json"):
            p = load_plan(fn[:-5])
            if p:
                out.append(p)
    return out


def delete_plan(pid):
    try:
        os.remove(os.path.join(_plans_dir(), pid + ".json"))
    except OSError:
        pass
    st = load_progress()
    st["plans"].pop(pid, None)
    save_progress(st)


def load_progress():
    try:
        with open(os.path.join(_dir(), PROGRESS_FILE), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    if not isinstance(st, dict):
        st = {}
    st.setdefault("xp", 0)
    st.setdefault("streak", 0)
    st.setdefault("last_day", "")
    if not isinstance(st.get("plans"), dict):
        st["plans"] = {}
    return st


def save_progress(st):
    _atomic_write_json(os.path.join(_dir(), PROGRESS_FILE), st)


def lesson_key(ui, li):
    return f"{ui}.{li}"


def lesson_done(st, pid, ui, li):
    return lesson_key(ui, li) in st["plans"].get(pid, {}).get("done", {})


def best_score(st, pid, ui, li):
    return st["plans"].get(pid, {}).get("done", {}).get(lesson_key(ui, li))


def record_lesson(st, pid, ui, li, correct, total, today=None):
    """Update xp / streak / best score in `st`. Returns the xp gained."""
    today = today or datetime.date.today().isoformat()
    pct = int(round(100 * correct / total)) if total else 100
    done = st["plans"].setdefault(pid, {}).setdefault("done", {})
    k = lesson_key(ui, li)
    first = k not in done
    done[k] = max(pct, done.get(k, 0))
    gained = correct * XP_PER_CORRECT + (XP_LESSON_BONUS if first else 0)
    st["xp"] += gained
    last = st.get("last_day", "")
    if last != today:
        try:
            gap = (datetime.date.fromisoformat(today)
                   - datetime.date.fromisoformat(last)).days if last else None
        except ValueError:
            gap = None
        st["streak"] = st["streak"] + 1 if gap == 1 else 1
        st["last_day"] = today
    return gained


def current_streak(st, today=None):
    """Streak as displayed: 0 if the last study day is older than yesterday."""
    today = datetime.date.fromisoformat(today) if today \
        else datetime.date.today()
    try:
        last = datetime.date.fromisoformat(st.get("last_day", ""))
    except ValueError:
        return 0
    return st["streak"] if (today - last).days <= 1 else 0


def next_lesson(st, plan):
    """(unit_index, lesson_index) of the first unfinished lesson, or None."""
    for ui, u in enumerate(plan["units"]):
        for li, _ in enumerate(u["lessons"]):
            if not lesson_done(st, plan["id"], ui, li):
                return ui, li
    return None


def plan_counts(st, plan):
    total = sum(len(u["lessons"]) for u in plan["units"])
    done = sum(1 for ui, u in enumerate(plan["units"])
               for li, _ in enumerate(u["lessons"])
               if lesson_done(st, plan["id"], ui, li))
    return done, total
