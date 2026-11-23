# tests/test_pdf_tools_screen.py - xvfb-run -a python3 tests/test_pdf_tools_screen.py  (kivy screens.)
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.clock import Clock
from screens.pdf_tools_screen import PDFToolsScreen
from core import pdf_tools_core as core

def wait(sc):
    for _ in range(200):
        Clock.tick()
        if not sc._running:
            return
        time.sleep(0.05)
    raise SystemExit("timeout")

sc = PDFToolsScreen()
sc.run(); assert "Add a PDF" in sc.status.text
try:
    import pypdf
except Exception:
    print("pdf tools screen OK (UI only: pypdf not installed)"); raise SystemExit
from PIL import Image
with tempfile.TemporaryDirectory() as d:
    def make(name, pages):
        p = os.path.join(d, name)
        ims = [Image.new("RGB", (100, 100 + i), (9, 9, 9)) for i in range(pages)]
        ims[0].save(p, "PDF", save_all=True, append_images=ims[1:]); return p
    a, b = make("a.pdf", 3), make("b.pdf", 2)
    sc.add_paths([a, b, os.path.join(d, "x.txt")])
    assert sc.paths == [a, b] and sc.pages[a] == 3
    sc.run(); wait(sc); assert "Merged 2 PDFs, 5 pages" in sc.status.text, sc.status.text
    sc.set_mode("split"); sc.add_paths([a, b]); assert sc.paths == [a]
    sc.split_sp.text = "Pick pages into a new file"; sc.range_in.text = "9"
    sc.run(); wait(sc); assert "outside" in sc.status.text
    sc.range_in.text = "1, 3"; sc.run(); wait(sc); assert "Extracted 2 pages" in sc.status.text
    sc.split_sp.text = "One file per page"; sc.run(); wait(sc); assert "Made 3 PDFs" in sc.status.text
print("pdf tools screen OK")
