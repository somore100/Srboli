# Tests for core/jsonio.py (atomic writes, corrupt files kept aside).
import os, sys, json, tempfile, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.jsonio import read_json, write_json_atomic

d = tempfile.mkdtemp()
p = os.path.join(d, "a.json")

assert read_json(p, {"x": 1}) == {"x": 1}                  # missing -> default
write_json_atomic(p, {"a": [1, 2], "u": "é"}, ensure_ascii=False)
assert read_json(p) == {"a": [1, 2], "u": "é"}
assert os.listdir(d) == ["a.json"]                          # no temp file left

# a failed write keeps the old file and leaves no temp file
class Bad:
    pass
try:
    write_json_atomic(p, {"b": Bad()})
    raise SystemExit("should have raised")
except TypeError:
    pass
assert read_json(p) == {"a": [1, 2], "u": "é"}
assert os.listdir(d) == ["a.json"]

# corrupt file: moved aside, default returned, original content kept
with open(p, "w") as f:
    f.write('{"half": ')
assert read_json(p, "dflt") == "dflt"
assert not os.path.exists(p)
bad = glob.glob(p + ".corrupt-*")
assert len(bad) == 1 and open(bad[0]).read() == '{"half": '

# user-chosen file is never renamed
q = os.path.join(d, "mine.json")
open(q, "w").write("nope")
assert read_json(q, None, quarantine_bad=False) is None
assert os.path.exists(q)
print("jsonio OK")
