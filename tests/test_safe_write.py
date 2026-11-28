# tests/test_safe_write.py - python3 tests/test_safe_write.py  (no Kivy)
# Regression tests for the never-clobber helpers (audit F-01, F-02, F-03).
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import safe_write as sw

d = tempfile.mkdtemp()

def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)

def get(path):
    with open(path) as f:
        return f.read()

# --- unique_path: counter based, never an existing path
put(d + "/u/a.txt", "1"); put(d + "/u/a (1).txt", "2")
assert sw.unique_path(d + "/u", "a.txt") == d + "/u/a (2).txt"
assert sw.unique_path(d + "/u", "new.txt") == d + "/u/new.txt"

# --- F-01: three same-named photos moved into one folder keep all three
out = d + "/out"
for n in "ABC":
    put(f"{d}/s{n}/IMG_0001.jpg", n)
for n in "ABC":
    sw.move_keep_both(f"{d}/s{n}/IMG_0001.jpg", out)
assert sorted(get(f"{out}/{f}") for f in os.listdir(out)) == ["A", "B", "C"], os.listdir(out)
assert not any(os.path.exists(f"{d}/s{n}/IMG_0001.jpg") for n in "ABC")

# --- F-01: rename refuses to replace another file, and bad names
put(d + "/r/x.jpg", "new"); put(d + "/r/beach.jpg", "keep")
try:
    sw.rename_no_overwrite(d + "/r/x.jpg", "beach")
    raise SystemExit("rename onto an existing name should fail")
except FileExistsError:
    pass
assert get(d + "/r/beach.jpg") == "keep" and get(d + "/r/x.jpg") == "new"
for bad in ("", "  ", "../evil", "a/b", "a\\b", ".."):
    try:
        sw.rename_no_overwrite(d + "/r/x.jpg", bad)
        raise SystemExit(f"{bad!r} should be refused")
    except ValueError:
        pass
assert sw.rename_no_overwrite(d + "/r/x.jpg", "sunset") == d + "/r/sunset.jpg"
assert get(d + "/r/sunset.jpg") == "new"
# renaming to the same name (case-only or unchanged) is not a clash
assert sw.rename_no_overwrite(d + "/r/sunset.jpg", "sunset") == d + "/r/sunset.jpg"

# --- F-02: a failed atomic write keeps the old file and leaves no temp file
put(d + "/t/note.txt", "old")
sw.write_text_atomic(d + "/t/note.txt", "new")
assert get(d + "/t/note.txt") == "new"
try:
    sw.write_text_atomic(d + "/t/note.txt", "bad\ud800", encoding="utf-8")  # unencodable
    raise SystemExit("surrogate write should fail")
except UnicodeEncodeError:
    pass
assert get(d + "/t/note.txt") == "new"
assert os.listdir(d + "/t") == ["note.txt"], os.listdir(d + "/t")

# --- F-03: editing EXIF keeps JPEG quality tables and the ICC profile
try:
    from PIL import Image
except ImportError:
    print("safe_write OK (Pillow missing: image checks skipped)")
    raise SystemExit(0)
import random
random.seed(1)
p = d + "/photo.jpg"
im = Image.new("RGB", (200, 200))
im.putdata([(random.randrange(256),) * 3 for _ in range(200 * 200)])
im.save(p, quality=95, icc_profile=b"ICC" * 50)
q0 = Image.open(p).quantization[0][:8]
size0 = os.path.getsize(p)
img = Image.open(p); img.load()
ex = img.getexif(); ex[271] = "Make"
sw.save_image_atomic(img, p, exif=ex)
after = Image.open(p)
assert after.quantization[0][:8] == q0, (q0, after.quantization[0][:8])
assert after.info.get("icc_profile") == b"ICC" * 50
assert after.getexif().get(271) == "Make"
assert os.path.getsize(p) > size0 * 0.9
# a failing save keeps the original bytes
before = open(p, "rb").read()
try:
    sw.save_image_atomic(img, p, exif=b"not exif", quality="bogus")
    raise SystemExit("bad save should fail")
except SystemExit:
    raise
except Exception:
    pass
assert open(p, "rb").read() == before
assert [f for f in os.listdir(d) if f.endswith("srboli-part")] == []
print("safe_write OK")
