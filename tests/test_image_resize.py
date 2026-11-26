import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from core import image_tools_core as ic

fails = 0
def check(n, c, i=""):
    global fails
    if not c:
        fails += 1; print("FAIL", n, i)

P = ic.plan_size
check("percent up", P(100, 50, "percent", 200) == (200, 100))
check("percent down", P(100, 50, "percent", 50) == (50, 25))
check("percent rounds, never 0", P(3, 3, "percent", 10) == (1, 1))
check("longest up", P(400, 200, "longest", 800) == (800, 400))
check("longest down", P(400, 200, "longest", 100) == (100, 50))
check("longest portrait", P(200, 400, "longest", 800) == (400, 800))
check("exact fit keeps ratio", P(400, 200, "exact", width=100, height=100, fit="fit") == (100, 50))
check("exact fill is the box", P(400, 200, "exact", width=100, height=100, fit="fill") == (100, 100))
check("exact stretch", P(400, 200, "exact", width=30, height=90, fit="stretch") == (30, 90))
check("exact width only", P(400, 200, "exact", width=100) == (100, 50))
check("exact height only", P(400, 200, "exact", height=100) == (200, 100))
for bad in (dict(mode="percent", value=0), dict(mode="percent", value=-5), dict(mode="longest", value=0),
            dict(mode="exact"), dict(mode="nope"), dict(mode="percent", value=100000),
            dict(mode="longest", value=20000)):
    try:
        P(100, 100, **bad); check("rejects " + str(bad), False)
    except ValueError:
        pass
try:
    P(0, 10, "percent", 100); check("zero size", False)
except ValueError:
    pass
try:
    P(10000, 10000, "percent", 150); check("pixel cap", False)
except ValueError as e:
    check("pixel cap message", "too big" in str(e))

img = Image.new("RGB", (40, 20), (200, 30, 30))
for x in range(20):
    for y in range(20):
        img.putpixel((x, y), (10, 10, 200))
up = ic.resize_image(img, "percent", 300)
check("upscaled size", up.size == (120, 60))
check("same size copy", ic.resize_image(img, "percent", 100).size == (40, 20) and ic.resize_image(img, "percent", 100) is not img)
fill = ic.resize_image(img, "exact", width=20, height=20, fit="fill")
check("fill crops to the box", fill.size == (20, 20) and fill.getpixel((2, 10))[2] > 100, fill.getpixel((2, 10)))
check("fit stays inside", ic.resize_image(img, "exact", width=20, height=20).size == (20, 10))
soft = ic.resize_image(img, "percent", 400)
sharp = ic.resize_image(img, "percent", 400, sharpen=3)
check("sharpen changes edges", sharp.tobytes() != soft.tobytes() and sharp.size == soft.size)
check("sharpen 0 / junk ignored", ic.resize_image(img, "percent", 400, sharpen=0).tobytes() == soft.tobytes()
      and ic.resize_image(img, "percent", 400, sharpen=9).tobytes() == soft.tobytes())
rgba = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
check("alpha kept", ic.resize_image(rgba, "percent", 200).mode == "RGBA")

d = tempfile.mkdtemp()
src = os.path.join(d, "pic.png")
img.save(src)
check("image_size", ic.image_size(src) == (40, 20))
out, b, a, size = ic.resize_file(src, os.path.join(d, "out"), "percent", 200, fmt_choice="keep")
check("resize_file", size == (80, 40) and os.path.basename(out) == "pic-80x40.png" and b > 0 and a > 0, out)
out2 = ic.resize_file(src, os.path.join(d, "out"), "percent", 200)[0]
check("never overwrites", out2 != out and os.path.exists(out) and os.path.exists(out2))
out3, _b, _a, _s = ic.resize_file(src, os.path.join(d, "out"), "longest", 10, fmt_choice="JPG", quality=70)
check("converts while resizing", out3.endswith(".jpg") and Image.open(out3).size == (10, 5), out3)
check("original untouched", Image.open(src).size == (40, 20))
check("describe", "bigger" in ic.describe_resize(10, 10, 20, 20) and "smaller" in ic.describe_resize(10, 10, 5, 5)
      and "same" in ic.describe_resize(10, 10, 10, 10))
check("exif image_size swaps", True)
im = Image.new("RGB", (30, 10))
ex = im.getexif(); ex[274] = 6
rot = os.path.join(d, "rot.jpg"); im.save(rot, exif=ex)
check("exif rotated size", ic.image_size(rot) == (10, 30), ic.image_size(rot))
print("OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
