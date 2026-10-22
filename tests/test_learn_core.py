# tests/test_learn_core.py - Learn engine (import, answers, progress). No Kivy.
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

tmp_home = tempfile.mkdtemp()
os.environ["HOME"] = tmp_home
import app_data
app_data._APP_ROOT = tmp_home
import core.learn_core as L

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

PLAN = {
    "title": "Python basics", "topic": "python", "level": "beginner",
    "units": [{"title": "Start", "lessons": [
        {"title": "print", "intro": "print shows text.", "items": [
            {"type": "info", "text": "tip"},
            {"type": "choice", "q": "Which prints?", "options": ["a", "print()"],
             "answer": 1},
            {"type": "multi", "q": "pick", "options": ["a", "b", "c"],
             "answer": [2, 0]},
            {"type": "tf", "q": "x", "answer": "true"},
            {"type": "fill", "q": "2+3?", "answer": 5},
        ]},
        {"title": "bad", "items": [{"type": "info", "text": "only info"}]},
    ]}, {"title": "Empty", "lessons": []}],
}

plan, warn = L.parse_plan(json.dumps(PLAN))
check("title", plan["title"], "Python basics")
check("bad lesson + empty unit dropped", (len(plan["units"]), len(plan["units"][0]["lessons"])), (1, 1))
check("warnings mention skips", len(warn), 2)
items = plan["units"][0]["lessons"][0]["items"]
check("multi answer sorted", items[2]["answer"], [0, 2])
check("tf string -> bool", items[3]["answer"], True)
check("fill -> type, number answer", (items[4]["type"], items[4]["answer"]), ("type", ["5"]))
check("id stable", L.parse_plan(json.dumps(PLAN))[0]["id"], plan["id"])

# wrapped in fences and chatter
wrapped = "Sure! Here it is:\n```json\n" + json.dumps(PLAN) + "\n```\nEnjoy"
check("fenced json", L.parse_plan(wrapped)[0]["id"], plan["id"])
check("chatter without fences", L.parse_plan("blah " + json.dumps(PLAN) + " bye")[0]["id"], plan["id"])

for name, txt in [("empty", ""), ("not json", "hello"), ("list", "[1]"),
                  ("no units", "{}"), ("units unusable", '{"units":[{"lessons":[]}]}')]:
    try:
        L.parse_plan(txt); ok = False
    except ValueError:
        ok = True
    check("rejects " + name, ok, True)

# answers
c, m, t, ty = items[1], items[2], items[3], items[4]
check("choice right", L.check_answer(c, 1), True)
check("choice wrong", L.check_answer(c, 0), False)
check("multi right", L.check_answer(m, [0, 2]), True)
check("multi partial", L.check_answer(m, [0]), False)
check("tf", (L.check_answer(t, True), L.check_answer(t, False)), (True, False))
check("type lenient", L.check_answer(ty, "  5. "), True)
check("type wrong/empty", (L.check_answer(ty, "6"), L.check_answer(ty, "")), (False, False))
check("answer_text", (L.answer_text(c), L.answer_text(m), L.answer_text(t), L.answer_text(ty)),
      ("print()", "a, c", "True", "5"))

# storage + progress
pid = L.save_plan(plan)
check("list_plans", [p["id"] for p in L.list_plans()], [pid])
st = L.load_progress()
check("next lesson fresh", L.next_lesson(st, plan), (0, 0))
g = L.record_lesson(st, pid, 0, 0, 3, 4, today="2026-01-01")
check("xp first run", g, 3 * 10 + 20)
check("score pct", L.best_score(st, pid, 0, 0), 75)
g2 = L.record_lesson(st, pid, 0, 0, 4, 4, today="2026-01-02")
check("no bonus on repeat", g2, 40)
check("best score kept/raised", L.best_score(st, pid, 0, 0), 100)
check("streak consecutive", st["streak"], 2)
L.record_lesson(st, pid, 0, 0, 1, 4, today="2026-01-02")
check("same day keeps streak", st["streak"], 2)
check("best not lowered", L.best_score(st, pid, 0, 0), 100)
L.record_lesson(st, pid, 0, 0, 1, 4, today="2026-01-09")
check("gap resets streak", st["streak"], 1)
check("shown streak decays", (L.current_streak(st, "2026-01-10"), L.current_streak(st, "2026-01-12")), (1, 0))
check("plan complete", (L.next_lesson(st, plan), L.plan_counts(st, plan)), (None, (1, 1)))
L.save_progress(st)
check("progress persists", L.load_progress()["xp"], st["xp"])
L.delete_plan(pid)
check("delete clears plan+progress", (L.list_plans(), L.load_progress()["plans"]), ([], {}))
check("prompt has topic", "teaches: rust" in L.build_prompt("rust", "advanced") and "advanced" in L.build_prompt("rust", "advanced"), True)

print("FAILED" if fails else "ALL OK")
sys.exit(1 if fails else 0)
