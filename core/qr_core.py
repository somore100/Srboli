# core/qr_core.py - a small QR code encoder (no dependencies) and a scanner hook.
#
# Encodes any text as UTF-8 in byte mode, error correction L or M, versions
# 1-10 (up to 271 bytes at L, 213 at M: a link, Wi-Fi login, contact or note).
# make() returns the module matrix (list of rows of bools); to_png() saves it.
# scan_image() decodes a picture with OpenCV when it is installed (computer
# builds); on Android it returns (None, reason) instead.
import os

# level -> version -> (ec codewords per block, [(blocks, data codewords per block), ...])
_EC = {
    "L": {1: (7, [(1, 19)]), 2: (10, [(1, 34)]), 3: (15, [(1, 55)]), 4: (20, [(1, 80)]),
          5: (26, [(1, 108)]), 6: (18, [(2, 68)]), 7: (20, [(2, 78)]), 8: (24, [(2, 97)]),
          9: (30, [(2, 116)]), 10: (18, [(2, 68), (2, 69)])},
    "M": {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
          5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]),
          8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
          10: (26, [(4, 43), (1, 44)])},
}
_FMT_BITS = {"L": 1, "M": 0}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
MAX_VERSION = 10


class QRTooLong(ValueError):
    pass


def capacity(level="M"):
    """Most bytes of text one code can hold at this level."""
    v = MAX_VERSION
    return _data_cw(v, level) - 3          # mode + 16-bit count + terminator


def _data_cw(version, level):
    return sum(n * d for n, d in _EC[level][version][1])


# ---------- Reed-Solomon over GF(256) ----------
_EXP, _LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(n):
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _mul(c, _EXP[i])
        g = nxt
    return g


def _rs_remainder(data, n):
    gen = _rs_generator(n)
    rem = [0] * n
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        if f:
            for i in range(n):
                rem[i] ^= _mul(gen[i + 1], f)
    return rem


# ---------- bits ----------
def _bits(value, n):
    return [(value >> i) & 1 for i in range(n - 1, -1, -1)]


def _build_codewords(data, version, level):
    cap_bits = _data_cw(version, level) * 8
    bits = _bits(0b0100, 4) + _bits(len(data), 8 if version < 10 else 16)
    for b in data:
        bits += _bits(b, 8)
    bits += [0] * min(4, cap_bits - len(bits))
    bits += [0] * (-len(bits) % 8)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = [0xEC, 0x11]
    while len(cw) < cap_bits // 8:
        cw.append(pad[(len(cw) - len(bits) // 8) % 2])
    ec_len, groups = _EC[level][version]
    blocks, pos = [], 0
    for n, d in groups:
        for _ in range(n):
            blocks.append(cw[pos:pos + d])
            pos += d
    ecs = [_rs_remainder(b, ec_len) for b in blocks]
    out = []
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ec_len):
        for e in ecs:
            out.append(e[i])
    return out


# ---------- matrix ----------
def _format_bits(level, mask):
    data = (_FMT_BITS[level] << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _version_bits(version):
    rem = version
    for _ in range(12):
        rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
    return (version << 12) | rem


def _mask_fn(m):
    return [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0,
            lambda r, c: c % 3 == 0, lambda r, c: (r + c) % 3 == 0,
            lambda r, c: (r // 2 + c // 3) % 2 == 0,
            lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
            lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
            lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0][m]


def _penalty(m):
    n = len(m)
    score = 0
    for grid in (m, [list(col) for col in zip(*m)]):
        for row in grid:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
            s = "".join("1" if x else "0" for x in row)
            score += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(x for row in m for x in row)
    score += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return score


def _layout(version):
    """(matrix, is_function) with all fixed patterns drawn, data area empty."""
    n = version * 4 + 17
    m = [[False] * n for _ in range(n)]
    f = [[False] * n for _ in range(n)]

    def put(r, c, v):
        if 0 <= r < n and 0 <= c < n:
            m[r][c] = v
            f[r][c] = True

    for r, c in ((0, 0), (0, n - 7), (n - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                ring = max(abs(dr - 3), abs(dc - 3))
                put(r + dr, c + dc, ring not in (2, 4) and ring <= 3)
    for i in range(8, n - 8):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    pos = _ALIGN[version]
    for r in pos:
        for c in pos:
            if (r, c) in ((6, 6), (6, pos[-1]), (pos[-1], 6)) and len(pos) > 1:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    put(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    put(n - 8, 8, True)                          # the always-dark module
    for i in range(9):                           # reserve the format areas
        if i != 6:                               # (row/column 6 is the timing line)
            put(8, i, False)
            put(i, 8, False)
    for i in range(8):
        put(8, n - 1 - i, False)
        put(n - 1 - i, 8, False)
    put(n - 8, 8, True)
    if version >= 7:
        vb = _version_bits(version)
        for i in range(18):
            bit = bool((vb >> i) & 1)
            put(i // 3, n - 11 + i % 3, bit)
            put(n - 11 + i % 3, i // 3, bit)
    return m, f


def _place(m, f, codewords):
    n = len(m)
    bits = [b for cw in codewords for b in _bits(cw, 8)]
    i, up = 0, True
    for col in range(n - 1, 0, -2):
        if col <= 6:
            col -= 1
        rows = range(n - 1, -1, -1) if up else range(n)
        for r in rows:
            for c in (col, col - 1):
                if not f[r][c]:
                    m[r][c] = bool(bits[i]) if i < len(bits) else False
                    i += 1
        up = not up


def _draw_format(m, level, mask):
    n = len(m)
    fb = _format_bits(level, mask)
    for i in range(15):
        bit = bool((fb >> i) & 1)
        if i < 6:
            m[i][8] = bit
        elif i < 8:
            m[i + 1][8] = bit
        else:
            m[n - 15 + i][8] = bit
        if i < 8:
            m[8][n - 1 - i] = bit
        elif i < 9:
            m[8][15 - i] = bit
        else:
            m[8][14 - i] = bit


def make(text, level="M"):
    """The QR matrix for `text`: list of rows, True = dark module."""
    if level not in _EC:
        raise ValueError("level must be 'L' or 'M'")
    data = text.encode("utf-8")
    if not data:
        raise ValueError("Nothing to encode.")
    version = None
    for v in range(1, MAX_VERSION + 1):
        extra = 2 if v < 10 else 3                 # mode nibble + count + terminator
        if len(data) + extra <= _data_cw(v, level):
            version = v
            break
    if version is None:
        raise QRTooLong(f"Too long for one code: {len(data)} bytes, "
                        f"at most {capacity(level)} at level {level}.")
    cws = _build_codewords(data, version, level)
    base, func = _layout(version)
    _place(base, func, cws)
    best, best_score = None, None
    for mask in range(8):
        fn = _mask_fn(mask)
        m = [row[:] for row in base]
        for r in range(len(m)):
            for c in range(len(m)):
                if not func[r][c] and fn(r, c):
                    m[r][c] = not m[r][c]
        _draw_format(m, level, mask)
        s = _penalty(m)
        if best is None or s < best_score:
            best, best_score = m, s
    return best


def to_png(matrix, path, scale=10, border=4):
    """Save the matrix as a black-on-white PNG. Needs Pillow."""
    from PIL import Image
    n = len(matrix) + 2 * border
    img = Image.new("L", (n, n), 255)
    px = img.load()
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                px[c + border, r + border] = 0
    img = img.resize((n * scale, n * scale), Image.NEAREST)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    return path


# ---------- scanning ----------
def can_scan():
    try:
        import cv2  # noqa: F401
        return True
    except Exception:
        return False


def scan_image(path):
    """(text, error): the text of the QR code in a picture."""
    try:
        import cv2
    except Exception:
        return None, "Scanning needs OpenCV, which is only in the computer builds."
    img = cv2.imread(path)
    if img is None:
        return None, "Could not read that picture."
    det = cv2.QRCodeDetector()
    for im in (img, cv2.resize(img, None, fx=2, fy=2), cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)):
        text, _pts, _ = det.detectAndDecode(im)
        if text:
            return text, ""
    return None, "No QR code found in that picture."


# ---------- ready-made text formats ----------
def wifi_text(ssid, password="", security="WPA", hidden=False):
    def esc(s):
        for ch in ("\\", ";", ",", ":", '"'):
            s = s.replace(ch, "\\" + ch)
        return s
    sec = security if security in ("WPA", "WEP") and password else "nopass"
    out = f"WIFI:T:{sec};S:{esc(ssid)};"
    if sec != "nopass":
        out += f"P:{esc(password)};"
    if hidden:
        out += "H:true;"
    return out + ";"
