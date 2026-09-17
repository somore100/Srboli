# screens/text_editor_screen.py
# Text editor with: color wheel, autosave, rotation, script mode link
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

AUTOSAVE_INTERVAL = 20


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

        root = BoxLayout(orientation="vertical", padding=4, spacing=4)

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
            halign="left", color=(0.6, 0.8, 1, 1))
        self._fmt_hint.bind(size=self._fmt_hint.setter("text_size"))
        root.add_widget(self._fmt_hint)


        # ── toolbar ──────────────────────────────────────────────────────────
        bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=4)
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
        self._status = Label(text="New file", font_size=10, halign="left")
        self._status.bind(size=self._status.setter("text_size"))
        bar.add_widget(self._status)
        root.add_widget(bar)

        # ── format row ───────────────────────────────────────────────────────
        fmt = BoxLayout(size_hint_y=None, height=dp(36), spacing=5)

        fmt.add_widget(Label(text="Zoom:", size_hint_x=None,
                             width=dp(42), font_size=12))
        self._base_font_size = 15
        self._font_sl = Slider(min=50, max=250, value=100,
                               size_hint_x=None, width=dp(100))
        self._font_lbl = Label(text="100%", size_hint_x=None,
                               width=dp(40), font_size=12)
        self._font_sl.bind(value=lambda s, v: (
            setattr(self._ed, "font_size", int(self._base_font_size * v / 100)),
            setattr(self._font_lbl, "text", f"{int(v)}%")))
        fmt.add_widget(self._font_sl)
        fmt.add_widget(self._font_lbl)

        # colour wheel button
        col_btn = Button(text=" Color", size_hint_x=None, width=dp(82),
                         font_size=12)
        col_btn.bind(on_release=lambda *a: _color_wheel_popup(
            self._insert_color_tag))
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

        root.add_widget(fmt)

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


    def _on_fmt_change(self, spinner, text):
        hints = {
            ".txt": "Plain text — colour not preserved. Zoom is just for "
                    "editing, it isn't saved to the file.",
            ".html": "HTML export — colour [color=hex]tags[/color] rendered. "
                     "Zoom is just for editing, it isn't saved to the file.",
            ".md": "Markdown — basic formatting, no colour. Zoom is just "
                   "for editing, it isn't saved to the file.",
        }
        key = text.split(" ")[0]
        self._fmt_hint.text = hints.get(key, "")
        # disable colour button for txt/md since they can't store it
        # (colour wheel stays — useful to insert tags for html mode)

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
