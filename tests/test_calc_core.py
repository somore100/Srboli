import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import calc_core as cc  # noqa: E402

fails = 0


def check(name, cond, info=""):
    global fails
    if not cond:
        fails += 1
        print("FAIL", name, info)


def press(c, text):
    for ch in text:
        if ch in "0123456789.":
            c.digit(ch)
        elif ch in "+-*/":
            c.op(ch)
        elif ch == "=":
            c.equals()
    return c


check("precedence", press(cc.Calc(), "2+3*4=").entry == "14")
check("decimals", press(cc.Calc(), "0.1+0.2=").entry == "0.3")
check("second dot ignored", press(cc.Calc(), "1.2.3").entry == "1.23")
check("leading zero replaced", press(cc.Calc(), "007").entry == "7")
check("dot first", press(cc.Calc(), ".5").entry == "0.5")
c = press(cc.Calc(), "9" * 30)
check("entry capped", len(c.entry) == cc.MAX_ENTRY)
c = press(cc.Calc(), "12")
c.back(); check("back", c.entry == "1")
c.back(); check("back to zero", c.entry == "0")
c.back(); check("back at zero", c.entry == "0")
c = press(cc.Calc(), "5"); c.negate(); check("negate", c.entry == "-5")
c.negate(); check("negate twice", c.entry == "5")
c = cc.Calc(); c.negate(); check("negate zero", c.entry == "0")
c = press(cc.Calc(), "8-"); c.negate()
c = press(cc.Calc(), "3"); c.negate(); c.op("*"); c.digit("2"); c.equals()
check("negative operand", c.entry == "-6")
c = press(cc.Calc(), "5"); c.op("+"); c.op("*"); c.digit("2"); c.equals()
check("operator replaced", c.entry == "10", c.entry)
c = press(cc.Calc(), "2"); c.percent(); check("percent", c.entry == "0.02")
c = press(cc.Calc(), "16"); c.sqrt(); check("sqrt", c.entry == "4")
c = press(cc.Calc(), "5"); c.negate(); c.sqrt(); check("sqrt negative", c.entry == "Error")
c = press(cc.Calc(), "1/0="); check("divide by zero", c.entry == "Error" and c.expr == "")
c = press(cc.Calc(), "4"); c.inverse(); check("inverse", c.entry == "0.25")
c = cc.Calc(); c.inverse(); check("inverse zero", c.entry == "Error")
c = press(cc.Calc(), "7"); c.square(); check("square", c.entry == "49")
c.digit("3"); check("digit after result starts fresh", c.entry == "3")
c = press(cc.Calc(), "1/0="); c.digit("4"); check("digit after error recovers", c.entry == "4")
c = press(cc.Calc(), "1/0="); c.op("+"); c.back(); c.negate(); check("keys ignored on Error", c.entry == "Error")
c.clear(); check("clear", c.entry == "0" and c.expr == "")
c = cc.Calc()
for i in range(25):
    press(c, f"{i}+1="); c.clear()
check("history capped at 20", len(c.history) == 20 and c.history[-1] == "24+1 = 25")
c = cc.Calc(); c.const(math.pi); check("constant", c.entry == "3.141592654")
c = press(cc.Calc(), "9" * 15); c.square(); c.square(); c.square(); check("overflow is Error or finite", c.entry == "Error" or float(c.entry) > 0)
check("junk keys ignored", press(cc.Calc(), "a").entry == "0" and cc.Calc().digit("12") is None)
check("fmt", cc.fmt(3.0) == "3" and cc.fmt(float("nan")) == "Error" and cc.fmt(float("inf")) == "Error" and cc.fmt(-0.5) == "-0.5")

for bad in ("__import__('os')", "2**3", "abs(1)", "1 if 1 else 2", "", "(1+", "True", "[1]", "1/0", "9" * 400 + "*9" * 50):
    try:
        cc.safe_eval(bad)
        check("reject " + bad[:20], False)
    except ValueError:
        pass
check("safe eval ok", cc.safe_eval("(1+2)*-3") == -9.0)

print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
