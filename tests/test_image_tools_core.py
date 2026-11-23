# tests/test_image_tools_core.py - python3 tests/test_image_tools_core.py
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from core import image_tools_core as t

assert t.is_image("A.JPG") and not t.is_image("a.txt")
assert t.human(500) == "500 B" and t.human(2048) == "2.0 KB"
big = Image.new("RGB", (400, 200), (10, 120, 200))
assert t.fit_max_side(big, 100).size == (100, 50) and t.fit_max_side(big, 1000).size == (400, 200)
assert t.fit_max_side(big, 0) is big

with tempfile.TemporaryDirectory() as d:
    a, b, c = (os.path.join(d, n) for n in ("a.png", "b.jpg", "c.png"))
    import random
    rnd = random.Random(2)
    noisy = Image.effect_noise((600, 400), 60).convert("RGB")
    noisy.save(a); noisy.save(b, quality=100)
    Image.new("RGBA", (100, 300), (255, 0, 0, 0)).save(c)       # transparent
    out = t.out_dir_for(a)
    assert out.endswith("srboli_images")
    p, before, after = t.process_file(b, out, 300, "keep", 40)
    assert p.endswith(".jpg") and after < before and Image.open(p).size == (300, 200)
    p2, _, _ = t.process_file(b, out, 300, "keep", 40)
    assert p2 != p and os.path.exists(p) and os.path.exists(p2)   # never overwrites
    pw, _, _ = t.process_file(a, out, 0, "WEBP", 70)
    assert pw.endswith(".webp")
    pj, _, _ = t.process_file(c, out, 0, "JPG", 80)               # transparent -> white
    assert Image.open(pj).getpixel((5, 5))[0] > 250
    assert os.path.getsize(a) > 0 and Image.open(a).size == (600, 400)   # original untouched

    imgs = [Image.new("RGB", (200, 100), (255, 0, 0)), Image.new("RGB", (100, 100), (0, 255, 0))]
    v = t.combine(imgs, "vertical", size=100, gap=10)
    assert v.size == (100, 50 + 10 + 100)
    h = t.combine(imgs, "horizontal", size=100, gap=0)
    assert h.size == (200 + 100, 100)
    g = t.combine(imgs * 2, "grid", cols=2, size=200, gap=4)
    assert g.size == (204, 204)
    g1 = t.combine(imgs, "grid", cols=9, size=200)               # cols capped to count
    assert g1.size == (200, 100)
    for bad in ([], ):
        try: t.combine(bad); raise SystemExit("no error")
        except ValueError: pass
    try:
        t.combine([Image.new("RGB", (10, 10))] * 3, "vertical", size=9000, gap=0)
        raise SystemExit("should be too big")
    except ValueError as e:
        assert "too big" in str(e)
    cp, size = t.combine_files([a, b, c], out, "vertical", size=300, fmt_choice="PNG")
    assert cp.endswith(".png") and Image.open(cp).width == 300 and size > 0
print("image tools core OK")
