# core/file_inspect_core.py - look inside a file: what it really is, its size,
# dates and permissions, checksums (and checking one you were given), and a
# text or hex preview. Pure Python (standard library only), no Kivy.

import datetime
import hashlib
import json
import mimetypes
import os
import stat
import zipfile

HASHES = ("md5", "sha1", "sha256", "sha512")
HASH_LEN = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
CHUNK = 1024 * 1024
HEAD = 4096                     # bytes read for detection and preview
PREVIEW_TEXT = 6000             # characters of text preview
HEX_BYTES = 512


class InspectError(Exception):
    """A problem worded for the user."""


# (offset, bytes, name, mime, [extensions])
SIGNATURES = [
    (0, b"\x89PNG\r\n\x1a\n", "PNG image", "image/png", ["png"]),
    (0, b"\xff\xd8\xff", "JPEG image", "image/jpeg", ["jpg", "jpeg", "jpe", "jfif"]),
    (0, b"GIF87a", "GIF image", "image/gif", ["gif"]),
    (0, b"GIF89a", "GIF image", "image/gif", ["gif"]),
    (0, b"BM", "BMP image", "image/bmp", ["bmp", "dib"]),
    (0, b"II*\x00", "TIFF image", "image/tiff", ["tif", "tiff"]),
    (0, b"MM\x00*", "TIFF image", "image/tiff", ["tif", "tiff"]),
    (0, b"\x00\x00\x01\x00", "ICO icon", "image/x-icon", ["ico"]),
    (0, b"%PDF-", "PDF document", "application/pdf", ["pdf"]),
    (0, b"PK\x03\x04", "ZIP archive", "application/zip", ["zip"]),
    (0, b"PK\x05\x06", "ZIP archive (empty)", "application/zip", ["zip"]),
    (0, b"\x1f\x8b", "GZIP archive", "application/gzip", ["gz", "tgz"]),
    (0, b"BZh", "BZIP2 archive", "application/x-bzip2", ["bz2", "tbz2"]),
    (0, b"\xfd7zXZ\x00", "XZ archive", "application/x-xz", ["xz", "txz"]),
    (0, b"7z\xbc\xaf\x27\x1c", "7-Zip archive", "application/x-7z-compressed", ["7z"]),
    (0, b"Rar!\x1a\x07", "RAR archive", "application/vnd.rar", ["rar"]),
    (257, b"ustar", "TAR archive", "application/x-tar", ["tar"]),
    (0, b"\x7fELF", "ELF program (Linux)", "application/x-executable", ["", "so", "o", "elf", "bin", "out"]),
    (0, b"MZ", "Windows program (EXE/DLL)", "application/vnd.microsoft.portable-executable", ["exe", "dll", "sys", "scr"]),
    (0, b"\xcf\xfa\xed\xfe", "Mach-O program (macOS)", "application/x-mach-binary", ["", "dylib", "o"]),
    (0, b"\xca\xfe\xba\xbe", "Java class or universal binary", "application/java-vm", ["class", "", "dylib"]),
    (0, b"SQLite format 3\x00", "SQLite database", "application/vnd.sqlite3", ["db", "sqlite", "sqlite3", "db3"]),
    (0, b"ID3", "MP3 audio", "audio/mpeg", ["mp3"]),
    (0, b"\xff\xfb", "MP3 audio", "audio/mpeg", ["mp3"]),
    (0, b"fLaC", "FLAC audio", "audio/flac", ["flac"]),
    (0, b"OggS", "Ogg media", "audio/ogg", ["ogg", "oga", "ogv", "opus"]),
    (0, b"\x1a\x45\xdf\xa3", "Matroska/WebM video", "video/x-matroska", ["mkv", "webm", "mka"]),
    (0, b"{\\rtf", "RTF document", "application/rtf", ["rtf"]),
    (0, b"%!PS", "PostScript", "application/postscript", ["ps", "eps"]),
    (0, b"wOFF", "WOFF font", "font/woff", ["woff"]),
    (0, b"wOF2", "WOFF2 font", "font/woff2", ["woff2"]),
    (0, b"\x00\x01\x00\x00\x00", "TrueType font", "font/ttf", ["ttf"]),
    (0, b"OTTO", "OpenType font", "font/otf", ["otf"]),
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "Old Microsoft Office file", "application/x-ole-storage", ["doc", "xls", "ppt", "msi"]),
]

# zip containers recognised by what is inside
ZIP_KINDS = [
    ("word/", "Word document (DOCX)", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ["docx", "docm"]),
    ("xl/", "Excel workbook (XLSX)", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ["xlsx", "xlsm"]),
    ("ppt/", "PowerPoint (PPTX)", "application/vnd.openxmlformats-officedocument.presentationml.presentation", ["pptx", "pptm"]),
    ("AndroidManifest.xml", "Android app (APK)", "application/vnd.android.package-archive", ["apk"]),
    ("META-INF/MANIFEST.MF", "Java archive (JAR)", "application/java-archive", ["jar", "war"]),
]


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,} bytes" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024.0


def read_head(path, n=HEAD):
    try:
        with open(path, "rb") as f:
            return f.read(n)
    except OSError as e:
        raise InspectError(f"Can't read that file: {e.strerror or e}")


def _is_text(head):
    """(is_text, encoding) from the first bytes."""
    if not head:
        return True, "utf-8"
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"),
                     (b"\xfe\xff", "utf-16")):
        if head.startswith(bom):
            return True, enc
    if b"\x00" in head:
        return False, ""
    try:
        head.decode("utf-8")
        return True, "utf-8"
    except UnicodeDecodeError as e:
        # a multi-byte character cut by the read limit is still text
        if e.start >= len(head) - 3:
            return True, "utf-8"
    ctrl = sum(1 for b in head if b < 9 or 13 < b < 32)
    if ctrl / len(head) < 0.05:
        return True, "latin-1"
    return False, ""


def detect(path, head=None):
    """(name, mime, [extensions], detail) from the contents. Unknown binary is
    'Unknown binary data'; text is told apart (JSON, XML, HTML, SVG, script...)."""
    head = read_head(path) if head is None else head
    if not head:
        return "Empty file", "application/x-empty", [], ""
    for off, sig, name, mime, exts in SIGNATURES:
        if head[off:off + len(sig)] == sig:
            if sig == b"BM" and len(head) < 14:
                continue
            if sig == b"MZ" and len(head) < 64:
                continue
            if sig.startswith(b"PK\x03\x04"):
                return _zip_kind(path, name, mime, exts)
            return name, mime, exts, ""
    if head[4:8] == b"ftyp":
        brand = head[8:12].decode("latin-1").strip()
        if brand.startswith(("M4A", "M4B")):
            return "M4A audio", "audio/mp4", ["m4a", "m4b"], f"brand {brand}"
        if brand.startswith("qt"):
            return "QuickTime video", "video/quicktime", ["mov", "qt"], f"brand {brand}"
        if brand.startswith(("heic", "heix", "mif1")):
            return "HEIC image", "image/heic", ["heic", "heif"], f"brand {brand}"
        return "MP4 video", "video/mp4", ["mp4", "m4v", "3gp"], f"brand {brand}"
    if head[:4] == b"RIFF" and len(head) >= 12:
        kind = head[8:12]
        for tag, name, mime, exts in (
                (b"WAVE", "WAV audio", "audio/wav", ["wav"]),
                (b"AVI ", "AVI video", "video/x-msvideo", ["avi"]),
                (b"WEBP", "WebP image", "image/webp", ["webp"])):
            if kind == tag:
                return name, mime, exts, ""
    text, enc = _is_text(head)
    if not text:
        return "Unknown binary data", "application/octet-stream", [], ""
    sample = head.decode(enc if enc != "latin-1" else "latin-1", errors="replace").lstrip("﻿")
    low = sample.lstrip().lower()
    detail = f"text, {enc}"
    if low.startswith("#!"):
        first = sample.lstrip().splitlines()[0]
        return "Script", "text/x-script", ["sh", "py", "pl", "rb", ""], f"starts with {first[:60]}"
    if low.startswith("<?xml"):
        if "<svg" in low[:2000]:
            return "SVG image", "image/svg+xml", ["svg"], detail
        return "XML document", "application/xml", ["xml", "plist", "xsd", "xsl", "gpx", "kml"], detail
    if low.startswith("<svg"):
        return "SVG image", "image/svg+xml", ["svg"], detail
    if low.startswith("<!doctype html") or low.startswith("<html"):
        return "HTML document", "text/html", ["html", "htm"], detail
    if low[:1] in ("{", "["):
        try:
            with open(path, "rb") as f:
                raw = f.read(2_000_000 + 1)
            if len(raw) <= 2_000_000:
                json.loads(raw.decode(enc, errors="strict"))
                return "JSON data", "application/json", ["json", "geojson", "map"], detail
        except (ValueError, OSError):
            pass
    return "Plain text", "text/plain", [], detail


def _zip_kind(path, name, mime, exts):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "mimetype" in names:
                try:
                    m = z.read("mimetype").decode("ascii", "replace").strip()
                    if m.startswith("application/vnd.oasis.opendocument"):
                        kind = m.rsplit(".", 1)[-1]
                        ext = {"text": "odt", "spreadsheet": "ods",
                               "presentation": "odp"}.get(kind, "odt")
                        return f"OpenDocument ({kind})", m, [ext], ""
                    if m == "application/epub+zip":
                        return "EPUB book", m, ["epub"], ""
                except (KeyError, OSError):
                    pass
            for marker, kname, kmime, kexts in ZIP_KINDS:
                if any(n == marker or n.startswith(marker) for n in names):
                    return kname, kmime, kexts, f"{len(names)} entries inside"
            return name, mime, exts, f"{len(names)} entries inside"
    except (zipfile.BadZipFile, OSError):
        return name + " (damaged?)", mime, exts, ""


def name_check(path, detected_exts):
    """A warning when the file name's extension doesn't fit the contents."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if not detected_exts or ext in detected_exts:
        return ""
    if not ext:
        return "The file name has no extension, but the contents look like " \
               f".{detected_exts[0]}."
    return (f"The name says .{ext}, but the contents look like "
            f".{detected_exts[0]}. It may be renamed or mislabelled.")


def _owner(st):
    try:
        import grp
        import pwd
        return pwd.getpwuid(st.st_uid).pw_name, grp.getgrgid(st.st_gid).gr_name
    except Exception:
        return None, None


def _when(ts):
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return "?"


def inspect(path):
    """Everything that is cheap to find out, as a dict. The folder case gives
    a short summary; hashes are separate (they read the whole file)."""
    path = os.path.expanduser(path.strip().strip('"'))
    if not path:
        raise InspectError("Choose a file first.")
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise InspectError("That file doesn't exist.")
    except OSError as e:
        raise InspectError(f"Can't look at that: {e.strerror or e}")
    info = {"path": os.path.abspath(path), "name": os.path.basename(path.rstrip("/\\")) or path}
    mode = st.st_mode
    info["link"] = os.readlink(path) if stat.S_ISLNK(mode) else ""
    if info["link"]:
        try:
            st = os.stat(path)
            mode = st.st_mode
        except OSError:
            info.update(kind="Broken link", size=0)
            return info
    info["size"] = st.st_size
    info["modified"] = _when(st.st_mtime)
    info["accessed"] = _when(st.st_atime)
    birth = getattr(st, "st_birthtime", None)
    if birth:
        info["created"] = _when(birth)
    else:
        info["changed"] = _when(st.st_ctime)
    info["perm_octal"] = oct(stat.S_IMODE(mode))[2:].zfill(3)
    info["perm_text"] = stat.filemode(mode)
    info["owner"], info["group"] = _owner(st)
    info["executable"] = bool(mode & 0o111) and stat.S_ISREG(mode)
    info["hidden"] = info["name"].startswith(".")
    if stat.S_ISDIR(mode):
        info["kind"] = "Folder"
        try:
            info["items"] = len(os.listdir(path))
        except OSError:
            info["items"] = None
        return info
    if not stat.S_ISREG(mode):
        info["kind"] = "Special file (device, socket or pipe)"
        return info
    info["kind"] = "File"
    head = read_head(path)
    name, mime, exts, detail = detect(path, head)
    info.update(type=name, mime=mime, detail=detail, expected_exts=exts)
    guess = mimetypes.guess_type(path)[0]
    info["mime_from_name"] = guess or ""
    info["warning"] = name_check(path, exts)
    text, enc = _is_text(head)
    info["is_text"], info["encoding"] = text, enc
    if text and st.st_size <= 20_000_000:
        try:
            n = 0
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(CHUNK), b""):
                    n += block.count(b"\n")
            info["lines"] = n + (1 if st.st_size and not _ends_nl(path) else 0)
        except OSError:
            pass
    return info


def _ends_nl(path):
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) == b"\n"


def report(info):
    """The info dict as readable lines."""
    rows = [("Name", info["name"]), ("Where", os.path.dirname(info["path"]))]
    if info.get("link"):
        rows.append(("Link to", info["link"]))
    rows.append(("Kind", info.get("kind", "")))
    if info.get("type"):
        rows.append(("Type (from contents)", info["type"]
                     + (f"  ({info['detail']})" if info.get("detail") else "")))
        rows.append(("MIME type", info["mime"]))
        if info.get("mime_from_name") and info["mime_from_name"] != info["mime"]:
            rows.append(("MIME by file name", info["mime_from_name"]))
    if info.get("items") is not None and info.get("kind") == "Folder":
        rows.append(("Items inside", str(info["items"])))
    if info.get("kind") in ("File", "Folder") or info.get("size"):
        rows.append(("Size", human_size(info.get("size", 0))))
    if info.get("is_text") is not None and info.get("kind") == "File":
        rows.append(("Text file", f"yes ({info['encoding']}), {info.get('lines', '?')} lines"
                     if info["is_text"] and info.get("lines") is not None
                     else (f"yes ({info['encoding']})" if info["is_text"] else "no (binary)")))
    for key, label in (("modified", "Modified"), ("accessed", "Last opened"),
                       ("created", "Created"), ("changed", "Status changed")):
        if info.get(key):
            rows.append((label, info[key]))
    if "perm_octal" in info:
        who = (f"  owner {info['owner']}, group {info['group']}" if info.get("owner") else "")
        rows.append(("Permissions", f"{info['perm_text']}  ({info['perm_octal']}){who}"))
        flags = [t for t, on in (("executable", info.get("executable")),
                                 ("hidden", info.get("hidden"))) if on]
        if flags:
            rows.append(("Flags", ", ".join(flags)))
    out = [f"{k}: {v}" for k, v in rows]
    if info.get("warning"):
        out += ["", "WARNING: " + info["warning"]]
    return "\n".join(out)


# ── checksums ───────────────────────────────────────────────────────────────
def hash_file(path, algos=HASHES, progress=None, cancelled=None):
    """{algo: hexdigest}, one pass over the file. progress(done, total) is called
    as it goes; cancelled() -> True stops (returns None)."""
    try:
        total = os.path.getsize(path)
        hs = {a: hashlib.new(a) for a in algos}
        done = 0
        with open(path, "rb") as f:
            while True:
                block = f.read(CHUNK)
                if not block:
                    break
                for h in hs.values():
                    h.update(block)
                done += len(block)
                if progress:
                    progress(done, total)
                if cancelled and cancelled():
                    return None
    except OSError as e:
        raise InspectError(f"Can't read that file: {e.strerror or e}")
    return {a: h.hexdigest() for a, h in hs.items()}


def verify(expected, digests):
    """(ok, message) comparing a pasted checksum with the computed ones. Accepts
    'hash', 'hash  filename' and 'ALGO (file) = hash' lines; the algorithm is
    told from the length."""
    text = (expected or "").strip()
    if not text:
        raise InspectError("Paste the checksum you want to compare with.")
    token = ""
    for part in text.replace("=", " ").split():
        part = part.strip("()*").lower()
        if len(part) in HASH_LEN and all(c in "0123456789abcdef" for c in part):
            token = part
            break
    if not token:
        raise InspectError("That doesn't look like an MD5, SHA-1, SHA-256 or "
                           "SHA-512 checksum.")
    algo = HASH_LEN[len(token)]
    got = digests.get(algo)
    if got is None:
        raise InspectError(f"Calculate the {algo.upper()} checksum first.")
    if got.lower() == token:
        return True, f"MATCH: the {algo.upper()} checksum is the same."
    return False, (f"DIFFERENT: the {algo.upper()} checksum does not match. "
                   f"The file is not the one that checksum belongs to, or it is damaged.")


def hash_report(digests):
    return "\n".join(f"{a.upper():7} {digests[a]}" for a in HASHES if a in digests)


# ── previews ────────────────────────────────────────────────────────────────
def text_preview(path, limit=PREVIEW_TEXT):
    head = read_head(path, limit * 4 + 4)
    text, enc = _is_text(head[:HEAD])
    if not text:
        raise InspectError("This file isn't text. Use the hex view.")
    s = head.decode(enc, errors="replace")
    more = len(s) > limit
    return s[:limit] + ("\n\n[... file continues ...]" if more or os.path.getsize(path) > len(head) else "")


def hex_dump(path, count=HEX_BYTES, offset=0):
    """Classic 'offset  hex bytes  ascii' lines."""
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read(count)
    except OSError as e:
        raise InspectError(f"Can't read that file: {e.strerror or e}")
    if not data:
        return "(empty)"
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk[:8]) + "  " + " ".join(f"{b:02x}" for b in chunk[8:])
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{offset + i:08x}  {hexs:<49} |{asc}|")
    return "\n".join(lines)
