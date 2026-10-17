# core/converter_core.py - the File Converter's engine. Kivy-free, so it can
# be unit-tested without a window.
#
#   images    : Pillow  (works on Android + desktop)
#   documents : pure Python - txt / md / html / docx / csv / tsv / json,
#               converted through ONE intermediate block model (the same one
#               screens/md_parse.py produces), so every document format can
#               reach every other one it makes sense for
#   audio/video: ffmpeg, if it is installed (desktop). Android apps cannot
#               ship ffmpeg here, so those are reported as unavailable
#               instead of failing mysteriously.
#
# convert_file() raises ConvertError with a human-readable message.

import os
import io
import re
import csv
import json
import html as _html
import shutil
import zipfile
import subprocess
import textwrap
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

_HERE = os.path.dirname(os.path.abspath(__file__))


class ConvertError(Exception):
    pass


# ── kinds & targets ─────────────────────────────────────────────────────────
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif", "tif", "tiff",
              "ico", "ppm"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "oga", "flac", "m4a", "aac", "opus", "wma"}
VIDEO_EXTS = {"mp4", "mkv", "webm", "mov", "avi", "m4v", "flv", "wmv", "3gp"}
DOC_EXTS = {"txt", "md", "markdown", "html", "htm", "docx", "csv", "tsv",
            "json"}

TARGETS = {
    "image": ["png", "jpg", "webp", "bmp", "gif", "tiff", "ico", "pdf"],
    "audio": ["mp3", "wav", "ogg", "flac", "m4a", "opus"],
    "video": ["mp4", "webm", "mkv", "gif", "mp3", "m4a", "wav", "ogg"],
    "doc":   ["txt", "md", "html", "docx", "pdf", "csv", "tsv", "json"],
}
KIND_LABEL = {"image": "Images", "audio": "Audio", "video": "Video",
              "doc": "Documents / data"}


def ext_of(path):
    return os.path.splitext(path)[1].lower().lstrip(".")


def kind_of(path):
    e = ext_of(path)
    if e in IMAGE_EXTS:
        return "image"
    if e in AUDIO_EXTS:
        return "audio"
    if e in VIDEO_EXTS:
        return "video"
    if e in DOC_EXTS:
        return "doc"
    return None


def _norm(e):
    return {"jpeg": "jpg", "tif": "tiff", "markdown": "md", "htm": "html",
            "oga": "ogg"}.get(e, e)


def targets_for(path):
    """Target extensions that make sense for this file (not its own type)."""
    k = kind_of(path)
    if not k:
        return []
    src = _norm(ext_of(path))
    out = [t for t in TARGETS[k] if t != src]
    if k == "doc":
        # csv/tsv/json only make sense from tabular sources
        if src not in ("csv", "tsv", "json", "docx", "html", "md"):
            out = [t for t in out if t not in ("csv", "tsv", "json")]
        # nothing converts INTO docx/html meaningfully from data? it does
        # (tables) - keep; but docx is only an output, never from itself
    return out


def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    for cand in ("/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg",
                 "/opt/homebrew/bin/ffmpeg", r"C:\ffmpeg\bin\ffmpeg.exe"):
        if os.path.exists(cand):
            return cand
    return None


def _on_android():
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


def unavailable_reason(path, target):
    """None if this conversion can run here, else why not."""
    k = kind_of(path)
    if k in ("audio", "video"):
        if _on_android():
            return ("Audio and video conversion isn't available on Android: "
                    "due to Android limitations it's not possible to bundle "
                    "ffmpeg inside the app. Use the desktop version for "
                    "these.")
        if not find_ffmpeg():
            return ("ffmpeg is not installed. Install it (Pop!OS/Ubuntu: "
                    "sudo apt install ffmpeg) and try again.")
    if k == "image":
        try:
            from PIL import features
        except ImportError:
            return "Pillow isn't installed."
        # phone builds of Pillow are sometimes compiled without a codec;
        # say so up front instead of failing halfway through a batch
        for name, feat in (("WebP", "webp"), ("JPEG", "jpg")):
            if feat in (_norm(ext_of(path)), target):
                try:
                    if not features.check(feat):
                        return (f"This build of the app can't read/write "
                                f"{name} images.")
                except Exception:
                    pass
    return None


def unique_path(folder, stem, ext):
    p = os.path.join(folder, f"{stem}.{ext}")
    n = 2
    while os.path.exists(p):
        p = os.path.join(folder, f"{stem} ({n}).{ext}")
        n += 1
    return p


# ── public entry point ──────────────────────────────────────────────────────
def convert_file(src, out_dir, target, options=None, cancel=None):
    """Convert `src` to `target` (extension) inside out_dir. Returns the new
    file's path. `cancel` is an optional threading.Event (ffmpeg only)."""
    options = options or {}
    k = kind_of(src)
    if not k:
        raise ConvertError(f"Unsupported file type: .{ext_of(src)}")
    if not os.path.isfile(src):
        raise ConvertError("File not found.")
    if target not in targets_for(src):
        raise ConvertError(f".{ext_of(src)} can't be converted to .{target}")
    why = unavailable_reason(src, target)
    if why:
        raise ConvertError(why)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    dst = unique_path(out_dir, stem, target)
    try:
        if k == "image":
            _convert_image(src, dst, target, options)
        elif k in ("audio", "video"):
            _convert_av(src, dst, k, target, options, cancel)
        else:
            _convert_doc(src, dst, target, options)
    except ConvertError:
        _rm(dst)
        raise
    except Exception as e:
        _rm(dst)
        if type(e).__name__ == "UnidentifiedImageError":
            raise ConvertError("Not a valid image (damaged, or not really "
                               f".{ext_of(src)}).")
        raise ConvertError(f"{type(e).__name__}: {e}")
    return dst


def _rm(p):
    try:
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


# ── images ──────────────────────────────────────────────────────────────────
_PIL_FORMAT = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP", "bmp": "BMP",
               "gif": "GIF", "tiff": "TIFF", "ico": "ICO", "pdf": "PDF"}


def _convert_image(src, dst, target, opt):
    from PIL import Image, ImageOps
    quality = int(opt.get("quality", 90))
    max_side = int(opt.get("max_side", 0) or 0)
    im = Image.open(src)
    animated = getattr(im, "n_frames", 1) > 1
    if animated and target in ("gif", "webp"):
        frames, durations = [], []
        for i in range(im.n_frames):
            im.seek(i)
            fr = im.convert("RGBA")
            if max_side:
                fr.thumbnail((max_side, max_side))
            frames.append(fr)
            durations.append(im.info.get("duration", 100))
        frames[0].save(dst, save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, format=_PIL_FORMAT[target],
                       **({"quality": quality} if target == "webp" else {}))
        return
    im.seek(0)
    try:
        im = ImageOps.exif_transpose(im)        # phone photos: honour rotation
    except Exception:
        pass
    if max_side:
        im.thumbnail((max_side, max_side))
    if target in ("jpg", "bmp", "pdf"):
        # no alpha channel in these: flatten onto white
        if im.mode in ("RGBA", "LA", "P"):
            rgba = im.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
    kw = {}
    if target == "jpg":
        kw = {"quality": quality, "optimize": True}
    elif target == "webp":
        kw = {"quality": quality}
    elif target == "png":
        kw = {"optimize": True}
    elif target == "pdf":
        kw = {"resolution": 150.0}
    elif target == "ico":
        side = min(256, max(im.size))
        sizes = [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= side]
        kw = {"sizes": sizes or [(side, side)]}
        if im.mode not in ("RGBA", "RGB"):
            im = im.convert("RGBA")
        if im.size[0] != im.size[1]:            # make it square (pad)
            m = max(im.size)
            sq = Image.new("RGBA", (m, m), (0, 0, 0, 0))
            sq.paste(im, ((m - im.size[0]) // 2, (m - im.size[1]) // 2))
            im = sq
    elif target == "gif":
        im = im.convert("P", palette=Image.ADAPTIVE) if im.mode != "P" else im
    im.save(dst, format=_PIL_FORMAT[target], **kw)


# ── audio / video (ffmpeg) ──────────────────────────────────────────────────
_AUDIO_ARGS = {
    "mp3":  ["-vn", "-codec:a", "libmp3lame", "-q:a", "2"],
    "wav":  ["-vn", "-codec:a", "pcm_s16le"],
    "ogg":  ["-vn", "-codec:a", "libvorbis", "-q:a", "5"],
    "flac": ["-vn", "-codec:a", "flac"],
    "m4a":  ["-vn", "-codec:a", "aac", "-b:a", "192k"],
    "opus": ["-vn", "-codec:a", "libopus", "-b:a", "128k"],
}
_VIDEO_ARGS = {
    "mp4":  ["-c:v", "libx264", "-crf", "23", "-preset", "medium",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0",
             "-c:a", "libopus", "-b:a", "128k"],
    "mkv":  ["-c:v", "libx264", "-crf", "23", "-preset", "medium",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k"],
    "gif":  ["-an", "-vf",
             "fps=12,scale=480:-1:flags=lanczos,split[s0][s1];"
             "[s0]palettegen[p];[s1][p]paletteuse"],
}


def build_ffmpeg_cmd(ffmpeg, src, dst, kind, target):
    if target in _AUDIO_ARGS:
        args = _AUDIO_ARGS[target]
    elif target in _VIDEO_ARGS and kind == "video":
        args = _VIDEO_ARGS[target]
    else:
        raise ConvertError(f"Can't convert {kind} to .{target}")
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", src] + args + [dst]


def _convert_av(src, dst, kind, target, opt, cancel):
    cmd = build_ffmpeg_cmd(find_ffmpeg(), src, dst, kind, target)
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    while True:
        try:
            _, err = p.communicate(timeout=0.3)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                p.terminate()
                p.wait()
                raise ConvertError("Cancelled.")
    if p.returncode != 0:
        tail = (err or b"").decode(errors="replace").strip().splitlines()
        raise ConvertError("ffmpeg failed: " + (tail[-1] if tail else
                           f"exit code {p.returncode}"))


# ── documents: readers (-> blocks) ──────────────────────────────────────────
def _read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _table_block(header, rows):
    n = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    header = list(header) + [""] * (n - len(header))
    rows = [list(r) + [""] * (n - len(r)) for r in rows]
    return {"type": "table", "aligns": ["left"] * n,
            "header": [str(h) for h in header],
            "rows": [[str(c) for c in r] for r in rows]}


def read_blocks(path):
    e = _norm(ext_of(path))
    if e == "txt":
        txt = _read_text(path)
        return [{"type": "para", "text": p.strip("\n")}
                for p in re.split(r"\n\s*\n", txt) if p.strip()]
    if e == "md":
        from screens.md_parse import parse_markdown
        return parse_markdown(_read_text(path))
    if e == "html":
        return _html_to_blocks(_read_text(path))
    if e == "docx":
        return _docx_to_blocks(path)
    if e in ("csv", "tsv"):
        return [_read_delimited(path, e)]
    if e == "json":
        return [_json_to_table(_read_text(path))]
    raise ConvertError(f"Can't read .{e}")


def _read_delimited(path, e):
    txt = _read_text(path)
    if e == "tsv":
        delim = "\t"
    else:
        try:
            delim = csv.Sniffer().sniff(txt[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delim = ","
    rows = list(csv.reader(io.StringIO(txt), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ConvertError("The file is empty.")
    return _table_block(rows[0], rows[1:])


def _json_to_table(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConvertError(f"Not valid JSON: {e}")
    if isinstance(data, dict):
        if data and all(isinstance(v, list) for v in data.values()):
            keys = list(data)
            n = max(len(v) for v in data.values())
            rows = [[_cell(data[k][i]) if i < len(data[k]) else ""
                     for k in keys] for i in range(n)]
            return _table_block(keys, rows)
        return _table_block(["key", "value"],
                            [[k, _cell(v)] for k, v in data.items()])
    if isinstance(data, list):
        if data and all(isinstance(x, dict) for x in data):
            keys = []
            for x in data:
                for k in x:
                    if k not in keys:
                        keys.append(k)
            return _table_block(keys, [[_cell(x.get(k, "")) for k in keys]
                                       for x in data])
        if data and all(isinstance(x, list) for x in data):
            return _table_block(
                [_cell(c) for c in data[0]],
                [[_cell(c) for c in r] for r in data[1:]])
        return _table_block(["value"], [[_cell(x)] for x in data])
    raise ConvertError("This JSON has no table-like structure.")


def _cell(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return "" if v is None else str(v)


# html -> blocks
class _HTMLBlocks(HTMLParser):
    SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._buf = []                 # inline text of the current block
        self._skip = 0
        self._kind = None              # heading level / "p" / "li" / "pre"
        self._lists = []               # stack of {"ordered":b, "items":[...]}
        self._li_done = set()          # list depths whose open <li> already
                                       # got its item (it has a nested list)
        self._quote = 0
        self._table = None
        self._cell = None
        self._href = []

    # helpers
    def _flush_para(self):
        txt = "".join(self._buf).strip()
        self._buf = []
        return txt

    def _emit(self, block):
        if self._lists:
            return
        self.blocks.append({"type": "quote", "blocks": [block]}
                           if self._quote else block)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        if self._skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self._flush_para_into_para()
            self._kind = int(tag[1])
        elif tag in ("p", "div", "section", "article"):
            self._flush_para_into_para()
        elif tag in ("ul", "ol"):
            if self._lists:
                txt = self._flush_para()          # text of the parent <li>
                if txt:
                    self._lists[-1]["items"].append(
                        {"blocks": [{"type": "para", "text": txt}],
                         "task": None})
                    self._li_done.add(len(self._lists))
            else:
                self._flush_para_into_para()
            self._lists.append({"ordered": tag == "ol", "items": []})
        elif tag == "li":
            self._buf = []
            self._kind = "li"
        elif tag == "pre":
            self._flush_para_into_para()
            self._kind = "pre"
        elif tag == "blockquote":
            self._flush_para_into_para()
            self._quote += 1
        elif tag == "hr":
            self._flush_para_into_para()
            self._emit({"type": "hr"})
        elif tag == "br":
            self._buf.append("\n")
        elif tag in ("b", "strong"):
            self._buf.append("**")
        elif tag in ("i", "em"):
            self._buf.append("*")
        elif tag in ("s", "del", "strike"):
            self._buf.append("~~")
        elif tag == "code" and self._kind != "pre":
            self._buf.append("`")
        elif tag == "a":
            self._href.append(a.get("href", ""))
            self._buf.append("[")
        elif tag == "img":
            self._buf.append(f"![{a.get('alt', '')}]({a.get('src', '')})")
        elif tag == "table":
            self._flush_para_into_para()
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._table.append([])
        elif tag in ("td", "th") and self._table is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            txt = self._flush_para()
            if txt:
                self._emit({"type": "heading", "level": int(tag[1]),
                            "text": txt})
            self._kind = None
        elif tag in ("p", "div", "section", "article"):
            self._flush_para_into_para()
        elif tag == "li":
            txt = self._flush_para()
            depth = len(self._lists)
            if depth in self._li_done:
                self._li_done.discard(depth)       # item was already added
            elif self._lists:
                self._lists[-1]["items"].append(
                    {"blocks": [{"type": "para", "text": txt}], "task": None})
            self._kind = None
        elif tag in ("ul", "ol"):
            if self._lists:
                lst = self._lists.pop()
                blk = {"type": "list", "ordered": lst["ordered"], "start": 1
                       if lst["ordered"] else 0, "items": lst["items"]}
                if self._lists:          # nested: attach to the parent's
                    parent = self._lists[-1]["items"]
                    if parent:
                        parent[-1]["blocks"].append(blk)
                else:
                    self._emit(blk)
        elif tag == "pre":
            txt = "".join(self._buf).strip("\n")
            self._buf = []
            if txt:
                self._emit({"type": "code", "lang": "", "text": txt})
            self._kind = None
        elif tag == "blockquote":
            self._flush_para_into_para()
            self._quote = max(0, self._quote - 1)
        elif tag in ("b", "strong"):
            self._buf.append("**")
        elif tag in ("i", "em"):
            self._buf.append("*")
        elif tag in ("s", "del", "strike"):
            self._buf.append("~~")
        elif tag == "code" and self._kind != "pre":
            self._buf.append("`")
        elif tag == "a":
            href = self._href.pop() if self._href else ""
            self._buf.append(f"]({href})")
        elif tag in ("td", "th") and self._table is not None and self._cell \
                is not None:
            self._table[-1].append("".join(self._cell).strip())
            self._cell = None
        elif tag == "table" and self._table is not None:
            rows = [r for r in self._table if r]
            self._table = None
            if rows:
                self._emit(_table_block(rows[0], rows[1:]))

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)
            return
        if self._kind != "pre":
            data = re.sub(r"\s+", " ", data)
        self._buf.append(data)

    def _flush_para_into_para(self):
        if self._lists or self._kind in ("li",):
            return
        txt = self._flush_para()
        if txt:
            self._emit({"type": "para", "text": txt})

    def close(self):
        super().close()
        self._flush_para_into_para()


def _html_to_blocks(text):
    p = _HTMLBlocks()
    p.feed(text)
    p.close()
    return p.blocks


# docx -> blocks
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_to_blocks(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise ConvertError("Not a valid .docx file.")
    root = ET.fromstring(xml)
    body = root.find(_W + "body")
    blocks, cur_list = [], None
    for el in (body if body is not None else []):
        if el.tag == _W + "p":
            text, style, is_item = _docx_par(el)
            if text.startswith("\u2022 "):          # our own bullets (and
                is_item, text = True, text[2:]       # Word's typed ones)
            if is_item:
                if cur_list is None:
                    cur_list = {"type": "list", "ordered": False, "start": 0,
                                "items": []}
                    blocks.append(cur_list)
                cur_list["items"].append(
                    {"blocks": [{"type": "para", "text": text}], "task": None})
                continue
            cur_list = None
            if not text.strip():
                continue
            m = re.match(r"heading\s*([1-6])", style, re.I)
            if m or style.lower() == "title":
                # headings are written bold; that is the style, not emphasis
                text = re.sub(r"^\*\*(.*)\*\*$", r"\1", text.strip(),
                              flags=re.S)
            if m:
                blocks.append({"type": "heading", "level": int(m.group(1)),
                               "text": text})
            elif style.lower() == "title":
                blocks.append({"type": "heading", "level": 1, "text": text})
            else:
                blocks.append({"type": "para", "text": text})
        elif el.tag == _W + "tbl":
            cur_list = None
            rows = []
            for tr in el.iter(_W + "tr"):
                rows.append(["".join(_docx_par(p)[0] for p in tc.iter(_W + "p"))
                             .strip() for tc in tr.findall(_W + "tc")])
            rows = [r for r in rows if r]
            if rows:
                rows[0] = [re.sub(r"^\*\*(.*)\*\*$", r"\1", c, flags=re.S)
                           for c in rows[0]]       # header cells are bold
                blocks.append(_table_block(rows[0], rows[1:]))
        else:
            cur_list = None
    return blocks


def _docx_par(p):
    style, is_item = "", p.find(f"{_W}pPr/{_W}numPr") is not None
    ps = p.find(f"{_W}pPr/{_W}pStyle")
    if ps is not None:
        style = ps.get(_W + "val", "")
        if style.lower().startswith("list"):
            is_item = True
    out = []
    for r in p.iter(_W + "r"):
        txt = ""
        for c in r:
            if c.tag == _W + "t":
                txt += c.text or ""
            elif c.tag == _W + "tab":
                txt += "\t"
            elif c.tag in (_W + "br", _W + "cr"):
                txt += "\n"
        if not txt:
            continue
        rpr = r.find(_W + "rPr")
        bold = rpr is not None and rpr.find(_W + "b") is not None
        ital = rpr is not None and rpr.find(_W + "i") is not None
        if txt.strip():
            lead = txt[:len(txt) - len(txt.lstrip())]
            trail = txt[len(txt.rstrip()):]
            core = txt.strip()
            if bold:
                core = f"**{core}**"
            if ital:
                core = f"*{core}*"
            txt = lead + core + trail
        out.append(txt)
    return "".join(out), style, is_item


# ── documents: writers (blocks ->) ──────────────────────────────────────────
def _esc(s):
    return _html.escape(s, quote=False)


def inline_to_html(s):
    s = _esc(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r'<img alt="\1" src="\2">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s, flags=re.S)
    s = re.sub(r"__(.+?)__", r"<strong>\1</strong>", s, flags=re.S)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s,
               flags=re.S)
    s = re.sub(r"~~(.+?)~~", r"<del>\1</del>", s, flags=re.S)
    s = re.sub(r"\[color=([#\w]+)\](.+?)\[/color\]",
               r'<span style="color:\1">\2</span>', s, flags=re.S)
    return s.replace("\n", "<br>\n")


def inline_to_plain(s):
    s = re.sub(r"\[color=[#\w]+\](.+?)\[/color\]", r"\1", s, flags=re.S)
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1 (\2)", s)
    s = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2),
               s, flags=re.S)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s,
               flags=re.S)
    s = re.sub(r"~~(.+?)~~", r"\1", s, flags=re.S)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s


def blocks_to_html(blocks, title="Document"):
    def rend(bs):
        out = []
        for b in bs:
            t = b["type"]
            if t == "heading":
                n = min(max(b["level"], 1), 6)
                out.append(f"<h{n}>{inline_to_html(b['text'])}</h{n}>")
            elif t == "para":
                out.append(f"<p>{inline_to_html(b['text'])}</p>")
            elif t == "quote":
                out.append(f"<blockquote>{rend(b['blocks'])}</blockquote>")
            elif t == "list":
                tag = "ol" if b["ordered"] else "ul"
                items = []
                for it in b["items"]:
                    box = ""
                    if it.get("task") is not None:
                        box = ('<input type="checkbox" disabled%s> '
                               % (" checked" if it["task"] else ""))
                    inner = rend(it["blocks"])
                    inner = re.sub(r"^<p>(.*?)</p>", r"\1", inner, count=1,
                                   flags=re.S)
                    items.append(f"<li>{box}{inner}</li>")
                out.append(f"<{tag}>{''.join(items)}</{tag}>")
            elif t == "code":
                out.append(f"<pre><code>{_esc(b['text'])}</code></pre>")
            elif t == "hr":
                out.append("<hr>")
            elif t == "table":
                head = "".join(f"<th>{inline_to_html(c)}</th>"
                               for c in b["header"])
                rows = "".join("<tr>" + "".join(
                    f"<td>{inline_to_html(c)}</td>" for c in r) + "</tr>"
                    for r in b["rows"])
                out.append(f"<table><thead><tr>{head}</tr></thead>"
                           f"<tbody>{rows}</tbody></table>")
            elif t == "image":
                out.append(f'<img alt="{_esc(b.get("alt", ""))}" '
                           f'src="{_esc(b.get("src", b.get("url", "")))}">')
        return "\n".join(out)
    css = ("body{font-family:system-ui,sans-serif;max-width:46em;margin:2em "
           "auto;padding:0 1em;line-height:1.6;color:#222;background:#fff}"
           "table{border-collapse:collapse}td,th{border:1px solid #bbb;"
           "padding:.3em .6em}pre{background:#f3f3f3;padding:.8em;overflow:"
           "auto}blockquote{border-left:4px solid #bbb;margin-left:0;"
           "padding-left:1em;color:#555}img{max-width:100%}"
           "@media(prefers-color-scheme:dark){body{background:#161616;"
           "color:#e6e6e6}pre{background:#222}td,th{border-color:#555}}")
    return (f"<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{_esc(title)}</title><style>{css}</style></head>\n"
            f"<body>\n{rend(blocks)}\n</body></html>\n")


def blocks_to_md(blocks):
    def rend(bs, indent=""):
        out = []
        for b in bs:
            t = b["type"]
            if t == "heading":
                out.append(f"{indent}{'#' * b['level']} {b['text']}")
            elif t == "para":
                out.append("\n".join(indent + ln
                                     for ln in b["text"].split("\n")))
            elif t == "quote":
                inner = rend(b["blocks"])
                out.append("\n".join("> " + ln for ln in inner.split("\n")))
            elif t == "list":
                n = b.get("start") or 1
                lines = []
                for it in b["items"]:
                    mark = f"{n}. " if b["ordered"] else "- "
                    n += 1
                    if it.get("task") is not None:
                        mark += "[x] " if it["task"] else "[ ] "
                    parts = []
                    for sub in it["blocks"]:
                        parts.append(rend([sub], "  " if parts else ""))
                    body = "\n".join(parts).split("\n")
                    lines.append(indent + mark + body[0])
                    lines += [indent + "  " + x for x in body[1:]]
                out.append("\n".join(lines))
            elif t == "code":
                out.append(f"{indent}```{b.get('lang', '')}\n{b['text']}\n```")
            elif t == "hr":
                out.append(f"{indent}---")
            elif t == "table":
                out.append(_md_table(b))
            elif t == "image":
                out.append(f"![{b.get('alt', '')}]"
                           f"({b.get('src', b.get('url', ''))})")
        return "\n\n".join(out)
    return rend(blocks) + "\n"


def _md_table(b):
    def row(cells):
        return "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ")
                                 for c in cells) + " |"
    sep = "| " + " | ".join(
        {"left": ":--", "right": "--:", "center": ":-:"}.get(a, "---")
        for a in b["aligns"]) + " |"
    return "\n".join([row(b["header"]), sep] + [row(r) for r in b["rows"]])


def blocks_to_text(blocks):
    def rend(bs, indent=""):
        out = []
        for b in bs:
            t = b["type"]
            if t in ("heading", "para"):
                txt = inline_to_plain(b["text"])
                out.append("\n".join(indent + ln for ln in txt.split("\n")))
            elif t == "quote":
                out.append("\n".join("  | " + ln for ln in
                                     rend(b["blocks"]).split("\n")))
            elif t == "list":
                n = b.get("start") or 1
                lines = []
                for it in b["items"]:
                    mark = f"{n}. " if b["ordered"] else "- "
                    n += 1
                    if it.get("task") is not None:
                        mark += "[x] " if it["task"] else "[ ] "
                    body = "\n".join(rend([s], "  ") for s in
                                     it["blocks"]).strip().split("\n")
                    lines.append(indent + mark + body[0].strip())
                    lines += [indent + "  " + x.strip() for x in body[1:]]
                out.append("\n".join(lines))
            elif t == "code":
                out.append(b["text"])
            elif t == "hr":
                out.append("-" * 24)
            elif t == "table":
                out.append("\n".join("\t".join(r) for r in
                                     [b["header"]] + b["rows"]))
        return "\n\n".join(out)
    return rend(blocks) + "\n"


def _first_table(blocks):
    def find(bs):
        for b in bs:
            if b["type"] == "table":
                return b
            if b["type"] == "quote":
                r = find(b["blocks"])
                if r:
                    return r
        return None
    t = find(blocks)
    if not t:
        raise ConvertError("This file has no table to turn into CSV/JSON.")
    return t


def table_to_delimited(table, delim):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    w.writerow(table["header"])
    w.writerows(table["rows"])
    return buf.getvalue()


def table_to_json(table):
    keys, seen = [], {}
    for i, h in enumerate(table["header"]):
        h = h or f"column{i + 1}"
        if h in seen:                       # keep keys unique
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 1
        keys.append(h)
    return json.dumps([dict(zip(keys, r)) for r in table["rows"]],
                      ensure_ascii=False, indent=2) + "\n"


def blocks_to_docx(path, blocks):
    """Minimal but valid .docx (Word/LibreOffice/Google Docs open it)."""
    def esc(s):
        return _html.escape(s, quote=False)

    def runs(text):
        """md inline -> <w:r> runs (bold/italic/code)."""
        text = inline_to_plain_keep_marks(text)
        out = []
        for part in re.split(r"(\*\*.+?\*\*|\*(?!\s).+?(?<!\s)\*|`[^`]+`)",
                             text, flags=re.S):
            if not part:
                continue
            props = ""
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                part, props = part[2:-2], "<w:b/>"
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                part, props = part[1:-1], '<w:rFonts w:ascii="Courier New" ' \
                                          'w:hAnsi="Courier New"/>'
            elif part.startswith("*") and part.endswith("*") and len(part) > 2:
                part, props = part[1:-1], "<w:i/>"
            lines = part.split("\n")
            for i, ln in enumerate(lines):
                br = "<w:br/>" if i else ""
                out.append(f"<w:r>{('<w:rPr>' + props + '</w:rPr>') if props else ''}"
                           f"{br}<w:t xml:space=\"preserve\">{esc(ln)}</w:t></w:r>")
        return "".join(out)

    def par(text, style=None, size=None, bold=False, num=False, mono=False):
        ppr = ""
        if num:
            ppr += '<w:ind w:left="360" w:hanging="360"/>'
        if ppr or style:
            st = f'<w:pStyle w:val="{style}"/>' if style else ""
            ppr = f"<w:pPr>{st}{ppr}</w:pPr>"
        r = runs(text)
        if size or bold or mono:
            extra = (f'<w:sz w:val="{size}"/>' if size else "") + \
                    ("<w:b/>" if bold else "") + \
                    ('<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/>'
                     if mono else "")
            r = r.replace("<w:r>", f"<w:r><w:rPr>{extra}</w:rPr>") \
                if "<w:rPr>" not in r else r.replace("<w:rPr>",
                                                     f"<w:rPr>{extra}")
        return f"<w:p>{ppr}{r}</w:p>"

    body = []

    def emit(bs, quote=False):
        for b in bs:
            t = b["type"]
            if t == "heading":
                sizes = {1: 40, 2: 34, 3: 30, 4: 28, 5: 26, 6: 24}
                body.append(par(b["text"], style=f"Heading{b['level']}",
                                size=sizes.get(b["level"], 24), bold=True))
            elif t == "para":
                body.append(par(("    " if quote else "") + b["text"]))
            elif t == "quote":
                emit(b["blocks"], True)
            elif t == "list":
                n = b.get("start") or 1
                for it in b["items"]:
                    mark = f"{n}. " if b["ordered"] else "\u2022 "
                    n += 1
                    if it.get("task") is not None:
                        mark += "[x] " if it["task"] else "[ ] "
                    first = True
                    for sub in it["blocks"]:
                        if sub["type"] == "para":
                            body.append(par((mark if first else "    ")
                                            + sub["text"], num=True))
                            first = False
                        else:
                            emit([sub])
            elif t == "code":
                for ln in b["text"].split("\n"):
                    body.append(par(ln, mono=True))
            elif t == "hr":
                body.append(par("_" * 40))
            elif t == "table":
                rows = [b["header"]] + b["rows"]
                tr = []
                for ri, r in enumerate(rows):
                    tcs = "".join(
                        "<w:tc><w:tcPr><w:tcW w:w=\"0\" w:type=\"auto\"/>"
                        "</w:tcPr>" + par(c, bold=(ri == 0)) + "</w:tc>"
                        for c in r)
                    tr.append(f"<w:tr>{tcs}</w:tr>")
                body.append(
                    '<w:tbl><w:tblPr><w:tblBorders>' + "".join(
                        f'<w:{s} w:val="single" w:sz="4" w:color="888888"/>'
                        for s in ("top", "left", "bottom", "right",
                                  "insideH", "insideV"))
                    + '</w:tblBorders></w:tblPr>' + "".join(tr) + '</w:tbl>')
                body.append("<w:p/>")
    emit(blocks)
    if not body:
        body.append("<w:p/>")
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           f'<w:document {ns}><w:body>{"".join(body)}'
           f'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           f'<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
           f'w:left="1134"/></w:sectPr></w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
          'content-types"><Default Extension="rels" ContentType="application/'
          'vnd.openxmlformats-package.relationships+xml"/><Default '
          'Extension="xml" ContentType="application/xml"/><Override '
          'PartName="/word/document.xml" ContentType="application/vnd.'
          'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)


def inline_to_plain_keep_marks(s):
    """Docx runs: keep **bold** / *italic* / `code` marks (turned into run
    properties above) but flatten links, images, colour and strike."""
    s = re.sub(r"\[color=[#\w]+\](.+?)\[/color\]", r"\1", s, flags=re.S)
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1 (\2)", s)
    s = re.sub(r"__(.+?)__", r"**\1**", s, flags=re.S)
    s = re.sub(r"~~(.+?)~~", r"\1", s, flags=re.S)
    return s


# PDF: text rendered onto pages (so it works with Pillow alone)
def _load_font(size):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "/system/fonts/Roboto-Regular.ttf",
              "/system/fonts/DroidSans.ttf",
              "C:\\Windows\\Fonts\\arial.ttf",
              "/Library/Fonts/Arial.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def blocks_to_pdf(path, blocks):
    from PIL import Image, ImageDraw
    W, H, M = 1240, 1754, 110                       # A4 @150 dpi
    body, head, mono = _load_font(27), _load_font(40), _load_font(24)
    text = blocks_to_text(blocks)
    lines = []                                      # (text, font, gap_after)
    heads = {inline_to_plain(b["text"]) for b in blocks
             if b["type"] == "heading"}
    for para in text.split("\n"):
        font = head if para.strip() in heads else body
        if not para.strip():
            lines.append(("", font, 14))
            continue
        width_chars = 200
        # wrap by measured width
        words, cur = para.split(" "), ""
        for w in words:
            trial = (cur + " " + w) if cur else w
            if font.getlength(trial) <= W - 2 * M:
                cur = trial
            else:
                lines.append((cur, font, 0))
                cur = w
        lines.append((cur, font, 0))
    pages, y = [], M
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    for txt, font, gap in lines:
        lh = int(font.size * 1.45) if hasattr(font, "size") else 36
        if y + lh > H - M:
            pages.append(img)
            img = Image.new("RGB", (W, H), "white")
            d = ImageDraw.Draw(img)
            y = M
        if txt:
            d.text((M, y), txt, fill="black", font=font)
        y += lh + gap
    pages.append(img)
    pages[0].save(path, "PDF", resolution=150.0, save_all=True,
                  append_images=pages[1:])


# ── documents: driver ───────────────────────────────────────────────────────
def _convert_doc(src, dst, target, opt):
    blocks = read_blocks(src)
    if not blocks:
        raise ConvertError("The file has no content.")
    title = os.path.splitext(os.path.basename(src))[0]
    if target == "txt":
        data = blocks_to_text(blocks)
    elif target == "md":
        data = blocks_to_md(blocks)
    elif target == "html":
        data = blocks_to_html(blocks, title)
    elif target in ("csv", "tsv"):
        data = table_to_delimited(_first_table(blocks),
                                  "," if target == "csv" else "\t")
    elif target == "json":
        data = table_to_json(_first_table(blocks))
    elif target == "docx":
        blocks_to_docx(dst, blocks)
        return
    elif target == "pdf":
        blocks_to_pdf(dst, blocks)
        return
    else:
        raise ConvertError(f"Can't convert documents to .{target}")
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(data)
