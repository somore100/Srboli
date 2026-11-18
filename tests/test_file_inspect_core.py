# tests/test_file_inspect_core.py - python3 tests/test_file_inspect_core.py
import hashlib, os, sys, tempfile, zipfile, sqlite3, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import file_inspect_core as c

d = tempfile.mkdtemp()
def mk(name, data):
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode())
    return p
def kind(p): return c.detect(p)[0]

assert kind(mk("a.png", b"\x89PNG\r\n\x1a\n" + b"x" * 20)) == "PNG image"
assert kind(mk("a.jpg", b"\xff\xd8\xff\xe0" + b"x" * 20)) == "JPEG image"
assert kind(mk("a.gif", b"GIF89a" + b"x")) == "GIF image"
assert kind(mk("a.pdf", b"%PDF-1.7\n")) == "PDF document"
assert kind(mk("a.gz", b"\x1f\x8b\x08\x00")) == "GZIP archive"
assert kind(mk("a.elf", b"\x7fELF" + b"\0" * 20)) == "ELF program (Linux)"
assert kind(mk("a.mp3", b"ID3\x03\x00")) == "MP3 audio"
assert kind(mk("a.wav", b"RIFF\x00\x00\x00\x00WAVEfmt ")) == "WAV audio"
assert kind(mk("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")) == "WebP image"
assert kind(mk("a.mp4", b"\x00\x00\x00\x18ftypisom\x00\x00")) == "MP4 video"
assert kind(mk("a.m4a", b"\x00\x00\x00\x18ftypM4A \x00\x00")) == "M4A audio"
assert kind(mk("empty", b"")) == "Empty file"
assert kind(mk("rnd.bin", bytes(range(256)))) == "Unknown binary data"
assert kind(mk("t.txt", "hello\nworld\n")) == "Plain text"
assert kind(mk("t.json", '{"a": [1, 2]}')) == "JSON data"
assert kind(mk("bad.json", '{"a": ')) == "Plain text"
assert kind(mk("t.xml", '<?xml version="1.0"?><a/>')) == "XML document"
assert kind(mk("t.svg", '<?xml version="1.0"?><svg xmlns="x"/>')) == "SVG image"
assert kind(mk("t.html", "<!DOCTYPE html><html></html>")) == "HTML document"
assert kind(mk("run.sh", "#!/bin/sh\necho hi\n")) == "Script"
assert kind(mk("u.txt", "café 中".encode("utf-8"))) == "Plain text"
assert kind(mk("u16.txt", b"\xff\xfeh\x00i\x00")) == "Plain text"
# sqlite, tar, zip kinds
db = os.path.join(d, "x.db"); sqlite3.connect(db).execute("create table t(a)").connection.commit()
assert kind(db) == "SQLite database"
def zipof(name, files, first=None):
    p = os.path.join(d, name)
    with zipfile.ZipFile(p, "w") as z:
        for n in files:
            z.writestr(n, "x")
    return p
assert kind(zipof("w.docx", ["[Content_Types].xml", "word/document.xml"])) == "Word document (DOCX)"
assert kind(zipof("s.xlsx", ["xl/workbook.xml"])) == "Excel workbook (XLSX)"
assert kind(zipof("a.apk", ["AndroidManifest.xml"])) == "Android app (APK)"
assert kind(zipof("j.jar", ["META-INF/MANIFEST.MF"])) == "Java archive (JAR)"
assert kind(zipof("p.zip", ["a.txt", "b.txt"])) == "ZIP archive"
assert c.detect(zipof("p2.zip", ["a.txt"]))[3] == "1 entries inside"
odt = os.path.join(d, "d.odt")
with zipfile.ZipFile(odt, "w") as z:
    z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
assert kind(odt) == "OpenDocument (text)"
bad = mk("broken.zip", b"PK\x03\x04garbage")
assert "damaged" in kind(bad)
import tarfile
tp = os.path.join(d, "t.tar")
with tarfile.open(tp, "w") as t:
    t.add(mk("inner.txt", "x"), "inner.txt")
assert kind(tp) == "TAR archive"

# name vs contents
assert c.name_check("x.png", ["png"]) == ""
assert "contents look like .png" in c.name_check("x.jpg", ["png"])
assert "no extension" in c.name_check("x", ["png"])
assert c.name_check("x.anything", []) == ""
liar = mk("pic.jpg", b"\x89PNG\r\n\x1a\nxxxx")
assert "WARNING" in c.report(c.inspect(liar))

# inspect + report
t = mk("lines.txt", "a\nb\nc")
i = c.inspect(t)
assert i["size"] == 5 and i["lines"] == 3 and i["is_text"] and i["kind"] == "File"
assert c.inspect(mk("l2.txt", "a\nb\n"))["lines"] == 2
assert len(i["perm_octal"]) == 3 and i["perm_text"].startswith("-")
r = c.report(i); assert "Plain text" in r and "5 bytes" in r and "Permissions" in r and "3 lines" in r
fi = c.inspect(d); assert fi["kind"] == "Folder" and fi["items"] > 5 and "Items inside" in c.report(fi)
os.chmod(t, 0o755); assert c.inspect(t)["executable"] and c.inspect(t)["perm_octal"] == "755"
if hasattr(os, "symlink"):
    ln = os.path.join(d, "ln"); os.symlink(t, ln)
    assert c.inspect(ln)["link"] == t and "Link to" in c.report(c.inspect(ln))
    os.symlink(os.path.join(d, "nowhere"), os.path.join(d, "dead"))
    assert c.inspect(os.path.join(d, "dead"))["kind"] == "Broken link"
for bad_path in ("", os.path.join(d, "missing")):
    try:
        c.inspect(bad_path); raise SystemExit("should fail")
    except c.InspectError:
        pass
assert c.human_size(5) == "5 bytes" and c.human_size(2048) == "2.0 KB" and c.human_size(5 * 1024 ** 2) == "5.0 MB"

# hashes
data = b"hello world" * 1000
p = mk("h.bin", data)
h = c.hash_file(p)
assert h["md5"] == hashlib.md5(data).hexdigest() and h["sha256"] == hashlib.sha256(data).hexdigest()
assert set(h) == set(c.HASHES) and "SHA256" in c.hash_report(h)
seen = []
assert c.hash_file(p, ("sha1",), progress=lambda a, b: seen.append((a, b)))["sha1"] == hashlib.sha1(data).hexdigest()
assert seen[-1] == (len(data), len(data))
assert c.hash_file(p, cancelled=lambda: True) is None
ok, msg = c.verify(h["sha256"].upper(), h); assert ok and "MATCH" in msg
ok, msg = c.verify(f"{h['md5']}  h.bin", h); assert ok
ok, msg = c.verify(f"SHA256 (h.bin) = {h['sha256']}", h); assert ok
ok, msg = c.verify("0" * 64, h); assert not ok and "DIFFERENT" in msg
for bad_in in ("", "nothex", "abc123"):
    try:
        c.verify(bad_in, h); raise SystemExit("should fail")
    except c.InspectError:
        pass
try:
    c.verify("0" * 64, {"md5": "x"}); raise SystemExit("needs calc")
except c.InspectError as e:
    assert "first" in str(e)

# previews
assert c.text_preview(t).startswith("a\nb\nc")
big = mk("big.txt", "line\n" * 5000)
tp_ = c.text_preview(big); assert tp_.endswith("[... file continues ...]") and len(tp_) < 6100
try:
    c.text_preview(mk("b.bin", bytes(range(256)))); raise SystemExit("binary")
except c.InspectError:
    pass
hx = c.hex_dump(mk("hx.bin", b"ABC\x00" + bytes(range(20))))
first = hx.splitlines()[0]
assert first.startswith("00000000  41 42 43 00 00 01 02 03") and first.endswith("|ABC.............|"), first
assert len(hx.splitlines()) == 2 and c.hex_dump(mk("e.bin", b"")) == "(empty)"
assert c.hex_dump(p, 16, 16).startswith("00000010")
print("file inspect core: all ok")
