# screens/md_view.py — the "Styled" view for the Text Editor.
#
# MarkdownView is a ScrollView that renders the block list produced by
# screens/md_parse.py as real Kivy widgets (headings, code blocks with a
# Copy button, quotes, nested lists, task checkboxes, tables, rules,
# local images). It's read-only: editing happens in the Raw view.
#
# Big documents are built in time-boxed slices across frames, so switching
# to Styled on a long file doesn't freeze the window.
#
# Known limits (by design, for now):
#   - no syntax highlighting inside code blocks
#   - long code lines wrap instead of scrolling sideways
#   - text in the styled view can't be mouse-selected (use Copy All / Raw)
#   - only local images render; http(s) images show as a clickable link

import os
import time
import webbrowser

from kivy.uix.scrollview import ScrollView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line, Ellipse
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard
from kivy.properties import NumericProperty

from screens.md_parse import (parse_markdown, inline_to_markup, safe_url,
                              kivy_escape, MUTED_COLOR, LINK_COLOR)

BG        = (0.10, 0.10, 0.12, 1)     # matches the raw editor background
TEXT      = (0.92, 0.92, 0.88, 1)
HEAD_TEXT = (0.97, 0.97, 0.95, 1)
MUTED     = (0.62, 0.64, 0.68, 1)
QUOTE_TXT = (0.74, 0.76, 0.80, 1)
RULE      = (1, 1, 1, 0.16)
CODE_BG   = (0.16, 0.17, 0.21, 1)
CODE_TXT  = (0.86, 0.88, 0.92, 1)
QUOTE_BAR = (0.36, 0.40, 0.48, 1)
TBL_HEAD  = (0.19, 0.20, 0.25, 1)
TBL_ZEBRA = (0.13, 0.14, 0.17, 1)
TBL_LINE  = (1, 1, 1, 0.14)

HEADING_SCALE = {1: 2.0, 2: 1.6, 3: 1.32, 4: 1.15, 5: 1.0, 6: 0.9}
MONO = "RobotoMono-Regular"

# Kivy renders each Label's texture on the *next* frame, so building must be
# budgeted by how many labels we create, not by wall-clock time spent here.
LABELS_PER_FRAME = 24
# A Label is one GPU texture; many GPUs cap textures at 4096-8192 px. Keep
# every label well under that by splitting very long text into stacked chunks.
CHUNK_PX = 1800
FRAME_BUDGET_S = 0.012


# ── small building blocks ────────────────────────────────────────────────────
def _wrap(lbl, w):
    if w > 1:
        lbl.text_size = (w, None)


def _fit(lbl, ts):
    lbl.height = max(ts[1], lbl.font_size * 1.25)


class _VBox(BoxLayout):
    """Vertical box that sizes itself to its children."""
    def __init__(self, spacing=dp(6), **kw):
        kw.setdefault("padding", 0)
        super().__init__(orientation="vertical", size_hint_y=None,
                         spacing=spacing, **kw)
        self._hset = self.setter("height")
        self.bind(minimum_height=self._hset)


def _rel(child):
    """Wrap a block in a RelativeLayout. Kivy stacks from the bottom with
    absolute coordinates, so appending a block shifts every existing block
    and re-lays-out their whole subtrees (quadratic on long documents).
    A RelativeLayout keeps its child in LOCAL coordinates, so moving the
    wrapper moves the subtree for free."""
    rl = RelativeLayout(size_hint_y=None, height=child.height)
    child.size_hint = (1, None)
    child.bind(height=lambda i, h: setattr(rl, "height", h))
    rl.add_widget(child)
    return rl


class _Rule(Widget):
    def __init__(self, thick=dp(1.5), pad=dp(4), **kw):
        super().__init__(size_hint_y=None, height=thick + 2 * pad, **kw)
        self._thick, self._pad = thick, pad
        with self.canvas:
            Color(*RULE)
            self._r = Rectangle()
        self.bind(pos=self._u, size=self._u)

    def _u(self, *a):
        self._r.pos = (self.x, self.y + self._pad)
        self._r.size = (self.width, self._thick)


class _Quote(_VBox):
    def __init__(self, **kw):
        super().__init__(spacing=dp(8),
                         padding=(dp(16), dp(2), 0, dp(2)), **kw)
        with self.canvas.before:
            Color(*QUOTE_BAR)
            self._bar = Rectangle()
        self.bind(pos=self._u, size=self._u)

    def _u(self, *a):
        self._bar.pos = (self.x, self.y)
        self._bar.size = (dp(3), self.height)


class _Bullet(Widget):
    """Bullet drawn on the canvas: cheaper than a Label (no texture) and
    crisper. kind 'dot' for level 0/2, 'dash' for level 1."""
    def __init__(self, kind, fs, **kw):
        super().__init__(size_hint=(None, 1), width=dp(22), **kw)
        self._kind, self._fs = kind, fs
        self.bind(pos=self._d, size=self._d)

    def _d(self, *a):
        self.canvas.clear()
        # NB: use x/y/width/height, not .right/.top - those are cached alias
        # properties that can still hold stale values inside a size callback.
        cx = self.x + self.width - dp(7)
        cy = self.y + self.height - self._fs * 0.64
        with self.canvas:
            Color(*MUTED)
            if self._kind == "dot":
                r = max(dp(2.6), self._fs * 0.17)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            else:
                Line(points=[cx - dp(4), cy, cx + dp(4), cy], width=1.3)


class _Check(Widget):
    """Drawn checkbox (☐/☑ glyphs aren't in Kivy's default font)."""
    def __init__(self, done, px, **kw):
        super().__init__(size_hint=(None, None), size=(px, px), **kw)
        self._done = done
        self.bind(pos=self._d, size=self._d)
        self._d()

    def _d(self, *a):
        self.canvas.clear()
        x, y = self.pos
        w, h = self.size
        with self.canvas:
            if self._done:
                Color(0.24, 0.66, 0.42, 1)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[3])
                Color(1, 1, 1, 1)
                Line(points=[x + w * .22, y + h * .52, x + w * .42,
                             y + h * .30, x + w * .78, y + h * .72],
                     width=1.6)
            else:
                Color(0.62, 0.64, 0.70, 1)
                Line(rounded_rectangle=(x, y, w, h, 3), width=1.2)


class _CodeBlock(_VBox):
    def __init__(self, view, lang, code, **kw):
        super().__init__(spacing=dp(4), padding=dp(10), **kw)
        with self.canvas.before:
            Color(*CODE_BG)
            self._bg = RoundedRectangle(radius=[dp(6)])
        self.bind(pos=self._u, size=self._u)

        head = BoxLayout(size_hint_y=None, height=dp(22), spacing=dp(6))
        head.add_widget(Label(
            text=lang or "code", font_size=max(10, view.fs * 0.72),
            color=MUTED, halign="left", valign="middle"))
        head.children[0].bind(size=lambda i, s: setattr(i, "text_size", s))
        copy = Button(text="Copy", size_hint_x=None, width=dp(54),
                      font_size=max(10, view.fs * 0.72),
                      background_normal="", background_color=(0.24, 0.26, 0.32, 1))
        copy.bind(on_release=lambda *a: (Clipboard.copy(code),
                                         view._status("Code copied")))
        head.add_widget(copy)
        self.add_widget(head)

        lines = (code.expandtabs(4) or " ").split("\n")
        per = view._lines_per_chunk(0.9)
        body = _VBox(spacing=0)
        for i in range(0, len(lines), per):
            lbl = Label(text="\n".join(lines[i:i + per]) or " ",
                        markup=False, font_name=MONO,
                        font_size=view.fs * 0.9, color=CODE_TXT,
                        size_hint_y=None, halign="left", valign="top")
            lbl.bind(width=_wrap, texture_size=_fit)
            body.add_widget(lbl)
            view._made += 1
        self.add_widget(body)
        view._made += 2

    def _u(self, *a):
        self._bg.pos, self._bg.size = self.pos, self.size


class _Cell(AnchorLayout):
    natural_h = NumericProperty(dp(28))

    def __init__(self, view, markup, align, kind, **kw):
        super().__init__(anchor_x="center", anchor_y="top",
                         padding=(dp(8), dp(5)), size_hint_y=None,
                         height=dp(28), **kw)
        self._kind = kind
        with self.canvas.before:
            self._bgc = Color(0, 0, 0, 0)
            self._bg = Rectangle()
        with self.canvas.after:
            Color(*TBL_LINE)
            self._ln = Line(width=1)
        self.bind(pos=self._u, size=self._u)
        if kind == "head":
            self._bgc.rgba = TBL_HEAD
        elif kind == "zebra":
            self._bgc.rgba = TBL_ZEBRA

        lbl = view._label(markup, view.fs * 0.95, TEXT)
        lbl.halign = align
        lbl.bind(height=lambda i, h: setattr(self, "natural_h", h + dp(10)))
        self.natural_h = lbl.height + dp(10)
        self.add_widget(lbl)

    def _u(self, *a):
        self._bg.pos, self._bg.size = self.pos, self.size
        self._ln.rectangle = (self.x, self.y, self.width, self.height)


class _Table(GridLayout):
    """Rows are added by build_rows(), a generator that yields after each row, so a
    huge table can be built a slice per frame."""
    def __init__(self, view, block, **kw):
        cols = max(1, len(block["header"]))
        super().__init__(cols=cols, size_hint_y=None, spacing=0, **kw)
        self.bind(minimum_height=self.setter("height"))
        self._view, self._block = view, block
        self._cell_rows = []

    def build_rows(self):
        block = self._block
        for r, row in enumerate([block["header"]] + block["rows"]):
            kind = "head" if r == 0 else ("zebra" if r % 2 == 0 else "plain")
            cells = []
            for c, txt in enumerate(row):
                mk = inline_to_markup(txt)
                if r == 0 and mk:
                    mk = f"[b]{mk}[/b]"
                cell = _Cell(self._view, mk, block["aligns"][c], kind)
                cell.bind(natural_h=lambda inst, v, ri=r: self._sync(ri))
                cells.append(cell)
                self.add_widget(cell)
            self._cell_rows.append(cells)
            self._sync(r)
            yield

    def _sync(self, r):
        if r >= len(self._cell_rows):
            return
        h = max(c.natural_h for c in self._cell_rows[r])
        for c in self._cell_rows[r]:
            if abs(c.height - h) > 0.5:
                c.height = h


# ── the view ─────────────────────────────────────────────────────────────────
class MarkdownView(ScrollView):
    def __init__(self, base_font=15, on_status=None, **kw):
        super().__init__(do_scroll_x=False, bar_width=dp(8),
                         scroll_type=["bars", "content"], **kw)
        self.base_font = base_font
        self.scale = 1.0
        self.base_dir = None
        self._on_status = on_status
        self._queue = []
        self._ev = None
        self._restore_y = None
        self._made = 0            # labels created (drives the per-frame budget)
        self._width_hint = 0

        with self.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._ubg, size=self._ubg)

        self._col = _VBox(spacing=dp(10), padding=(dp(18), dp(14)))
        self.add_widget(self._col)

    # -- plumbing -------------------------------------------------------------
    @property
    def fs(self):
        return self.base_font * self.scale

    def _ubg(self, *a):
        self._bg.pos, self._bg.size = self.pos, self.size

    def _status(self, msg):
        if self._on_status:
            self._on_status(msg)

    def _on_ref(self, lbl, ref):
        url = safe_url(ref)
        if not url:
            return
        try:
            webbrowser.open(url)
            self._status(f"Opened {url}")
        except Exception as e:
            self._status(f"Couldn't open link: {e}")

    def _label(self, markup, size, color=TEXT):
        lbl = Label(text=markup, markup=True, font_size=size, color=color,
                    size_hint_y=None, halign="left", valign="top",
                    line_height=1.2)
        est = self._est_width()
        if est:
            lbl.text_size = (est, None)      # wrap correctly on first render
        lbl.bind(width=_wrap, texture_size=_fit, on_ref_press=self._on_ref)
        self._made += 1
        return lbl

    def _est_width(self):
        w = self.width if self.width > 150 else self._width_hint
        return max(0, w - dp(36) - dp(12)) if w > 150 else 0

    # -- public API -----------------------------------------------------------
    def set_markdown(self, text, base_dir=None, keep_scroll=False,
                     width_hint=0):
        if self._ev:
            self._ev.cancel()
            self._ev = None
        self.base_dir = base_dir
        self._width_hint = width_hint
        self._restore_y = self.scroll_y if keep_scroll else 1.0
        self._col.clear_widgets()
        self._queue = list(reversed(parse_markdown(text)))
        self._pump(0)
        if self._queue:
            self._ev = Clock.schedule_interval(self._pump, 0)

    def set_scale(self, scale):
        self.scale = scale

    @property
    def building(self):
        return bool(self._queue)

    def _pump(self, dt):
        t0, start = time.perf_counter(), self._made
        while self._queue:
            item = self._queue.pop()
            if callable(item):                       # resume a big list/table
                if not item():
                    self._queue.append(item)
            else:
                w, step = self._build_top(item)
                if w is not None:
                    self._col.add_widget(_rel(w))
                if step:
                    self._queue.append(step)
            if (self._made - start >= LABELS_PER_FRAME
                    or time.perf_counter() - t0 > FRAME_BUDGET_S):
                break
        if not self._queue:
            self._ev = None
            if self._restore_y is not None:
                y, self._restore_y = self._restore_y, None
                Clock.schedule_once(
                    lambda dt: setattr(self, "scroll_y", y), 0)
            return False
        return True

    def _lines_per_chunk(self, size_mult=1.0):
        return max(20, int(CHUNK_PX / (self.fs * size_mult * 1.3)))

    def _make_step(self, gen):
        """Wrap a generator as a resumable per-frame step (True when done)."""
        def step():
            t0, start = time.perf_counter(), self._made
            for _ in gen:
                if (self._made - start >= LABELS_PER_FRAME
                        or time.perf_counter() - t0 > FRAME_BUDGET_S):
                    return False
            return True
        return step

    def _build_top(self, b):
        """Top-level blocks: lists and tables are built incrementally."""
        if b["type"] == "list":
            box, gen = self._list_box(b, 0, False)
            return box, self._make_step(gen)
        if b["type"] == "table":
            tbl = _Table(self, b)
            return tbl, self._make_step(tbl.build_rows())
        return self._build(b, 0, False), None

    # -- block builders -------------------------------------------------------
    def _build(self, b, depth, muted):
        kind = b["type"]
        color = QUOTE_TXT if muted else TEXT
        fs = self.fs

        if kind == "para":
            lines = b["text"].split("\n")
            per = self._lines_per_chunk()
            if len(lines) <= per:
                return self._label(inline_to_markup(b["text"]), fs, color)
            box = _VBox(spacing=0)          # very long paragraph: stacked chunks
            for i in range(0, len(lines), per):
                box.add_widget(self._label(
                    inline_to_markup("\n".join(lines[i:i + per])), fs, color))
            return box

        if kind == "heading":
            if not b["text"]:
                return None
            lvl = b["level"]
            mk = inline_to_markup(b["text"])
            col = MUTED if lvl == 6 else HEAD_TEXT
            lbl = self._label(f"[b]{mk}[/b]", fs * HEADING_SCALE[lvl], col)
            if lvl <= 2:
                box = _VBox(spacing=dp(4))
                box.add_widget(lbl)
                box.add_widget(_Rule(pad=dp(1)))
                return box
            return lbl

        if kind == "hr":
            return _Rule(pad=dp(8))

        if kind == "code":
            return _CodeBlock(self, b["lang"], b["text"])

        if kind == "quote":
            q = _Quote()
            for sub in b["blocks"]:
                w = self._build(sub, depth, True)
                if w is not None:
                    q.add_widget(w)
            return q

        if kind == "list":
            box, gen = self._list_box(b, depth, muted)
            for _ in gen:
                pass
            return box

        if kind == "table":
            tbl = _Table(self, b)
            for _ in tbl.build_rows():
                pass
            return tbl

        if kind == "image":
            return self._build_image(b)

        return None

    def _list_box(self, b, depth, muted):
        """-> (box, generator). The generator adds one item per step."""
        box = _VBox(spacing=dp(4))
        return box, self._list_items(box, b, depth, muted)

    def _list_items(self, box, b, depth, muted):
        fs = self.fs
        num = b["start"]
        kind = "dot" if depth % 2 == 0 else "dash"
        mw = dp(30)

        for item in b["items"]:
            row = BoxLayout(size_hint_y=None, spacing=dp(4))
            row.bind(minimum_height=row.setter("height"))

            if item["task"] is not None:
                px = max(dp(13), fs * 0.95)
                holder = AnchorLayout(anchor_x="right", anchor_y="top",
                                      size_hint=(None, 1), width=dp(24),
                                      padding=(0, dp(3), dp(2), 0))
                holder.add_widget(_Check(item["task"], px))
                row.add_widget(holder)
            elif b["ordered"]:
                m = Label(text=f"{num}.", color=MUTED, font_size=fs,
                          size_hint=(None, 1), width=mw,
                          halign="right", valign="top")
                m.bind(size=lambda i, s: setattr(
                    i, "text_size", (s[0] - dp(4), s[1])))
                row.add_widget(m)
                self._made += 1
            else:
                row.add_widget(_Bullet(kind, fs))
            num += 1

            content = _VBox(spacing=dp(4))
            for sub in item["blocks"]:
                w = self._build(sub, depth + 1, muted)
                if w is not None:
                    content.add_widget(w)
            row.add_widget(content)
            box.add_widget(_rel(row))
            yield

    def _build_image(self, b):
        url, alt = b["url"], b["alt"] or "image"
        low = url.lower()
        if not low.startswith(("http://", "https://")):
            path = url
            if not os.path.isabs(path) and self.base_dir:
                path = os.path.join(self.base_dir, path)
            path = os.path.expanduser(path)
            if os.path.isfile(path):
                wrap = BoxLayout(size_hint_y=None, height=dp(60))
                img = Image(source=path, size_hint=(None, None),
                            size=(dp(60), dp(60)), nocache=True)

                def _size(*a):
                    tw, th = img.texture_size
                    if tw <= 0 or th <= 0 or wrap.width <= 1:
                        return
                    w = min(float(tw), wrap.width)
                    h = w * th / tw
                    if h > dp(480):
                        h = dp(480)
                        w = h * tw / th
                    img.size = (w, h)
                    wrap.height = h
                wrap.bind(width=_size)
                img.bind(texture_size=_size)
                wrap.add_widget(img)
                return wrap
            return self._label(
                f"[i][color={MUTED_COLOR}]&bl;image not found: "
                f"{kivy_escape(url)}&br;[/color][/i]", self.fs, TEXT)
        ok = safe_url(url)
        link = (f"[ref={ok}][color={LINK_COLOR}][u]image: "
                f"{kivy_escape(alt)}[/u][/color][/ref]") if ok else \
            kivy_escape(alt)
        return self._label(link, self.fs, TEXT)
