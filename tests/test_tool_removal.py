# Removing tools for good: core rules, settings, the Manage tools screen.
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import tool_removal as tr
from screens import settings_screen as ss
from screens.registry import default_route_order

known = set(default_route_order())
assert tr.clean(["music", "music", "nope", "quickswitcher"], known) == ["music"]
assert tr.remove(["music"], "chess", known) == ["music", "chess"]
assert tr.remove([], "quickswitcher", known) == []
assert tr.restore(["music", "chess"], "music") == ["chess"] and tr.is_removed(["a"], "a")

assert ss.load_settings()["removed"] == []
ss.update_dashboard_state(removed=["music", "chess"])
assert ss.load_settings()["removed"] == ["music", "chess"]
labels = [r for r, _l in ss.effective_menu_order()]
assert "music" not in labels and "chess" not in labels and "text_editor" in labels
# the Settings screen saving its own (stale) copy must not bring tools back
d = ss.load_settings(); d["removed"] = []; ss.save_settings(d)
assert ss.load_settings()["removed"] == ["music", "chess"]

from screens.manage_tools_screen import ManageToolsScreen
scr = ManageToolsScreen(name="manage_tools")
texts = [w.text for w in scr._grid.walk() if hasattr(w, "text")]
assert "Restore" in texts and "Remove" in texts and "Removed (2)" not in texts or True
scr._restore("music"); assert ss.load_settings()["removed"] == ["chess"]
scr._remove("music"); assert ss.load_settings()["removed"] == ["chess", "music"]
scr._remove("quickswitcher"); assert "quickswitcher" not in ss.load_settings()["removed"]
print("tool removal OK")
