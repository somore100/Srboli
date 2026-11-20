# screens/folder_colors_screen.py - Folder Colors: coloured folders and folders
# with a picture, shown by your file manager (Linux and Windows).
# Pick a folder, pick a colour or a picture, press Apply. "Reset" brings the
# normal icon back. Only the folder's icon setting changes, never its files.
# Logic: core/folder_icons_core.py.

import os

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput

from core import folder_icons_core as core
from core import theme
from screens.scaffold import ToolScreen

GREEN = (0.2, 0.55, 0.2, 1)
PIC_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def _hex_rgba(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1,)


class FolderColorsScreen(ToolScreen):
    title = "Folder Colors"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.color = core.COLORS[5][1]       # blue
        self.picture = ""
        self.use_picture = False
        self.include_sub = False
        root = self.body

        r = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.path_in = TextInput(multiline=False, font_size=sp(12),
                                 hint_text="folder to colour")
        r.add_widget(self.path_in)
        pick = Button(text="Choose...", size_hint_x=None, width=dp(96), font_size=sp(12))
        pick.bind(on_release=lambda *a: self.choose_folder())
        r.add_widget(pick)
        root.add_widget(r)

        grid = GridLayout(cols=6, size_hint_y=None, height=dp(96), spacing=dp(6))
        for name, hx in core.COLORS:
            b = Button(text=name, font_size=sp(11), background_normal="",
                       background_color=_hex_rgba(hx),
                       color=(0, 0, 0, 1) if name in ("Yellow", "White", "Grey") else (1, 1, 1, 1))
            b.bind(on_release=lambda i, h=hx: self.pick_color(h))
            grid.add_widget(b)
        root.add_widget(grid)

        r = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.hex_in = TextInput(multiline=False, font_size=sp(12), text=self.color,
                                hint_text="#rrggbb", size_hint_x=0.35)
        self.hex_in.bind(on_text_validate=lambda *a: self.pick_color(self.hex_in.text))
        r.add_widget(self.hex_in)
        pic = Button(text="Use a picture...", font_size=sp(12))
        pic.bind(on_release=lambda *a: self.choose_picture())
        r.add_widget(pic)
        self.sub_btn = Button(text="Subfolders: no", font_size=sp(12), size_hint_x=0.4)
        self.sub_btn.bind(on_release=lambda *a: self.toggle_sub())
        r.add_widget(self.sub_btn)
        root.add_widget(r)

        self.preview = Image(size_hint_y=1, fit_mode="contain")
        root.add_widget(self.preview)

        self.status = Label(text="", font_size=sp(11), color=theme.MUTED, size_hint_y=None,
                            height=dp(48), halign="left", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.status)

        r = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        ap = Button(text="Apply", background_color=GREEN, font_size=sp(13))
        ap.bind(on_release=lambda *a: self.apply())
        rs = Button(text="Reset to normal", font_size=sp(13))
        rs.bind(on_release=lambda *a: self.reset())
        r.add_widget(ap)
        r.add_widget(rs)
        root.add_widget(r)

        if not core.supported():
            self.status.text = ("Folder icons work on Linux and Windows. Your system "
                                "can't show custom folder icons from here.")
        else:
            self.status.text = ("Pick a folder and a colour (or a picture), then Apply. "
                                "Only the folder's icon changes; refresh the file manager if it "
                                "does not update at once.")
        self.refresh_preview()

    # ── choices ─────────────────────────────────────────────────────────
    def pick_color(self, hx):
        try:
            core._rgb(hx)
            if len(hx.lstrip("#")) != 6:
                raise ValueError
        except ValueError:
            self.status.text = f"'{hx}' is not a colour like #3e63dd."
            return
        self.color = "#" + hx.lstrip("#").lower()
        self.use_picture = False
        self.hex_in.text = self.color
        self.refresh_preview()

    def toggle_sub(self):
        self.include_sub = not self.include_sub
        self.sub_btn.text = "Subfolders: yes" if self.include_sub else "Subfolders: no"

    def set_picture(self, path):
        if not os.path.isfile(path):
            self.status.text = "That picture isn't there."
            return
        self.picture = path
        self.use_picture = True
        self.refresh_preview()

    def refresh_preview(self):
        try:
            png = core.image_icon(self.picture) if self.use_picture else core.color_icon(self.color)
            self.preview.source = png
            self.preview.reload()
        except Exception as e:
            self.status.text = f"Can't make the preview: {e}"

    def _chooser(self, title, button, dirselect, filters, done):
        start = os.path.expanduser("~")
        chooser = FileChooserIconView(path=start, dirselect=dirselect,
                                      filters=filters)
        use = Button(text=button, size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title=title, content=lay, size_hint=(0.92, 0.92))

        def _use(*a):
            sel = chooser.selection[0] if chooser.selection else chooser.path
            pop.dismiss()
            done(sel)

        use.bind(on_release=_use)
        pop.open()

    def choose_folder(self):
        def done(p):
            self.path_in.text = p if os.path.isdir(p) else os.path.dirname(p)
        self._chooser("Choose a folder", "Use this folder", True, [], done)

    def choose_picture(self):
        self._chooser("Choose a picture", "Use this picture", False,
                      ["*" + e for e in PIC_EXT] + ["*" + e.upper() for e in PIC_EXT],
                      lambda p: self.set_picture(p))

    # ── doing it ────────────────────────────────────────────────────────
    def _folder(self):
        f = self.path_in.text.strip().strip('"')
        if not f or not os.path.isdir(f):
            self.status.text = "Choose a folder first - that path isn't a folder."
            return None
        return f

    def apply(self):
        f = self._folder()
        if not f:
            return
        try:
            png = core.image_icon(self.picture) if self.use_picture else core.color_icon(self.color)
            n = 0
            how = []
            for t in core.targets(f, self.include_sub):
                how = core.apply(t, png)
                n += 1
        except core.IconError as e:
            self.status.text = str(e)
            return
        except Exception as e:
            self.status.text = f"Failed: {e}"
            return
        self.status.text = (f"Done: {n} folder{'s' if n != 1 else ''}. Used: " + ", ".join(how) +
                            ". If you don't see it, refresh the file manager (F5).")

    def reset(self):
        f = self._folder()
        if not f:
            return
        try:
            n = sum(1 for t in core.targets(f, self.include_sub) if core.reset(t))
        except core.IconError as e:
            self.status.text = str(e)
            return
        self.status.text = f"Back to normal: {n} folder{'s' if n != 1 else ''}."
