import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import macro_core as mc  # noqa: E402

fails = 0


def check(name, cond, info=""):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name, info)


m = mc.Macro("t")
check("add click", m.add_click(0.5, 0.25) == 0 and m.actions[0]["interval_ms"] == 500)
check("add drag", m.add_drag(0.1, 0.1, 0.9, 0.9, 1000, 200) == 1 and m.actions[1]["duration_ms"] == 1000)
check("clamps", m.add_click(5, -3) == 2 and m.actions[2]["x"] == 1 and m.actions[2]["y"] == 0)
check("junk numbers", m.add_click("a", float("nan")) == 3 and m.actions[3]["x"] == 0.5)
check("remove last", m.remove_last()["kind"] == "click" and len(m.actions) == 3)
check("remove idx", m.remove(0)["x"] == 0.5 and len(m.actions) == 2 and m.remove(9) is None)
check("remove empty", mc.Macro().remove_last() is None)
check("update", m.update(1, interval_ms=1500) and m.actions[1]["interval_ms"] == 1500)
check("update drag dur", m.update(0, duration_ms=300) and m.actions[0]["duration_ms"] == 300)
check("update bad", not m.update(7, x=0) and not m.update(0, kind="zap"))
check("update clamps", m.update(0, interval_ms=10 ** 9) and m.actions[0]["interval_ms"] == mc.MAX_MS)
check("bad kind rejected", mc.clean_action({"kind": "x"}) is None and mc.clean_action(5) is None)

m = mc.Macro("p", loops=2, speed=2.0)
m.add_click(0.5, 0.5, 1000)
m.add_drag(0, 0, 1, 1, 400, 200)
ev = mc.plan(m, 100, 200)
check("plan count", len(ev) == 4)
hm = mc.Macro("h", actions=[{"kind": "click", "hold_ms": 1000, "interval_ms": 500}, {"kind": "click"}])
hev = mc.plan(hm, 10, 10)
check("hold shifts the next action", hev[0][6] == 1000 and hev[1][0] == 1500, [e[:1] + e[6:7] for e in hev])
check("hold defaults and clamps", mc.clean_action({"kind": "click"})["hold_ms"] == 0
      and mc.clean_action({"kind": "click", "hold_ms": -5})["hold_ms"] == 0 and "hold_ms" not in mc.clean_action({"kind": "drag"}))
check("add_click with hold", mc.Macro().add_click(0.5, 0.5, 100, 700) == 0)
check("plan times", [e[0] for e in ev] == [0, 500, 800, 1000 + 0 - 0 + 0] or [e[0] for e in ev] == [0, 500, 800, 1300], [e[0] for e in ev])
check("plan pixels", ev[0][2:4] == (50, 100) and ev[1][4:6] == (100, 200))
check("speed scales drag", ev[1][6] == 200)
check("total", mc.total_ms(m) > 0 and mc.total_ms(mc.Macro()) == 0)
check("loops 0 plans once", len(mc.plan(mc.Macro(loops=0, actions=m.actions), 10, 10)) == 2)

check("units", mc.to_ms(2, "s") == 2000 and mc.to_ms(250, "ms") == 250 and mc.to_ms("x", "s") == 0)
check("from_ms", mc.from_ms(3000) == (3, "s") and mc.from_ms(250) == (250, "ms") and mc.from_ms(0) == (0, "ms"))
check("safe name", mc.safe_name("../a/b?*") == "ab" and mc.safe_name("") == "macro")

d = tempfile.mkdtemp()
p = mc.save(m, d)
r = mc.load(p)
check("roundtrip", r.to_dict() == m.to_dict() and mc.list_saved(d) == [os.path.basename(p)])
check("load missing", mc.load(os.path.join(d, "nope.json")).actions == [])
check("from_dict junk", mc.Macro.from_dict(None).actions == [] and mc.Macro.from_dict({"actions": "x"}).actions == [])
big = mc.Macro("b", actions=[{"kind": "click"}] * 500)
check("cap actions", len(big.actions) == mc.MAX_ACTIONS and not big.add_click(0, 0))
check("list missing dir", mc.list_saved(os.path.join(d, "none")) == [])

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
