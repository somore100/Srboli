# screens/md_editor.py - a Markdown text box with a formatting bar.
#
# Used by the Full Editor for each outline node's body. Same idea as the Text
# Editor's bar: tap B and `**|**` is inserted with the cursor between the
# markers (or the selection is wrapped); colours come from swatches or the
# colour wheel, so nobody has to type a hex code. "Preview" swaps the text
# box for the rendered Markdown (screens/md_view.py).

import os

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

try:
    from screens.md_view import MarkdownView
except Exception as _e:                                    # pragma: no cover
    print(f"md_editor: preview unavailable: {_e}")
    MarkdownView = None

# The quick-colour strip starts with these; every colour picked on the wheel
# moves to the front, so the strip becomes "your recent colours". Shared by all
# editors for the session.
RECENT_COLORS = ["#FF4D4D", "#FF9F43", "#FFD93D", "#3DDC84",
                 "#3DE0FF", "#4D94FF", "#B07CFF", "#FF7EB6"]
RECENT_MAX = len(RECENT_COLORS)
_recent_listeners = []


def on_recent_change(cb):
    """Call cb() whenever the recent-colours list changes (to repaint swatches)."""
    _recent_listeners.append(cb)


def remember_color(hex_str):
    """Move a colour to the front of the recent-colours strip."""
    hex_str = hex_str.upper()
    if hex_str in RECENT_COLORS:
        RECENT_COLORS.remove(hex_str)
    RECENT_COLORS.insert(0, hex_str)
    del RECENT_COLORS[RECENT_MAX:]
    for cb in _recent_listeners:
        cb()


def open_color_wheel(on_pick):
    """Open the Text Editor's colour wheel popup; on_pick gets '#RRGGBB'."""
    try:
        from screens.text_editor_screen import _color_wheel_popup
    except Exception as e:
        Popup(title="Colours", size_hint=(0.7, 0.3),
              content=Button(text=f"Colour wheel unavailable: {e}")).open()
        return
    _color_wheel_popup(on_pick)

# (label, kind, before, after); "wrap" surrounds the selection, "line" goes at
# the start of the current line, "block" is inserted as is.
ROW1 = [("B", "wrap", "**", "**"), ("I", "wrap", "*", "*"),
        ("S", "wrap", "~~", "~~"), ("Code", "wrap", "`", "`"),
        ("H1", "line", "# ", ""), ("H2", "line", "## ", ""),
        ("H3", "line", "### ", "")]
ROW2 = [("Quote", "line", "> ", ""), ("List", "line", "- ", ""),
        ("1.", "line", "1. ", ""), ("Link", "wrap", "[", "](https://)"),
        ("Line", "block", "\n---\n", "")]


def _home():
    # Android: "~" resolves to "/" (read-only, empty). Start in shared storage.
    try:
        from core.android_storage import shared_storage_root
        return shared_storage_root()
    except Exception:
        return os.path.expanduser("~")


def hex_rgba(h, a=1):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255,
            int(h[4:6], 16) / 255, a)


class ColorStrip(BoxLayout):
    """A Wheel button and the recent-colours swatches in one row.
    on_pick(hex) is called with '#RRGGBB'; wheel picks are remembered."""

    def __init__(self, on_pick, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(36))
        kw.setdefault("spacing", dp(3))
        super().__init__(**kw)
        self._on_pick = on_pick
        wheel = Button(text="Wheel", font_size=12, size_hint_x=None, width=dp(58))
        wheel.bind(on_release=lambda *a: open_color_wheel(self._wheel_picked))
        self.add_widget(wheel)
        self._swatches = []
        for i in range(RECENT_MAX):
            sw = Button(text="", background_normal="", background_down="")
            sw.bind(on_release=lambda inst, k=i: self._on_pick(RECENT_COLORS[k]))
            self._swatches.append(sw)
            self.add_widget(sw)
        self._paint()
        on_recent_change(self._paint)

    def _paint(self):
        for sw, hex_ in zip(self._swatches, RECENT_COLORS):
            sw.background_color = hex_rgba(hex_)

    def _wheel_picked(self, hex_str):
        remember_color(hex_str)
        self._on_pick(hex_str.upper())


class MarkdownEditor(BoxLayout):
    """Text box + formatting bar. `on_edit(text)` fires on every user edit;
    set_text() loads text without firing it."""

    def __init__(self, on_edit=None, **kw):
        super().__init__(orientation="vertical", spacing=dp(3), **kw)
        self._on_edit = on_edit
        self._loading = False
        self._view = None
        self._previewing = False
        self._fmt_buttons = []

        def row():
            return BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(3))

        def fmt(label, kind, a, b):
            btn = Button(text=label, font_size=13, shorten=True,
                         bold=(label == "B"), italic=(label == "I"),
                         strikethrough=(label == "S"))
            btn.bind(on_release=lambda inst: self._apply_fmt(kind, a, b))
            self._fmt_buttons.append(btn)
            return btn

        r1 = row()
        for spec in ROW1:
            r1.add_widget(fmt(*spec))
        self._prev_btn = ToggleButton(text="Preview", font_size=12)
        self._prev_btn.bind(state=lambda i, st: self._set_preview(st == "down"))
        r1.add_widget(self._prev_btn)
        self.add_widget(r1)

        r2 = row()
        for spec in ROW2:
            r2.add_widget(fmt(*spec))
        img = Button(text="Image", font_size=13)
        img.bind(on_release=lambda *a: self._pick_image())
        wheel = Button(text="Wheel", font_size=13)
        wheel.bind(on_release=lambda *a: self._open_wheel())
        for b in (img, wheel):
            self._fmt_buttons.append(b)
            r2.add_widget(b)
        self.add_widget(r2)

        r3 = row()
        self._swatches = []
        for i in range(len(RECENT_COLORS)):
            sw = Button(text="", background_normal="", background_down="")
            sw.bind(on_release=lambda inst, k=i: self._color(RECENT_COLORS[k]))
            self._swatches.append(sw)
            self._fmt_buttons.append(sw)
            r3.add_widget(sw)
        self._paint_swatches()
        on_recent_change(self._paint_swatches)
        self.add_widget(r3)

        self.ed = TextInput(
            multiline=True, font_size=15,
            background_color=(0.10, 0.10, 0.12, 1),
            foreground_color=(0.92, 0.92, 0.88, 1),
            cursor_color=(0.4, 0.8, 1, 1),
        )
        self.ed.bind(text=self._text_changed)
        self.add_widget(self.ed)

    # ── text in / out ─────────────────────────────────────────────────────
    @property
    def text(self):
        return self.ed.text

    def set_text(self, text):
        self._loading = True
        try:
            self.ed.text = text
        finally:
            self._loading = False
        if self._previewing:
            self._refresh_preview()

    def _text_changed(self, inst, val):
        if not self._loading and self._on_edit:
            self._on_edit(val)

    # ── formatting (same behaviour as the Text Editor's bar) ──────────────
    def _place_cursor(self, idx):
        """Put the caret at character index `idx` AFTER the editor has been
        refocused: tapping a bar button steals focus, and the TextInput moves
        the caret to the end when it regains it."""
        ed = self.ed
        ed.focus = True

        def _set(dt=0):
            try:
                ed.cursor = ed.get_cursor_from_index(min(idx, len(ed.text)))
            except Exception:
                pass
        _set()
        Clock.schedule_once(_set, 0)
        Clock.schedule_once(_set, 0.12)

    def _wrap_at_cursor(self, a, b):
        """Insert a+b with the cursor BETWEEN them, wrap the selection, or -
        if the cursor already sits inside the span - hop past the closing
        marker. Works on character indices (ed.cursor's row is the wrapped
        visual line, not the text line)."""
        ed = self.ed
        sel = ed.selection_text
        if sel:
            start = min(ed.selection_from, ed.selection_to)
            ed.delete_selection()
            ed.insert_text(f"{a}{sel}{b}")
            self._place_cursor(start + len(a) + len(sel) + len(b))
            return
        idx = ed.cursor_index()
        t = ed.text
        line_start = t.rfind("\n", 0, idx) + 1
        if b and t[idx:idx + len(b)] == b and t.rfind(a, line_start, idx) != -1:
            self._place_cursor(idx + len(b))
            return
        ed.insert_text(f"{a}{b}")
        self._place_cursor(idx + len(a))

    def _apply_fmt(self, kind, a, b):
        if self._previewing:
            return
        ed = self.ed
        if kind == "wrap":
            self._wrap_at_cursor(a, b)
        elif kind == "line":
            idx = ed.cursor_index()
            start = ed.text.rfind("\n", 0, idx) + 1
            ed.cursor = ed.get_cursor_from_index(start)
            ed.insert_text(a)
            self._place_cursor(idx + len(a))
        else:
            ed.insert_text(a)
            self._place_cursor(ed.cursor_index())

    def _paint_swatches(self):
        for sw, hex_ in zip(self._swatches, RECENT_COLORS):
            sw.background_color = hex_rgba(hex_)

    def _color(self, hex_str):
        if not self._previewing:
            self._wrap_at_cursor(f"[color={hex_str}]", "[/color]")

    def _wheel_picked(self, hex_str):
        """A colour from the wheel: remember it as the newest and apply it."""
        remember_color(hex_str)
        self._color(hex_str.upper())

    def _open_wheel(self):
        open_color_wheel(self._wheel_picked)

    def _pick_image(self):
        chooser = FileChooserIconView(
            path=_home(), filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"])
        btn = Button(text="Insert", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Insert image", content=layout, size_hint=(0.92, 0.92))

        def _do(*a):
            if chooser.selection:
                path = chooser.selection[0]
                name = os.path.splitext(os.path.basename(path))[0]
                self.ed.insert_text(f"\n![{name}]({path})\n")
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    # ── preview ───────────────────────────────────────────────────────────
    def _refresh_preview(self):
        self._view.set_markdown(self.ed.text, width_hint=self.ed.width or self.width)

    def _set_preview(self, on):
        if on == self._previewing:
            return
        if on:
            if MarkdownView is None:
                self._prev_btn.state = "normal"
                return
            if self._view is None:
                self._view = MarkdownView(base_font=15)
            self._previewing = True
            self._refresh_preview()
            idx = self.children.index(self.ed)
            self.remove_widget(self.ed)
            self.add_widget(self._view, index=idx)
        else:
            self._previewing = False
            if self._view is not None and self._view.parent is self:
                idx = self.children.index(self._view)
                self.remove_widget(self._view)
                self.add_widget(self.ed, index=idx)
        for b in self._fmt_buttons:
            b.disabled = self._previewing
