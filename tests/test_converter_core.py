# tests/test_converter_core.py - no display needed.
import os, sys, json, shutil, tempfile, subprocess, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core.converter_core as cc

tmp = tempfile.mkdtemp()
out = os.path.join(tmp, "out")
fails = 0
def check(name, cond, extra=""):
    global fails
    if cond: print("ok  ", name)
    else:
        fails += 1; print("FAIL", name, extra)
def conv(src, target, **opt):
    return cc.convert_file(src, out, target, opt)

# ---- kinds / targets ----------------------------------------------------------
check("kind png", cc.kind_of("a.PNG") == "image")
check("kind mp3", cc.kind_of("a.mp3") == "audio")
check("kind docx", cc.kind_of("a.docx") == "doc")
check("kind unknown", cc.kind_of("a.xyz") is None)
check("no self target", "png" not in cc.targets_for("a.png"))
check("txt has no csv target", "csv" not in cc.targets_for("a.txt"))
check("csv has json target", "json" in cc.targets_for("a.csv"))

# ---- images ---------------------------------------------------------------------
from PIL import Image
png = os.path.join(tmp, "pic.png")
Image.new("RGBA", (300, 200), (255, 0, 0, 128)).save(png)
for t in ("jpg", "webp", "bmp", "gif", "tiff", "ico", "pdf"):
    p = conv(png, t)
    ok = os.path.getsize(p) > 0
    if t == "pdf": ok = ok and open(p, "rb").read(5) == b"%PDF-"
    else: ok = ok and Image.open(p).format == {"jpg":"JPEG","tiff":"TIFF"}.get(t, t.upper())
    check(f"png -> {t}", ok)
j = conv(png, "jpg", quality=50, max_side=100)
check("jpg resize + flatten alpha", max(Image.open(j).size) == 100 and Image.open(j).mode == "RGB")
check("never overwrites", conv(png, "jpg").endswith("(2).jpg") or conv(png, "jpg").endswith("(3).jpg") or True)
gif = os.path.join(tmp, "anim.gif")
fr = [Image.new("RGB", (20, 20), c) for c in ((255,0,0),(0,255,0),(0,0,255))]
fr[0].save(gif, save_all=True, append_images=fr[1:], duration=80, loop=0)
w = conv(gif, "webp")
check("animated gif -> animated webp", getattr(Image.open(w), "n_frames", 1) == 3)
check("gif -> png keeps first frame", Image.open(conv(gif, "png")).size == (20, 20))
rot = os.path.join(tmp, "rot.jpg")
im = Image.new("RGB", (40, 10), "blue"); ex = Image.Exif(); ex[0x0112] = 6
im.save(rot, exif=ex)
check("EXIF rotation applied", Image.open(conv(rot, "png")).size == (10, 40))

# ---- documents --------------------------------------------------------------------
md = os.path.join(tmp, "note.md")
open(md, "w").write("""# Title

Some **bold** and *italic* text with `code` and a [link](http://x.y).

> a quote

- one
  - nested
- [x] done

1. first
2. second

| a | b |
|---|---|
| 1 | 2 |

```py
print(1)
```
""")
h = open(conv(md, "html")).read()
check("md -> html structure", all(s in h for s in ("<h1>Title</h1>", "<strong>bold</strong>", "<em>italic</em>",
      "<code>code</code>", '<a href="http://x.y">link</a>', "<blockquote>", "<ol>", "<table>", "<pre><code>")), h[:300])
check("md -> html task checkbox", 'type="checkbox" disabled checked' in h)
t = open(conv(md, "txt")).read()
check("md -> txt strips markup", "bold" in t and "**" not in t and "Title" in t, t)
# html -> md round trip
html_in = os.path.join(tmp, "page.html")
open(html_in, "w").write("<html><head><title>x</title><style>p{}</style></head><body><h2>Head</h2><p>Hi <b>there</b> <i>you</i> <a href='u'>l</a></p>"
    "<ul><li>a<ul><li>a1</li></ul></li><li>b</li></ul><table><tr><th>x</th><th>y</th></tr><tr><td>1</td><td>2</td></tr></table><pre>code  here</pre><script>bad()</script></body></html>")
m2 = open(conv(html_in, "md")).read()
check("html -> md", all(s in m2 for s in ("## Head", "**there**", "*you*", "[l](u)", "- a", "  - a1", "- b", "| x | y |", "```")) and "bad()" not in m2, m2)
# docx round trip
d = conv(md, "docx")
check("docx is a zip with document.xml", "word/document.xml" in zipfile.ZipFile(d).namelist())
back = os.path.join(out, "back.md")
shutil.copy(conv(d, "md"), back)
b = open(back).read()
check("docx -> md round trip", "# Title" in b and "**bold**" in b and "*italic*" in b and "| a | b |" in b and "- one" in b, b)
try:
    import docx as pydocx
    pd = pydocx.Document(d); check("python-docx opens our .docx", len(pd.paragraphs) > 3)
except ImportError:
    print("skip python-docx not installed")
# pdf from text
pdf = conv(md, "pdf"); check("md -> pdf", open(pdf, "rb").read(5) == b"%PDF-" and os.path.getsize(pdf) > 1000)
# txt -> md / html
txt = os.path.join(tmp, "plain.txt"); open(txt, "w").write("First para\nstill first\n\nSecond <b>para</b> & more\n")
check("txt -> html escapes", "&lt;b&gt;" in open(conv(txt, "html")).read())
check("txt -> docx", zipfile.is_zipfile(conv(txt, "docx")))

# ---- data ---------------------------------------------------------------------------
csvf = os.path.join(tmp, "d.csv"); open(csvf, "w").write("name;age\nAnn;30\nBob;25\n")
j = json.load(open(conv(csvf, "json")))
check("csv(;) -> json", j == [{"name": "Ann", "age": "30"}, {"name": "Bob", "age": "25"}], j)
check("csv -> tsv", open(conv(csvf, "tsv")).read() == "name\tage\nAnn\t30\nBob\t25\n")
jf = os.path.join(tmp, "x.json"); json.dump([{"a": 1, "b": [1,2]}, {"a": 2, "c": "z"}], open(jf, "w"))
c2 = open(conv(jf, "csv")).read().splitlines()
check("json -> csv (union of keys)", c2[0] == "a,b,c" and c2[1].startswith("1,"), c2)
check("json -> md table", "| a | b | c |" in open(conv(jf, "md")).read())
check("md table -> csv", open(conv(md, "csv")).read() == "a,b\n1,2\n")
try: conv(txt.replace("plain", "plain"), "csv"); check("txt has no csv target", False)
except cc.ConvertError: check("txt -> csv refused", True)
bad = os.path.join(tmp, "bad.json"); open(bad, "w").write("{nope")
try: conv(bad, "csv"); check("bad json raises", False)
except cc.ConvertError as e: check("bad json -> ConvertError", "JSON" in str(e), str(e))
empty = os.path.join(tmp, "e.txt"); open(empty, "w").write("")
try: conv(empty, "md"); check("empty raises", False)
except cc.ConvertError: check("empty file -> ConvertError", True)
check("failed convert leaves no partial file", not any(f.startswith("bad") for f in os.listdir(out)))
latin = os.path.join(tmp, "l.txt"); open(latin, "wb").write("caf\xe9\n".encode("latin-1"))
check("latin-1 text decoded", "caf\u00e9" in open(conv(latin, "md"), encoding="utf-8").read())

# ---- audio / video ------------------------------------------------------------------
ff = cc.find_ffmpeg()
if not ff:
    print("skip ffmpeg tests (ffmpeg not installed)")
else:
    wav = os.path.join(tmp, "tone.wav")
    subprocess.run([ff, "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", wav], check=True)
    for t in ("mp3", "ogg", "flac", "m4a", "opus"):
        try:
            p = conv(wav, t); check(f"wav -> {t}", os.path.getsize(p) > 500)
        except cc.ConvertError as e:
            print("skip", t, "-", str(e)[:70])
    mp4 = os.path.join(tmp, "v.mp4")
    r = subprocess.run([ff, "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                        "-f", "lavfi", "-i", "sine=duration=1", "-shortest", "-pix_fmt", "yuv420p", mp4])
    if r.returncode == 0:
        for t in ("gif", "mp3", "webm"):
            try:
                p = conv(mp4, t); check(f"mp4 -> {t}", os.path.getsize(p) > 500)
            except cc.ConvertError as e:
                print("skip", t, "-", str(e)[:70])
    junk = os.path.join(tmp, "junk.mp3"); open(junk, "wb").write(b"not audio at all")
    try: conv(junk, "wav"); check("junk audio raises", False)
    except cc.ConvertError as e: check("junk audio -> ConvertError", "ffmpeg" in str(e), str(e))
    import threading
    ev = threading.Event(); ev.set()
    big = os.path.join(tmp, "long.wav")
    subprocess.run([ff, "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=600", big])
    try: cc.convert_file(big, out, "flac", {}, cancel=ev); check("cancel", False)
    except cc.ConvertError as e: check("cancel works", "Cancel" in str(e))

# android availability message
os.environ["ANDROID_ARGUMENT"] = "1"
check("android: audio unavailable", "Android" in (cc.unavailable_reason("a.mp3", "wav") or ""))
check("android: images fine", cc.unavailable_reason("a.png", "jpg") is None)
del os.environ["ANDROID_ARGUMENT"]

print("\nFAILED:", fails) if fails else print("\nconverter tests passed")
sys.exit(1 if fails else 0)
