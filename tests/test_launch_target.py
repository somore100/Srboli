import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import launch_target as lt

fails = 0
def check(n, c, i=""):
    global fails
    if not c:
        fails += 1; print("FAIL", n, i)

check("extract", lt.extract_open(["m.py", "--open", "paint", "-x"]) == ("paint", ["m.py", "-x"]))
check("extract =", lt.extract_open(["m.py", "--open=drawing"]) == ("drawing", ["m.py"]))
check("extract none", lt.extract_open(["m.py"]) == (None, ["m.py"]))
check("extract dangling", lt.extract_open(["m.py", "--open"]) == (None, ["m.py", "--open"]))
S = ["drawing", "precision_canvas", "pdf_tools", "pomodoro", "basic_tools"]
L = {"drawing": "Drawing", "precision_canvas": "Precision Canvas", "pdf_tools": "PDF Tools", "pomodoro": "Pomodoro", "basic_tools": "Basic Tools"}
A = {"drawing": ["paint", "sketch"], "basic_tools": ["calculator"]}
r = lambda t: lt.resolve(t, S, L, A)
check("route id", r("drawing") == "drawing")
check("label", r("PDF Tools") == "pdf_tools" and r("pdf-tools") == "pdf_tools")
check("alias", r("paint") == "drawing" and r("Calculator") == "basic_tools")
check("prefix unique", r("pomo") == "pomodoro" and r("precision") == "precision_canvas")
check("prefix ambiguous", r("p") is None)
check("unknown/empty", r("zzz") is None and r("") is None and r("  ") is None)
check("real registry", lt.resolve("paint") == "drawing" and lt.resolve("studio") == "full_editor"
      and lt.resolve("overlay sandbox") == "overlay_sandbox", (lt.resolve("paint"), lt.resolve("studio")))
check("tool argv", lt.tool_argv(["py", "m.py"], "drawing") == ["py", "m.py", "--open", "drawing"])
check("file argv", lt.open_file_argv("/a b") == ["xdg-open", "/a b"])
ch = lt.tool_choices(S, L)
check("choices", ch[0] == ("Drawing", "drawing") and len(ch) == 5)
check("choices real", len(lt.tool_choices()) >= 52)
d = tempfile.mkdtemp()
check("no request", lt.take_request(d) is None)
check("write", lt.write_request(d, "paint"))
check("take once", lt.take_request(d) == "paint" and lt.take_request(d) is None)
lt.write_request(d, "old")
check("stale dropped", lt.take_request(d, now=time.time() + 100) is None and not os.path.exists(lt.request_path(d)))
check("write fails quietly", not lt.write_request("/proc/nope/x", "a"))
print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
