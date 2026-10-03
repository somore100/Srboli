# screens/text_editor_screen.py
# Text editor with: color wheel, autosave, rotation, script mode link,
# and a Raw / Styled view toggle (Markdown-style rendering, like GitHub)
# Draw tab REMOVED (txt can't store drawings)
# Saves internally (app data) AND can export to chosen location

import os
import time
import math

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard

import app_data

try:
    from screens.md_view import MarkdownView
except Exception as _e:          # renderer optional; Raw view still works
    print(f"Styled view unavailable: {_e}")
    MarkdownView = None

AUTOSAVE_INTERVAL = 20
STYLED_REFRESH_DELAY = 0.25     # debounce while typing/zooming


def _home():
    return os.path.expanduser("~")


# ── Colour wheel widget ───────────────────────────────────────────────────────
class ColorWheel(Widget):
    """
    A simple HSV colour wheel drawn on canvas.
    Tap to pick a colour. Calls on_color(r,g,b,a) callback.
    """

    def __init__(self, on_color=None, **kw):
        super().__init__(**kw)
        self._on_color  = on_color
        self._hue       = 0.0
        self._sat       = 1.0
        self._val       = 1.0
        self._alpha     = 1.0
        self._segments  = 60
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *a):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        R = min(self.width, self.height) * 0.44
        seg = self._segments
        with self.canvas:
            for i in range(seg):
                ang_start = i * (360 / seg)
                ang_end   = ang_start + (360 / seg) + 0.5
                # BUG FIX: Kivy's Ellipse angle_start/angle_end use a
                # different convention than the touch-picking math below
                # (Kivy: 0deg = north/up, angle increases CLOCKWISE.
                #  _pick()/atan2: 0deg = east, angle increases CCW).
                # Without correcting for this, the wedge painted under
                # the user's finger did not match the hue _pick() computed
                # for that same screen position - the wheel's displayed
                # colour and the colour actually picked disagreed.
                # Convert this wedge's Kivy-angle midpoint to the
                # equivalent standard (atan2-style) angle before choosing
                # its hue, so the two stay in sync.
                kivy_mid  = ang_start + (360 / seg) / 2
                theta_std = (90 - kivy_mid) % 360
                hue = theta_std / 360
                import colorsys
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                Color(r, g, b, 1)
                Ellipse(pos=(cx-R, cy-R), size=(R*2, R*2),
                        angle_start=ang_start, angle_end=ang_end)
            # white centre gradient (fake saturation)
            from kivy.graphics import Mesh
            # inner white circle
            Color(1, 1, 1, 0.55)
            Ellipse(pos=(cx - R*0.35, cy - R*0.35),
                    size=(R*0.7, R*0.7))
            # pointer
            ang = math.radians(self._hue * 360)
            pr  = R * max(0.1, self._sat)
            px  = cx + pr * math.cos(ang)
            py  = cy + pr * math.sin(ang)
            Color(0, 0, 0, 1)
            Line(circle=(px, py, 7), width=2)
            import colorsys
            r, g, b = colorsys.hsv_to_rgb(self._hue, self._sat, self._val)
            Color(r, g, b, 1)
            Ellipse(pos=(px-5, py-5), size=(10, 10))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._pick(touch.x, touch.y)
        return True

    def on_touch_move(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self._pick(touch.x, touch.y)
        return True

    def _pick(self, tx, ty):
        cx, cy = self.center_x, self.center_y
        R = min(self.width, self.height) * 0.44
        dx, dy = tx - cx, ty - cy
        dist   = math.sqrt(dx*dx + dy*dy)
        if dist > R:
            return
        self._hue = (math.degrees(math.atan2(dy, dx)) % 360) / 360
        self._sat = min(1.0, dist / R)
        self._draw()
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(self._hue, self._sat, self._val)
        if self._on_color:
            self._on_color(r, g, b, self._alpha)

    def set_val_alpha(self, val, alpha):
        self._val   = val
        self._alpha = alpha
        self._draw()
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(self._hue, self._sat, self._val)
        if self._on_color:
            self._on_color(r, g, b, self._alpha)


def _color_wheel_popup(on_pick):
    """Open a popup with a colour wheel + V/A sliders. Calls on_pick(hex_str)."""
    layout = BoxLayout(orientation="vertical", padding=8, spacing=6)

    picked = [1.0, 1.0, 1.0, 1.0]   # mutable r,g,b,a

    preview = Label(text="  ████████  ", size_hint_y=None, height=dp(32),
                    font_size=18)

    def _on_color(r, g, b, a):
        picked[:] = [r, g, b, a]
        preview.color = (r, g, b, a)
        preview.canvas.before.clear()
        with preview.canvas.before:
            Color(r, g, b, 1)
            Rectangle(pos=preview.pos, size=preview.size)

    wheel = ColorWheel(on_color=_on_color, size_hint=(1, 0.55))
    layout.add_widget(wheel)

    # V slider
    v_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
    v_row.add_widget(Label(text="Brightness:", size_hint_x=None,
                           width=dp(82), font_size=12))
    v_sl = Slider(min=0.1, max=1.0, value=1.0)
    v_row.add_widget(v_sl)
    layout.add_widget(v_row)

    a_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
    a_row.add_widget(Label(text="Opacity:", size_hint_x=None,
                           width=dp(82), font_size=12))
    a_sl = Slider(min=0.0, max=1.0, value=1.0)
    a_row.add_widget(a_sl)
    layout.add_widget(a_row)

    def _upd(*a):
        wheel.set_val_alpha(v_sl.value, a_sl.value)

    v_sl.bind(value=_upd)
    a_sl.bind(value=_upd)

    layout.add_widget(preview)

    apply_btn = Button(text="OK Use this colour", size_hint_y=None,
                       height=dp(44), font_size=14,
                       background_color=(0.2, 0.55, 0.2, 1))
    layout.add_widget(apply_btn)

    popup = Popup(title="Pick Colour", content=layout,
                  size_hint=(0.82, 0.82))

    def _apply(*a):
        r, g, b, _ = picked
        hex_str = "#{:02X}{:02X}{:02X}".format(
            int(r*255), int(g*255), int(b*255))
        popup.dismiss()
        on_pick(hex_str)

    apply_btn.bind(on_release=_apply)
    popup.open()


# ── Main screen ───────────────────────────────────────────────────────────────
class TextEditorScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._file        = None
        self._dirty       = False
        self._autosave_ev = None
        self._last_saved  = ""
        self._landscape   = False
        self._styled      = False   # False = Raw view, True = Styled view
        self._md          = None    # MarkdownView, built on first use
        self._md_ev       = None    # debounced refresh event

        root = BoxLayout(orientation="vertical", padding=4, spacing=4)
        self._root = root

        # ── export format selector ────────────────────────────────────────────
        fmt_sel_row = BoxLayout(size_hint_y=None, height=dp(54), spacing=6,
                                padding=(0, 4))
        fmt_sel_row.add_widget(Label(text="Export format:", size_hint_x=None,
                                     width=dp(110), font_size=13))
        from kivy.uix.spinner import Spinner as _FmtSp
        self._export_fmt = _FmtSp(
            text=".txt",
            values=(".txt — raw text, no styling",
                    ".html — coloured text, opens in browser",
                    ".md — Markdown, basic formatting"),
            font_size=12,
        )
        self._export_fmt.bind(text=self._on_fmt_change)
        fmt_sel_row.add_widget(self._export_fmt)
        root.add_widget(fmt_sel_row)

        # format hint label
        self._fmt_hint = Label(
            text="Plain text — colour not preserved. Zoom is just for "
                 "editing, it isn't saved to the file.",
            font_size=11, size_hint_y=None, height=dp(20),
            halign="left", color=(0.6, 0.8, 1, 1),
            shorten=True, shorten_from="right", max_lines=1)
        self._fmt_hint.bind(size=self._fmt_hint.setter("text_size"))
        root.add_widget(self._fmt_hint)


        # ── toolbar ──────────────────────────────────────────────────────────
        # Rows are wider than a phone screen, so they sit in a horizontal
        # ScrollView (swipe sideways) instead of being clipped.
        bar = BoxLayout(size_hint=(None, 1), spacing=4)
        bar.bind(minimum_width=bar.setter("width"))
        for lbl, cb in [("New",    self._new),
                         ("Open",   self._open),
                         ("Save",   self._save_internal),
                         ("Export", self._export),
                         ("Save As",self._save_as)]:
            w = dp(80) if lbl in ("Save As","Export") else dp(62)
            b = Button(text=lbl, font_size=12, size_hint_x=None, width=w)
            b.bind(on_release=cb)
            bar.add_widget(b)
        copy_btn = Button(text="Copy All", font_size=11,
                          size_hint_x=None, width=dp(78))
        copy_btn.bind(on_release=lambda *a: Clipboard.copy(self._ed.text))
        bar.add_widget(copy_btn)

        # Raw / Styled view toggle (like GitHub's Code | Preview)
        self._raw_btn = ToggleButton(text="Raw", group="te_view", state="down",
                                     allow_no_selection=False,
                                     size_hint_x=None, width=dp(54), font_size=12)
        self._sty_btn = ToggleButton(text="Styled", group="te_view",
                                     allow_no_selection=False,
                                     size_hint_x=None, width=dp(64), font_size=12)
        self._sty_btn.bind(state=lambda i, st: self._set_view(st == "down"))
        bar.add_widget(self._raw_btn)
        bar.add_widget(self._sty_btn)
        self._status = Label(text="New file", font_size=10, halign="left",
                             shorten=True, shorten_from="right", max_lines=1,
                             size_hint_x=None, width=dp(140))
        self._status.bind(size=self._status.setter("text_size"))
        bar.add_widget(self._status)
        bar_sv = ScrollView(size_hint_y=None, height=dp(44), do_scroll_x=True,
                            do_scroll_y=False, bar_width=dp(2))
        bar_sv.add_widget(bar)
        root.add_widget(bar_sv)

        # ── format row ───────────────────────────────────────────────────────
        fmt = BoxLayout(size_hint=(None, 1), spacing=5)
        fmt.bind(minimum_width=fmt.setter("width"))

        fmt.add_widget(Label(text="Zoom:", size_hint_x=None,
                             width=dp(42), font_size=12))
        # font_size ints are px in Kivy; main.py scales them by density on
        # Android, so the zoom base has to be scaled the same way.
        from kivy.utils import platform as _plat
        from kivy.metrics import Metrics as _M
        self._base_font_size = 15 * (_M.density if _plat == "android" else 1)
        self._font_sl = Slider(min=50, max=250, value=100,
                               size_hint_x=None, width=dp(100))
        self._font_lbl = Label(text="100%", size_hint_x=None,
                               width=dp(40), font_size=12)
        self._font_sl.bind(value=self._on_zoom)
        fmt.add_widget(self._font_sl)
        fmt.add_widget(self._font_lbl)

        # colour wheel button
        col_btn = Button(text=" Color", size_hint_x=None, width=dp(82),
                         font_size=12)
        col_btn.bind(on_release=lambda *a: _color_wheel_popup(
            self._insert_color_tag))
        self._col_btn = col_btn
        fmt.add_widget(col_btn)

        # autosave
        self._auto_btn = ToggleButton(text="Autosave ON", state="down",
                                      size_hint_x=None, width=dp(108),
                                      font_size=11)
        self._auto_btn.bind(on_release=self._toggle_autosave)
        fmt.add_widget(self._auto_btn)

        # rotate
        rot_btn = Button(text=" Rotate", size_hint_x=None, width=dp(84),
                         font_size=11)
        rot_btn.bind(on_release=self._toggle_rotation)
        fmt.add_widget(rot_btn)

        # script mode link
        script_btn = Button(text="Copy Script Mode", size_hint_x=None,
                            width=dp(116), font_size=11)
        script_btn.bind(on_release=lambda *a: setattr(
            self.manager, "current", "script_mode"))
        fmt.add_widget(script_btn)

        fmt_sv = ScrollView(size_hint_y=None, height=dp(40), do_scroll_x=True,
                            do_scroll_y=False, bar_width=dp(2))
        fmt_sv.add_widget(fmt)
        root.add_widget(fmt_sv)

        # ── formatting bar (Markdown / HTML only) ────────────────────────────
        # Select text, tap a button: the markers are wrapped around it
        # (Raw view shows **bold**; Styled view shows the result).
        self._fmt_buttons = []
        fb = BoxLayout(size_hint=(None, 1), spacing=4)
        fb.bind(minimum_width=fb.setter("width"))
        for label, kind, a, b2 in [
                ("B", "wrap", "**", "**"), ("I", "wrap", "*", "*"),
                ("S", "wrap", "~~", "~~"), ("Code", "wrap", "`", "`"),
                ("H1", "line", "# ", ""), ("H2", "line", "## ", ""),
                ("H3", "line", "### ", ""), ("Quote", "line", "> ", ""),
                ("List", "line", "- ", ""), ("1.", "line", "1. ", ""),
                ("Link", "wrap", "[", "](https://)"),
                ("Image", "wrap", "![", "](image.jpg)"),
                ("Line", "block", "\n---\n", "")]:
            w = dp(40) if len(label) <= 2 else dp(58)
            btn = Button(text=label, size_hint_x=None, width=w, font_size=13,
                         bold=(label == "B"), italic=(label == "I"),
                         strikethrough=(label == "S"))
            btn.bind(on_release=lambda i, k=kind, x=a, y=b2: self._apply_fmt(k, x, y))
            fb.add_widget(btn)
            self._fmt_buttons.append(btn)
        help_btn = Button(text="?", size_hint_x=None, width=dp(40), font_size=14)
        help_btn.bind(on_release=lambda *a: self._show_syntax_help())
        fb.add_widget(help_btn)
        self._fmt_bar_sv = ScrollView(size_hint_y=None, height=dp(40),
                                      do_scroll_x=True, do_scroll_y=False,
                                      bar_width=dp(2))
        self._fmt_bar_sv.add_widget(fb)
        root.add_widget(self._fmt_bar_sv)

        # ── editor ───────────────────────────────────────────────────────────
        self._ed = TextInput(
            text="", multiline=True, font_size=15,
            background_color=(0.10, 0.10, 0.12, 1),
            foreground_color=(0.92, 0.92, 0.88, 1),
            cursor_color=(0.4, 0.8, 1, 1),
        )
        self._ed.bind(text=self._on_change)
        root.add_widget(self._ed)

        back = Button(text="< Back", size_hint_y=None, height=dp(42))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)
        self._update_fmt_ui()


    # ── formatting helpers ───────────────────────────────────────────────────
    def _fmt_key(self):
        return self._export_fmt.text.split(" ")[0]

    def _apply_fmt(self, kind, a, b):
        ed = self._ed
        if self._styled:
            self._popup("Switch to Raw", "Formatting buttons edit the text - "
                        "switch to the Raw view first.")
            return
        sel = ed.selection_text
        if kind == "wrap":
            if sel:
                ed.delete_selection()
                ed.insert_text(f"{a}{sel}{b}")
            else:
                ed.insert_text(f"{a}text{b}")
        elif kind == "line":
            # put the marker at the start of the current line
            col, row = ed.cursor
            lines = ed.text.split("\n")
            if row < len(lines):
                lines[row] = a + lines[row]
                ed.text = "\n".join(lines)
                ed.cursor = (col + len(a), row)
        else:  # block
            ed.insert_text(a)
        ed.focus = True

    def _show_syntax_help(self):
        rows = [("# Heading", "big heading (## and ### smaller)"),
                ("**bold**", "bold"), ("*italic*", "italic"),
                ("~~strike~~", "strikethrough"), ("`code`", "code"),
                ("> quote", "quote"), ("- item", "bullet"),
                ("1. item", "numbered"), ("[text](url)", "link"),
                ("---", "divider line"), ("![alt](image.jpg)", "image")]
        grid = GridLayout(cols=2, size_hint_y=None, spacing=4, padding=6)
        grid.bind(minimum_height=grid.setter("height"))
        for l, r in rows:
            for t in (l, r):
                lb = Label(text=t, size_hint_y=None, height=dp(30),
                           font_size=13, halign="left", valign="middle")
                lb.bind(size=lb.setter("text_size"))
                grid.add_widget(lb)
        sv = ScrollView()
        sv.add_widget(grid)
        Popup(title="Markdown syntax", content=sv, size_hint=(0.92, 0.7)).open()

    def _update_fmt_ui(self):
        """.txt = plain (no formatting, no colour); .md = Markdown buttons;
        .html = Markdown buttons + colour."""
        k = self._fmt_key()
        fmt_on = k in (".md", ".html")
        for b in self._fmt_buttons:
            b.disabled = not fmt_on
        self._fmt_bar_sv.opacity = 1 if fmt_on else 0.35
        if not self._styled:
            self._col_btn.disabled = (k != ".html")

    def _on_fmt_change(self, spinner, text):
        hints = {
            ".txt": "Plain text — colour not preserved. Zoom is just for "
                    "editing, it isn't saved to the file.",
            ".html": "HTML export — colour [color=hex]tags[/color] rendered. "
                     "Zoom is just for editing, it isn't saved to the file.",
            ".md": "Markdown — use the B / I / H1... buttons. No colour. Zoom is just "
                   "for editing, it isn't saved to the file.",
        }
        key = text.split(" ")[0]
        self._fmt_hint.text = hints.get(key, "")
        self._update_fmt_ui()
        # disable colour button for txt/md since they can't store it
        # (colour wheel stays — useful to insert tags for html mode)

    # ── Raw / Styled view ────────────────────────────────────────────────────
    def _on_zoom(self, slider, v):
        self._ed.font_size = int(self._base_font_size * v / 100)
        self._font_lbl.text = f"{int(v)}%"
        if self._styled:
            self._schedule_styled_refresh(keep_scroll=True)

    def _md_status(self, msg):
        self._status.text = msg

    def _base_dir(self):
        return os.path.dirname(self._file) if self._file else None

    def _refresh_styled(self, keep_scroll=False):
        self._md_ev = None
        if self._md is None:
            return
        self._md.set_scale(self._font_sl.value / 100)
        self._md.set_markdown(self._ed.text, base_dir=self._base_dir(),
                              keep_scroll=keep_scroll,
                              width_hint=self._ed.width or self._root.width)

    def _schedule_styled_refresh(self, keep_scroll=False):
        if self._md_ev:
            self._md_ev.cancel()
        self._md_ev = Clock.schedule_once(
            lambda dt: self._refresh_styled(keep_scroll),
            STYLED_REFRESH_DELAY)

    def _restore_status(self):
        name = os.path.basename(self._file) if self._file else "unsaved"
        self._status.text = f"*{name}" if self._dirty else (
            name if self._file else "New file")

    def _set_view(self, styled):
        if styled == self._styled:
            return
        if styled:
            if MarkdownView is None:
                self._raw_btn.state = "down"
                self._popup("Styled view unavailable",
                            "screens/md_view.py failed to load - "
                            "check the console output.")
                return
            if self._md is None:
                self._md = MarkdownView(base_font=self._base_font_size,
                                        on_status=self._md_status)
            self._refresh_styled()
            idx = self._root.children.index(self._ed)
            self._root.remove_widget(self._ed)
            self._root.add_widget(self._md, index=idx)
            self._col_btn.disabled = True       # colour tags are inserted in Raw
            self._styled = True
            self._status.text = "Styled (read-only)"
        else:
            if self._md_ev:
                self._md_ev.cancel()
                self._md_ev = None
            idx = self._root.children.index(self._md)
            self._root.remove_widget(self._md)
            self._root.add_widget(self._ed, index=idx)
            self._col_btn.disabled = (self._fmt_key() != ".html")
            self._styled = False
            self._restore_status()
            Clock.schedule_once(lambda dt: setattr(self._ed, "focus", True), 0)

    # ── colour tag ───────────────────────────────────────────────────────────
    def _insert_color_tag(self, hex_str):
        self._ed.insert_text(f"[color={hex_str}]text[/color]")

    # ── rotation ─────────────────────────────────────────────────────────────
    def _toggle_rotation(self, *a):
        from kivy.core.window import Window
        w, h = Window.size
        Window.size = (h, w)
        self._landscape = not self._landscape

    # ── file ops ─────────────────────────────────────────────────────────────
    def _on_change(self, inst, val):
        self._dirty = True
        name = os.path.basename(self._file) if self._file else "unsaved"
        self._status.text = f"*{name}"
        if self._styled:
            self._schedule_styled_refresh()

    def _new(self, *a):
        if self._dirty:
            self._confirm_discard(self._do_new)
        else:
            self._do_new()

    def _do_new(self):
        self._ed.text = ""; self._file = None
        self._dirty   = False
        self._status.text = "New file"

    def _open(self, *a):
        chooser = FileChooserIconView(path=_home(), multiselect=False)
        btn = Button(text="Open", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser); layout.add_widget(btn)
        popup = Popup(title="Open", content=layout, size_hint=(0.92, 0.92))

        def _do(*a):
            if chooser.selection:
                p = chooser.selection[0]
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        self._ed.text = f.read()
                    self._file = p; self._dirty = False
                    self._status.text = os.path.basename(p)
                except Exception as e:
                    self._popup("Error", str(e))
            popup.dismiss()

        btn.bind(on_release=_do); popup.open()

    def _save_internal(self, *a):
        """Save to app data folder (quick save, no dialog)."""
        saves_dir = app_data.subdir("text_saves")
        name = os.path.basename(self._file) if self._file else "untitled.txt"
        path = os.path.join(saves_dir, name)
        self._write(path)
        self._file = path
        self._status.text = f"Saved internally: {name}"

    def _export(self, *a):
        """Export/save to user-chosen location in selected format."""
        fmt_key = self._export_fmt.text.split(" ")[0]
        if fmt_key == ".html":
            self._export_as_html()
        elif fmt_key == ".md":
            self._export_as_md()
        else:
            self._save_as()

    def _export_as_html(self, *a):
        chooser = FileChooserIconView(path=_home())
        name = os.path.splitext(os.path.basename(self._file or "document"))[0]
        name_in = TextInput(text=f"{name}.html", multiline=False,
                            size_hint_y=None, height=dp(36), font_size=13)
        btn = Button(text="Export HTML", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(chooser); layout.add_widget(name_in)
        layout.add_widget(btn)
        popup = Popup(title="Export as HTML", content=layout,
                      size_hint=(0.92, 0.92))
        def _do(*a):
            path = os.path.join(chooser.path, name_in.text.strip())
            try:
                # Convert [color=hex]text[/color] tags to HTML spans
                import re as _re
                txt = self._ed.text
                html = _re.sub(
                    r"\[color=([#\w]+)\](.+?)\[/color\]",
                    r'<span style="color:\1">\2</span>',
                    txt, flags=_re.DOTALL)
                html = html.replace("\n", "<br>")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{background:#111;color:#eee;font-family:sans-serif;
padding:24px;line-height:1.6}}</style></head>
<body>{html}</body></html>""")
                self._popup("Exported", f"Saved: {path}")
            except Exception as e:
                self._popup("Error", str(e))
            popup.dismiss()
        btn.bind(on_release=_do); popup.open()

    def _export_as_md(self, *a):
        chooser = FileChooserIconView(path=_home())
        name = os.path.splitext(os.path.basename(self._file or "document"))[0]
        name_in = TextInput(text=f"{name}.md", multiline=False,
                            size_hint_y=None, height=dp(36), font_size=13)
        btn = Button(text="Export Markdown", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(chooser); layout.add_widget(name_in)
        layout.add_widget(btn)
        popup = Popup(title="Export as Markdown", content=layout,
                      size_hint=(0.92, 0.92))
        def _do(*a):
            path = os.path.join(chooser.path, name_in.text.strip())
            try:
                import re as _re
                # Strip colour tags for markdown
                txt = _re.sub(r"\[/?color[^\]]*\]", "", self._ed.text)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(txt)
                self._popup("Exported", f"Saved: {path}")
            except Exception as e:
                self._popup("Error", str(e))
            popup.dismiss()
        btn.bind(on_release=_do); popup.open()

    def _save_as(self, *a):
        chooser  = FileChooserIconView(path=_home())
        name_in  = TextInput(
            text=os.path.basename(self._file) if self._file else "document.txt",
            multiline=False, size_hint_y=None, height=dp(36), font_size=13)
        btn = Button(text="Save", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(chooser); layout.add_widget(name_in)
        layout.add_widget(btn)
        popup = Popup(title="Save As", content=layout, size_hint=(0.92, 0.92))

        def _do(*a):
            path = os.path.join(chooser.path, name_in.text.strip())
            self._write(path); self._file = path; popup.dismiss()

        btn.bind(on_release=_do); popup.open()

    def _write(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._ed.text)
            self._dirty = False
            self._status.text = os.path.basename(path)
        except Exception as e:
            self._popup("Save error", str(e))

    def _confirm_discard(self, cb):
        layout = BoxLayout(orientation="vertical", padding=8, spacing=6)
        layout.add_widget(Label(text="Discard unsaved changes?"))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        yes = Button(text="Discard"); no = Button(text="Cancel")
        row.add_widget(yes); row.add_widget(no)
        layout.add_widget(row)
        popup = Popup(title="Unsaved", content=layout, size_hint=(0.62, 0.36))
        yes.bind(on_release=lambda *a: (popup.dismiss(), cb()))
        no.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    # ── autosave ─────────────────────────────────────────────────────────────
    def _toggle_autosave(self, btn):
        if btn.state == "down":
            btn.text = "Autosave ON"
            self._start_autosave()
        else:
            btn.text = "Autosave OFF"
            self._stop_autosave()

    def _start_autosave(self):
        if not self._autosave_ev:
            self._autosave_ev = Clock.schedule_interval(
                self._do_autosave, AUTOSAVE_INTERVAL)

    def _stop_autosave(self):
        if self._autosave_ev:
            self._autosave_ev.cancel()
            self._autosave_ev = None

    def _do_autosave(self, dt):
        txt = self._ed.text
        if not txt or txt == self._last_saved:
            return
        path = os.path.join(app_data.subdir("autosave"), "text_autosave.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
            self._last_saved = txt
            ts = time.strftime("%H:%M:%S")
            name = os.path.basename(self._file) if self._file else "unsaved"
            self._status.text = f"*{name} [auto {ts}]"
        except Exception:
            pass

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def on_enter(self, *a):
        if not self._ed.text:
            p = os.path.join(app_data.subdir("autosave"), "text_autosave.txt")
            if os.path.exists(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        self._ed.text = f.read()
                    self._status.text = "Restored from autosave"
                except Exception:
                    pass
        self._start_autosave()

    def on_leave(self, *a):
        self._stop_autosave()

    def _go_back(self, *a):
        if self._dirty:
            self._confirm_discard(
                lambda: setattr(self.manager, "current", "dashboard"))
        else:
            if self.manager:
                self.manager.current = "dashboard"

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=str(msg)),
              size_hint=(0.72, 0.38)).open()
