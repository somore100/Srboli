# tests/test_bulk_rename_screen.py - xvfb-run -a python3 tests/test_bulk_rename_screen.py
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from screens.bulk_rename_screen import BulkRenameScreen

w = tempfile.mkdtemp()
for n in ("a 1.txt", "a 2.txt", "b.md"):
    open(os.path.join(w, n), "w").write(n)
s = BulkRenameScreen()
assert s.go.disabled and s.undo_btn.disabled and "Choose a folder" in (s.status.text or "Choose a folder")
s.set_folder(w)
assert s.go.disabled and "0 will be renamed" in s.status.text      # empty rule is skipped
row = s.rules_box.children[0]
row.spin.text = "Spaces to _ (or text)"; s.refresh()
assert not s.go.disabled and "2 will be renamed" in s.status.text, s.status.text
assert "a_1.txt" in s.preview.text
s.add_rule("number"); s.rules_box.children[0].a.text = "1"; s.rules_box.children[0].b.text = "2"
s.pattern.text = "*.txt"; s.refresh()
assert "a_1_01.txt" in s.preview.text and "b.md" not in s.preview.text, s.preview.text
s.do_rename()
assert sorted(os.listdir(w)) == ["a_1_01.txt", "a_2_02.txt", "b.md"], os.listdir(w)
assert not s.undo_btn.disabled and "Renamed 2" in s.status.text
s.undo(); assert sorted(os.listdir(w)) == ["a 1.txt", "a 2.txt", "b.md"] and "Put 2" in s.status.text
assert s.undo_btn.disabled
# a clash is shown and blocks the button
s.pattern.text = ""; s.rules_box.clear_widgets(); s.add_rule("template")
s.rules_box.children[0].a.text = "same"; s.refresh()
assert s.go.disabled and "problem" in s.status.text and "same" in s.preview.text
s.remove_rule(s.rules_box.children[0]); s.refresh(); assert "0 will be renamed" in s.status.text
print("bulk rename screen: all ok")
