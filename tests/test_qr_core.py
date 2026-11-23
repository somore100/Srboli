# tests/test_qr_core.py - python3 tests/test_qr_core.py (cv2 round trip if installed)
import os, sys, tempfile, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import qr_core as q

assert len(q.make("A")) == 21 and len(q.make("A" * 40, "L")) == 29
try:
    q.make("x" * 400)
    raise SystemExit("should be too long")
except q.QRTooLong:
    pass
assert q.wifi_text("my;net", "pw") == r"WIFI:T:WPA;S:my\;net;P:pw;;"
assert q.wifi_text("open") == "WIFI:T:nopass;S:open;;"

if q.can_scan():
    import cv2, numpy as np
    rnd = random.Random(1)
    cases = []
    for level in ("L", "M"):
        for n in (1, 10, 20, 30, 40, 60, 90, 130, 170, 200, 212):
            cases.append((level, "".join(rnd.choice("abcXYZ019 /:.-") for _ in range(n))))
        cases.append((level, "Zdravo, srpski: šđčćž 😀"))
    for level in ("L", "M"):
        cases.append((level, "".join(rnd.choice("abcdef ") for _ in range(q.capacity(level)))))
    det = cv2.QRCodeDetector()
    for level, text in cases:
        m = q.make(text, level)
        n = len(m) + 8
        img = np.full((n, n), 255, np.uint8)
        for r, row in enumerate(m):
            for c, d in enumerate(row):
                if d:
                    img[r + 4, c + 4] = 0
        img = cv2.resize(img, None, fx=8, fy=8, interpolation=cv2.INTER_NEAREST)
        got, _, _ = det.detectAndDecode(img)
        assert got == text, (level, len(text), len(m), got[:30])
    with tempfile.TemporaryDirectory() as d:
        p = q.to_png(q.make("hello qr"), os.path.join(d, "a.png"))
        assert q.scan_image(p) == ("hello qr", "")
        assert q.scan_image(os.path.join(d, "none.png"))[0] is None
print("qr core OK")
