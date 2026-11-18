import os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import export_core as e
src = tempfile.mkdtemp(); out = tempfile.mkdtemp()
try: e.zip_folders([src], out, "x"); assert False
except OSError: pass
os.makedirs(os.path.join(src, "sub")); open(os.path.join(src, "a.log"), "w").write("hi")
open(os.path.join(src, "sub", "b.txt"), "w").write("yo")
p, n = e.zip_folders([src], out, "t")
assert n == 2 and os.path.dirname(p) == out
names = zipfile.ZipFile(p).namelist(); assert len(names) == 2 and any(x.endswith("b.txt") for x in names)
print("export core OK")
