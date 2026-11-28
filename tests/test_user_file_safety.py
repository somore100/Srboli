# tests/test_user_file_safety.py - xvfb-run -a python3 tests/test_user_file_safety.py  (kivy screens.)
# The Gallery Sorter and Text Editor screens must never replace a user's file.
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from screens.gallery_sorter_screen import GallerySorterScreen
from screens.text_editor_screen import TextEditorScreen

d = tempfile.mkdtemp()

def put(p, t):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(t)

# Gallery: commit three same-named photos, then rename onto an existing name
g = GallerySorterScreen(name="g")
out = d + "/out"
for n in "ABC":
    put(f"{d}/{n}/IMG_1.jpg", n)
    assert g._do_move(f"{d}/{n}/IMG_1.jpg", out), g._move_err
assert sorted(open(f"{out}/{f}").read() for f in os.listdir(out)) == ["A", "B", "C"]

put(d + "/p/a.jpg", "new"); put(d + "/p/beach.jpg", "keep")
g._files = [d + "/p/a.jpg"]; g._index = 0
g._popup = lambda *a, **k: None
g._ren_in.text = "beach"
g._rename()
assert open(d + "/p/beach.jpg").read() == "keep" and os.path.exists(d + "/p/a.jpg")
assert g._files == [d + "/p/a.jpg"]

# Text Editor: two new documents saved internally stay two files
t = TextEditorScreen(name="t")
t._ed.text = "first note"; t._save_internal()
t._do_new()
t._ed.text = "second note"; t._save_internal()
saves = app_data.subdir("text_saves")
texts = sorted(open(os.path.join(saves, f)).read() for f in os.listdir(saves))
assert texts == ["first note", "second note"], texts
# saving the same document again updates it instead of adding a copy
t._ed.text = "second note v2"; t._save_internal()
assert len(os.listdir(saves)) == 2
# two different files named todo.txt get two slots
for i in (1, 2):
    put(f"{d}/dir{i}/todo.txt", f"todo {i}")
    t._file = f"{d}/dir{i}/todo.txt"; t._ed.text = f"todo {i}"; t._save_internal()
assert len(os.listdir(saves)) == 4, os.listdir(saves)
print("user file safety OK")
