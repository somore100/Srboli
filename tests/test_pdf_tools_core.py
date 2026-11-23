# tests/test_pdf_tools_core.py - python3 tests/test_pdf_tools_core.py
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import pdf_tools_core as c

assert c.parse_ranges("1-3, 5, 8-", 9) == [0, 1, 2, 4, 7, 8]
assert c.parse_ranges("-2", 5) == [0, 1] and c.parse_ranges("3;1", 5) == [2, 0]
for bad in ("", "0", "6", "3-2", "a", "1-9", "--"):
    try: c.parse_ranges(bad, 5); raise SystemExit(f"no error for {bad!r}")
    except c.PDFError: pass
assert c.chunk_ranges(5, 2) == [[0, 1], [2, 3], [4]] and c.chunk_ranges(3, 10) == [[0, 1, 2]]
assert c.is_pdf("A.PDF") and not c.is_pdf("a.png")

try:
    import pypdf
except Exception:
    print("pdf tools core OK (ranges only: pypdf not installed)"); raise SystemExit

from PIL import Image
with tempfile.TemporaryDirectory() as d:
    def make(name, pages, color):
        p = os.path.join(d, name)
        ims = [Image.new("RGB", (100, 100 + i), color) for i in range(pages)]
        ims[0].save(p, "PDF", save_all=True, append_images=ims[1:])
        return p
    a, b = make("a.pdf", 3, (255, 0, 0)), make("b.pdf", 2, (0, 0, 255))
    assert c.page_count(a) == 3
    out = c.out_dir_for(a); assert out.endswith("srboli_pdf")
    m, n = c.merge([a, b], out); assert n == 5 and c.page_count(m) == 5
    m2, _ = c.merge([a, b], out); assert m2 != m                        # never overwrites
    try: c.merge([a], out); raise SystemExit("one file")
    except c.PDFError: pass
    e, n = c.extract(m, "1, 4-5", out); assert n == 3 and c.page_count(e) == 3
    parts = c.split(m, out, 2); assert [c.page_count(p) for p in parts] == [2, 2, 1]
    assert all("-part" in p for p in parts)
    each = c.split(a, out, 1); assert len(each) == 3
    bad = os.path.join(d, "bad.pdf"); open(bad, "wb").write(b"not a pdf")
    try: c.page_count(bad); raise SystemExit("bad pdf")
    except c.PDFError: pass
print("pdf tools core OK")
