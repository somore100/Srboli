# tests/test_learn_modes.py - Learn: modes, optional points, review, practice, AI follow-up parsing.
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
tmp = tempfile.mkdtemp()
os.environ["HOME"] = tmp
import app_data
app_data._APP_ROOT = tmp
import core.learn_core as L

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")

def course(mode=None, lessons=1):
    d = {"title": "T", "topic": "t", "units": [{"title": "U", "lessons": [
        {"title": f"L{i}", "intro": "x", "items": [
            {"type": "tf", "q": f"q{i}a", "answer": True, "explain": "e"},
            {"type": "choice", "q": f"q{i}b", "options": ["a", "b"], "answer": 1}]}
        for i in range(lessons)]}]}
    if mode:
        d["mode"] = mode
    import json
    return L.parse_plan(json.dumps(d))[0]

# modes
check("derive lesson", course(lessons=1)["mode"], "lesson")
check("derive course", course(lessons=3)["mode"], "course")
check("explicit general", course("general", 3)["mode"], "general")
check("bad mode falls back", course("nonsense", 3)["mode"], "course")
for m in L.MODES:
    check("prompt " + m, "Reply with ONLY" in L.build_prompt("x", "beginner", m), True)
check("lesson prompt single", "ONE lesson" in L.build_prompt("x", mode="lesson"), True)
check("general prompt", '"mode": "general"' in L.build_prompt("x", mode="general"), True)
check("default prompt unchanged", "3-6 units" in L.build_prompt("x"), True)
g = course("general", 3)
st = L.load_progress()
check("general all open", [L.lesson_state(st, g, 0, i) for i in range(3)][1:], ["open", "open"])
c = course(lessons=3)
check("course locks", L.lesson_state(st, c, 0, 2), "locked")

# optional points
pid = c["id"]
check("graded default", L.is_graded(st, pid), True)
x0 = st["xp"]
check("graded xp", L.record_lesson(st, pid, 0, 0, 2, 2, today="2026-01-01") > 0, True)
L.set_graded(st, pid, False)
x1 = st["xp"]
check("ungraded gives 0", L.record_lesson(st, pid, 0, 1, 2, 2, today="2026-01-02"), 0)
check("ungraded keeps xp", st["xp"], x1)
check("ungraded still done", L.lesson_done(st, pid, 0, 1), True)
check("ungraded streak counts", st["streak"], 2)
check("ungraded practice", L.record_practice(st, pid, 3, today="2026-01-02"), 0)
L.set_graded(st, pid, True)
check("practice xp", L.record_practice(st, pid, 3, today="2026-01-02"), 3 * L.XP_PER_PRACTICE)
L.set_graded(st, pid, False)
L.record_lesson(st, pid, 0, 2, 2, 2, today="2026-01-03")
check("ungraded no milestone xp", L.award_milestones(st, c, 0)[0], 0)

# review
q1 = c["units"][0]["lessons"][0]["items"][0]
q2 = c["units"][0]["lessons"][0]["items"][1]
recs = [L.make_record(q1, True, True), L.make_record(q2, 0, False),
        L.make_record(q2, 1, True, first=False)]
check("given text", recs[1]["given"], "a")
check("answer text", recs[1]["answer"], "b")
sm = L.review_summary(recs)
check("summary counts", (len(sm["right"]), len(sm["wrong"]), sm["total"], sm["pct"]), (1, 1, 2, 50))
check("empty summary", L.review_summary([])["pct"], 100)
check("given multi", L.given_text({"type": "multi", "options": ["a", "b", "c"]}, [2, 0]), "a, c")
check("given none", L.given_text({"type": "choice", "options": ["a"]}, None), "(nothing)")

# missed questions: remembered, then cleared once answered right
L.note_results(st, pid, recs)
check("missed stored", [m["q"] for m in L.missed_items(st, c)], [q2["q"]])
check("missed has no private keys", all(not k.startswith("_") for m in L.missed_items(st, c) for k in m), True)
L.note_results(st, pid, [L.make_record(q2, 1, True)])
check("missed cleared", L.missed_items(st, c), [])
many = [L.make_record({"type": "tf", "q": f"m{i}", "answer": True}, False, False) for i in range(60)]
L.note_results(st, pid, many)
check("missed capped", len(L.missed_items(st, c)), L.MAX_MISSED)

# mixed
import random
check("mixed size", len(L.mixed_items(c, 4, random.Random(1))), 4)
check("mixed no info", all(i["type"] != "info" for i in L.mixed_items(c, 99)), True)
check("mixed does not mutate", len(L.all_questions(c)), 6)

# AI follow-up prompt and parsing
p = L.build_followup_prompt(c, [recs[1]], 3)
check("followup prompt content", all(s in p for s in ("q0b", "They answered: a", "Correct: b", "Write 3 NEW")), True)
items, w = L.parse_items('Sure!\n```json\n{"items": [{"type": "tf", "q": "z", "answer": "true"}, {"type": "bogus"}, '
                         '{"type": "info", "text": "skip"}]}\n```')
check("parse items", [(i["type"], i["answer"]) for i in items], [("tf", True)])
check("parse bare list", len(L.parse_items('[{"type":"type","q":"r","answer":"5"}]')[0]), 1)
for bad in ("", "no json", '{"items": []}', '{"items": [{"type": "bogus"}]}', '{"x": 1}'):
    try:
        L.parse_items(bad)
        check("reject " + bad, "accepted", "rejected")
    except ValueError:
        pass
try:
    L.ai_followups(c, [])
    check("followup needs wrong", "ok", "error")
except Exception as e:
    check("followup needs wrong", type(e).__name__, "AIError")

print("FAILED" if fails else "ALL OK")
sys.exit(1 if fails else 0)
