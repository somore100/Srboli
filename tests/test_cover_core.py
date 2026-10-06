# tests/test_cover_core.py — config normalisation, hotkey parsing and the
# control-line parser for the Cover feature. No Kivy, no tkinter, no display.
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["HOME"] = tempfile.mkdtemp()

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

import app_data
import core.cover_core as cc

# hotkeys
check("hk basic", cc.normalize_hotkey("Ctrl+Alt+H"), "<ctrl>+<alt>+h")
check("hk already pynput", cc.normalize_hotkey("<ctrl>+<shift>+<f5>"),
      "<ctrl>+<shift>+<f5>")
check("hk aliases", cc.normalize_hotkey("win+escape"), "<cmd>+<esc>")
check("hk empty", cc.normalize_hotkey("  "), "")
for bad in ("h", "ctrl+alt", "ctrl+a+b", "ctrl+bogus", "+"):
    try:
        cc.normalize_hotkey(bad); ok = False
    except ValueError:
        ok = True
    check(f"hk rejects {bad!r}", ok, True)

# normalisation
n = cc.normalize_config({"boxes": [
    {"id": "a", "x": "5", "y": "oops", "w": 1, "h": 99999999,
     "style": "weird", "color": "red", "opacity": 7, "hotkey": "nope"},
    {"id": "a"}, "junk"], "hotkeys": {"toggle": "ctrl+shift+t", "x": "y"}})
b0, b1, b2 = n["boxes"]
check("box clamp", (b0["x"], b0["y"], b0["w"], b0["h"]), (5, 100, 8, 20000))
check("box style fallback", b0["style"], "solid")
check("box bad colour", b0["color"], "#000000")
check("box opacity clamp", b0["opacity"], 1.0)
check("box bad hotkey dropped", b0["hotkey"], "")
check("duplicate ids made unique", b0["id"] != b1["id"], True)
check("junk box -> default", b2["w"], 400)
check("hotkey normalised", n["hotkeys"]["toggle"], "<ctrl>+<shift>+t")
check("unknown action ignored", "x" in n["hotkeys"], False)
check("garbage config", cc.normalize_config("x")["boxes"], [])

# save / load roundtrip in a temp data dir
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
cfg = cc.default_config()
cfg["boxes"].append(cc.default_box(1))
cc.save_config(cfg)
check("roundtrip", cc.load_config()["boxes"][0]["name"], "Box 1")
check("new id skips used", cc.new_box_id(cc.load_config())[0], "b2")

# control line
check("parse ok", cc.parse_control_line("tok toggle\n"), ("tok", "toggle", ""))
check("parse arg", cc.parse_control_line("tok toggle_box b2"),
      ("tok", "toggle_box", "b2"))
check("parse junk", cc.parse_control_line("x"), (None, None, ""))
check("token good", cc.token_ok(cc._token()), True)
check("token bad", cc.token_ok("nope"), False)
check("capture exclusion only on nt", cc.capture_exclusion_supported(),
      os.name == "nt")

print("\nFAILED" if fails else "\nall passed")
sys.exit(1 if fails else 0)
