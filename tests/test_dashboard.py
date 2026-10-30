# tests/test_dashboard.py - needs a display (xvfb-run -a python3 tests/test_dashboard.py)
# The Dashboard class is taken out of main.py's source (importing main.py would
# configure the real window) and run against the real settings code and a temp
# data folder.
import os, sys, ast, time, tempfile
from unittest.mock import MagicMock
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import screens.settings_screen as st
from screens.registry import GROUPS, LABELS
from core import dashboard_core as dash

from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.core.window import Window
visited = []
from screens.dashboard_screen import Dashboard as _D

def Dashboard(**kw):
    return _D(open_route=visited.append, version="t", **kw)

def tool_labels(d, include_heads=False):
    """Tile texts in order; the Pinned / Recent tiles are prefixed P: / R:."""
    out, mode = [], ""
    for w in reversed(d._grid.children):
        if isinstance(w, GridLayout):
            pre = {"Pinned": "P:", "Recent": "R:"}.get(mode, "")
            out += [pre + b.text.lstrip("* ") for b in reversed(w.children)]
        elif isinstance(w, Button):
            mode = ""
        elif getattr(w, "text", "").startswith("[b]"):
            mode = w.text[3:-4]
    return out

d = Dashboard(name="dashboard")
d.manager = MagicMock()
assert Window.width >= 700   # tests assume a desktop-sized window
heads = [w.text for w in reversed(d._grid.children) if isinstance(w, Button) and w.text.startswith("[")]
assert heads[0].startswith("[-]  Writing  (4)") and len(heads) == 6, heads
L = [t for t in tool_labels(d) if not t[:2] in ("R:", "P:")]; assert len(L) == 29, len(L)


# using a tool puts it in Recent after coming back
d._goto("chess"); d._goto("music")
assert visited == ["chess", "music"]
d.on_enter()
labels = tool_labels(d)
assert labels[:2] == ["R:Music Player", "R:Chess"], labels[:3]
print("recent row OK")

# collapse a section: its tools disappear, header flips, state survives a new Dashboard
d._toggle_section("fun")
heads = [w.text for w in reversed(d._grid.children) if isinstance(w, Button) and w.text.startswith("[")]
assert [h for h in heads if "Fun" in h] == ["[+]  Fun  (5)"], heads
assert "Minesweeper" not in tool_labels(d)
d2 = Dashboard(name="d2"); d2.manager = MagicMock()
assert "Minesweeper" not in tool_labels(d2) and "R:Chess" in tool_labels(d2)
d2._toggle_section("fun"); assert "Minesweeper" in tool_labels(d2)
print("collapse + persistence OK")

# search
d2._search.text = "edit"
assert tool_labels(d2) == ["Text Editor", "Full Editor"], tool_labels(d2)
d2._search.text = "zzzz"
assert any("No tool matches" in getattr(w, "text", "") for w in d2._grid.children)
d2._search.text = ""
assert "Minesweeper" in tool_labels(d2)
print("search OK")

# unchanged list is not rebuilt (no flash on Back)
before = list(d2._grid.children); d2.on_enter(); assert list(d2._grid.children) == before
print("no rebuild when nothing changed OK")

# hiding a tool in Settings removes it everywhere, including Recent
cfg = st.load_settings(); cfg["hidden"] = ["chess"]; st.save_settings(cfg)
d2.on_enter()
assert not any("Chess" in t for t in tool_labels(d2)), tool_labels(d2)[:5]

# the Settings screen can't wipe the Dashboard's state with a stale copy
stale = st.load_settings()
st.update_dashboard_state(recent=["spin"], collapsed=["media"])
stale["hidden"] = []; st.save_settings(stale)                      # an old copy saved later
now = st.load_settings()
assert now["recent"] == ["spin"] and now["collapsed"] == ["media"] and now["hidden"] == [], now
print("stale Settings copy can't overwrite recents/collapsed OK")

# Settings moves only within a section
sc = st.SettingsScreen(name="s"); time.sleep(0.3)
sc._cfg = st.load_settings()
order0 = list(sc._cfg["order"])
sc._selected = "text_editor"; sc._move_selected(-1)
assert sc._cfg["order"] == order0, "first of a section can't move up"
sc._move_selected(1)
o = sc._cfg["order"]
sec = [r for r in o if r in ("text_editor", "script_mode", "full_editor", "learn")]
assert sec == ["script_mode", "text_editor", "full_editor", "learn"], sec
assert [x for x in o if x not in ("text_editor", "script_mode")] == [x for x in order0 if x not in ("text_editor", "script_mode")], "other tools must not move"
sc._selected = "learn"; sc._move_selected(1); assert sc._cfg["order"] == o, "last of a section can't move down"
print("settings move within section OK")


# pins: toggled, remembered, shown first, survive a stale Settings save
d3 = Dashboard(name="d3"); d3.manager = MagicMock()
d3._toggle_pin("minesweeper"); d3._toggle_pin("learn")
assert tool_labels(d3)[:2] == ["P:Minesweeper", "P:Learn (AI courses)"], tool_labels(d3)[:3]
d3._toggle_pin("minesweeper")
assert tool_labels(d3)[0] == "P:Learn (AI courses)" and st.load_settings()["pinned"] == ["learn"]
stale = st.load_settings(); stale["pinned"] = []; st.save_settings(stale)
assert st.load_settings()["pinned"] == ["learn"]
print("pins OK")

# search by alias, Enter opens the first hit
d3._search.text = "base64"
assert tool_labels(d3) == ["File to Base64"], tool_labels(d3)
visited.clear(); d3._open_first_hit(); assert visited == ["image_text"]
d3._search.text = ""
print("alias search + Enter OK")

# long press / right click pin; a normal tap opens
from screens.dashboard_screen import ToolButton
calls = []
tb = ToolButton("music", lambda r: calls.append(("open", r)), lambda r: calls.append(("pin", r)), text="x")
tb._released(); assert calls == [("open", "music")]
calls.clear(); tb._long(0); tb._released(); assert calls == [("pin", "music")]
tb._released(); assert calls[-1] == ("open", "music")
print("tool button OK")
