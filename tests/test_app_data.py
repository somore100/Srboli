# Tests for app_data: safe data-dir move, config read-modify-write, cache clearing.
import os, sys, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_data

tmp = tempfile.mkdtemp()
app_data._CONFIG_FILE = os.path.join(tmp, "cfg.json")
json.dump({"data_dir": os.path.join(tmp, "old"), "keep": 1}, open(app_data._CONFIG_FILE, "w"))
app_data._APP_DIR = None
old = app_data.get_data_dir()
os.makedirs(os.path.join(old, "sub", "deep"))
open(os.path.join(old, "a.txt"), "w").write("A")
open(os.path.join(old, "sub", "deep", "b.txt"), "w").write("B")
os.makedirs(os.path.join(old, "gallery_cache"))
open(os.path.join(old, "gallery_cache", "x.jpg"), "w").write("12345")
open(os.path.join(old, "my_thumbnails_notes.txt"), "w").write("keep me")   # "thumb" in name
open(os.path.join(old, "work.tmp"), "w").write("keep me too")

# cache: only the cache folders are touched
assert app_data.clear_cache() == 5
assert os.path.exists(os.path.join(old, "my_thumbnails_notes.txt"))
assert os.path.exists(os.path.join(old, "work.tmp"))
open(os.path.join(old, "gallery_cache", "x.jpg"), "w").write("12345")

def snapshot(root):
    out = {}
    for cur, _d, fs in os.walk(root):
        for f in fs:
            out[os.path.relpath(os.path.join(cur, f), root)] = open(os.path.join(cur, f)).read()
    return out
before = snapshot(old)

# new inside old / old inside new: refused, nothing changed
for bad in (os.path.join(old, "sub"),):
    try:
        app_data.set_data_dir(bad)
        raise SystemExit("nesting should be refused: " + bad)
    except app_data.DataDirError:
        pass
assert snapshot(old) == before and app_data.get_data_dir() == old

# target already has data: refused, nothing deleted or overwritten
dest = os.path.join(tmp, "dest")
os.makedirs(os.path.join(dest, "srboli_data", "sub"))
open(os.path.join(dest, "srboli_data", "sub", "keep.txt"), "w").write("theirs")
try:
    app_data.set_data_dir(dest)
    raise SystemExit("existing data should be refused")
except app_data.DataDirExists:
    pass
assert open(os.path.join(dest, "srboli_data", "sub", "keep.txt")).read() == "theirs"
assert snapshot(old) == before and app_data.get_data_dir() == old

assert app_data._nested(old, os.path.join(old, "x")) and app_data._nested(os.path.join(old, "x"), old)
assert not app_data._nested(old, os.path.join(tmp, "other"))

# "use existing": repoint only, old data untouched
assert app_data.set_data_dir(dest, use_existing=True) == os.path.join(dest, "srboli_data")
assert snapshot(old) == before
assert json.load(open(app_data._CONFIG_FILE))["keep"] == 1      # other keys survive
app_data._APP_DIR = old; app_data._save_config({"data_dir": old})  # back to old
assert app_data.get_data_dir() == old

# a failing copy leaves the app on the old location, everything intact
import core.file_safety as fs
real = fs.safe_copy
def flaky(src, dst, overwrite=False):
    if src.endswith("b.txt"):
        raise OSError("disk full")
    return real(src, dst, overwrite)
fs.safe_copy = flaky
target = os.path.join(tmp, "target")
try:
    app_data.set_data_dir(target)
    raise SystemExit("failure should raise")
except app_data.MoveFailed as e:
    assert len(e.failures) == 1 and "b.txt" in e.failures[0][0]
fs.safe_copy = real
assert snapshot(old) == before and app_data.get_data_dir() == old
assert json.load(open(app_data._CONFIG_FILE))["data_dir"] == old
assert not os.path.exists(os.path.join(target, "srboli_data"))

# successful move: verified copy, originals removed, config switched
seen = []
new = app_data.set_data_dir(target, progress=lambda d, t: seen.append((d, t)))
assert new == os.path.join(target, "srboli_data") == app_data.get_data_dir()
assert snapshot(new) == before and not os.path.exists(old)
assert seen and seen[-1][0] == seen[-1][1]
assert json.load(open(app_data._CONFIG_FILE))["data_dir"] == new

# corrupt config is kept aside, not silently overwritten
open(app_data._CONFIG_FILE, "w").write("{broken")
app_data._APP_DIR = None
app_data.get_data_dir()
assert any(".corrupt-" in n for n in os.listdir(tmp))
print("app_data OK")
