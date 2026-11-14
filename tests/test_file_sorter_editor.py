# tests/test_file_sorter_editor.py - needs a display (kivy).
# The rule editor: new conditions never start as copies, duplicates and
# contradictions are refused, an empty name becomes the rule itself, and the
# sorter screen lists rules and "+ Add Rule" above the save/load buttons.
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config
Config.set("graphics", "width", "1000"); Config.set("graphics", "height", "700")
from kivy.core.window import Window
from kivy.clock import Clock
import screens.file_sorter_screen as fs

saved = []
ed = fs.RuleEditorPopup(on_save=saved.append)
assert not ed.name_input.text                       # name starts empty
Clock.tick()
assert "IF " in ed._auto_lbl.text                   # live "will be named" hint

# "+ Add condition" never creates a copy
for _ in range(3):
    ed._add_condition()
fields = [r._field_key() for r in ed._condition_rows]
assert len(set(fields)) == len(fields) == 4, fields

# whole-pixel popup
assert ed.width == int(ed.width) and (Window.width - ed.width) % 2 == 0

# identical rows are refused and nothing is saved
ed2 = fs.RuleEditorPopup(on_save=saved.append)
ed2._add_condition({"field": "file_type", "op": "is", "value": "Image"})
ed2._condition_rows[0].field_sp.text = "File type"
ed2._dest_path = "/tmp/x"
errs = []
ed2._flash_error = errs.append
ed2._save()
assert errs and "identical" in errs[0] and not saved, (errs, saved)

# valid rule, no name -> named after itself
ed3 = fs.RuleEditorPopup(on_save=saved.append)
ed3._condition_rows[0].field_sp.text = "File name"
ed3._condition_rows[0].value_input.text = "roblox"
ed3._dest_path = "/home/videos/roblox"
ed3._save()
r = saved[-1]
assert r["auto_name"] and r["name"] == "IF File name contains roblox THEN Move TO /home/videos/roblox", r
# a typed name wins and is not marked auto
ed4 = fs.RuleEditorPopup(on_save=saved.append)
ed4._condition_rows[0].field_sp.text = "File name"
ed4._condition_rows[0].value_input.text = "x"
ed4._dest_path = "/d"
ed4.name_input.text = "Games"
ed4._save()
assert saved[-1]["name"] == "Games" and not saved[-1].get("auto_name")
# editing an auto-named rule shows an empty name box again
ed5 = fs.RuleEditorPopup(on_save=saved.append, existing=r)
assert ed5.name_input.text == ""

# screen order: rules + Add Rule above Rulesets / Export
scr = fs.FileSorterScreen()
texts = []
def walk(w):
    t = getattr(w, "text", None)
    if isinstance(t, str): texts.append(t)
    for ch in reversed(w.children): walk(ch)   # top to bottom
walk(scr)
order = lambda s: next(i for i, t in enumerate(texts) if s in t)
assert order("Rules (evaluated") < order("+ Add Rule") < order("Pick Source") \
    < order("Preview") < order("Rulesets...") < order("Export...") < order("< Back")
print("file sorter editor passed")
