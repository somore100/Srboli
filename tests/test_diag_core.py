import os, sys, tempfile, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import diag_core as d
t = d.report({"screen": "x"}); assert "Srboli diagnostic report" in t and "screen: x" in t
p, n = d.make_zip(tempfile.mkdtemp())
assert "diagnostic.txt" in zipfile.ZipFile(p).namelist() and n >= 1
print("diag core OK")
