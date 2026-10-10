# core/pathbar.py
# Adds a "type / paste a path" bar + quick-jump buttons to EVERY
# FileChooserIconView in the app, without touching the ~30 call sites.
#
# install() swaps `kivy.uix.filechooser.FileChooserIconView` for a subclass
# BEFORE any screen module does `from kivy.uix.filechooser import
# FileChooserIconView`. When the chooser is put into a vertical BoxLayout
# (every picker in the app does this), the subclass inserts the bar above
# itself. Callers still use .path / .selection / on_submit exactly as before.
#
# The bar also shows WHY a list is empty ("Can't read this folder" vs
# "Empty folder"), which a bare FileChooser never says.

import os

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core.android_storage import shared_storage_root

_installed = False


def _fs_root(path):
    """'/' on Linux/mac/Android, the drive root (C:\\) on Windows."""
    if os.name == "nt":
        drive = os.path.splitdrive(os.path.abspath(path or "."))[0]
        return (drive or "C:") + "\\"
    return "/"


def _clean(text):
    t = (text or "").strip().strip("\"'")
    if not t:
        return ""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(t)))


def folder_state(path):
    """('ok'|'empty'|'denied'|'missing', None) without listing the folder."""
    if not os.path.isdir(path):
        return "missing"
    if not os.access(path, os.R_OK | os.X_OK):
        return "denied"
    try:
        with os.scandir(path) as it:
            for _ in it:
                return "ok"
        return "empty"
    except PermissionError:
        return "denied"
    except OSError:
        return "denied"


class PathBar(BoxLayout):
    def __init__(self, chooser, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(40) + dp(34) + dp(18), **kw)
        self._chooser = chooser

        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self._input = TextInput(
            multiline=False, write_tab=False, font_size=13,
            hint_text="Type or paste a folder path",
            foreground_color=(1, 1, 1, 1), hint_text_color=(0.6, 0.6, 0.6, 1),
            background_color=(0.12, 0.12, 0.12, 1),
            cursor_color=(0.4, 0.75, 1, 1), padding=(dp(8), dp(10)))
        self._input.bind(on_text_validate=lambda *a: self._go())
        go = Button(text="Go", size_hint_x=None, width=dp(56), font_size=13)
        go.bind(on_release=lambda *a: self._go())
        paste = Button(text="Paste", size_hint_x=None, width=dp(64),
                       font_size=13)
        paste.bind(on_release=lambda *a: self._paste())
        row.add_widget(self._input)
        row.add_widget(paste)
        row.add_widget(go)
        self.add_widget(row)

        self._chips = BoxLayout(size_hint_y=None, height=dp(34),
                                spacing=dp(4))
        self.add_widget(self._chips)

        self._status = Label(text="", font_size=11, size_hint_y=None,
                             height=dp(18), halign="left", valign="middle",
                             color=(1, 0.6, 0.4, 1))
        self._status.bind(size=lambda i, s: setattr(i, "text_size", s))
        self.add_widget(self._status)

        self._build_chips()
        chooser.bind(path=self._sync)
        self._sync()

    # chips -------------------------------------------------------------
    def _build_chips(self):
        home = shared_storage_root()
        from core.android_storage import ON_ANDROID
        if ON_ANDROID:
            # "Phone" = internal storage, "Storage" lists it plus SD card /
            # USB drives (switch between them here), "Root" = /.
            targets = [("Phone", home), ("Storage", "/storage"),
                       ("Root", "/")]
        else:
            targets = [("Home", home), ("Root", _fs_root(home))]
        for name in ("DCIM", "Download", "Pictures", "Movies", "Music"):
            p = os.path.join(home, name)
            if os.path.isdir(p):
                targets.append((name, p))
        for label, p in targets[:6]:
            b = Button(text=label, font_size=12, background_color=(
                0.25, 0.25, 0.25, 1))
            b.bind(on_release=lambda inst, pp=p: self._open(pp))
            self._chips.add_widget(b)

    # behaviour ---------------------------------------------------------
    def _open(self, path):
        self._input.text = path
        self._go()

    def _paste(self):
        try:
            from kivy.core.clipboard import Clipboard
            txt = Clipboard.paste()
        except Exception:
            txt = ""
        if txt:
            self._input.text = txt.strip().splitlines()[0]
            self._go()
        else:
            self._status.text = "Clipboard is empty"

    def _go(self):
        p = _clean(self._input.text)
        if not p:
            return
        if os.path.isfile(p):
            folder = os.path.dirname(p)
            self._chooser.path = folder
            Clock.schedule_once(
                lambda dt: setattr(self._chooser, "selection", [p]), 0.2)
            return
        state = folder_state(p)
        if state == "missing":
            self._status.text = "Not found: " + p
            return
        if state == "denied":
            self._status.text = ("No permission to read this folder"
                                 " (Android: allow 'all files access')")
            return
        self._chooser.path = p

    def _sync(self, *a):
        p = self._chooser.path
        if not self._input.focus:
            self._input.text = p
        state = folder_state(p)
        self._status.text = {
            "ok": "", "empty": "Empty folder",
            "denied": "Can't read this folder (no permission?)",
            "missing": "Folder not found"}.get(state, "")


def install():
    """Replace kivy's FileChooserIconView with the path-bar subclass.
    Safe to call twice. Call before screens are imported."""
    global _installed
    if _installed:
        return
    import kivy.uix.filechooser as fc
    _Orig = fc.FileChooserIconView

    class FileChooserIconView(_Orig):
        def on_parent(self, inst, parent):
            if (parent is None or getattr(self, "_pathbar_done", False)
                    or not isinstance(parent, BoxLayout)
                    or parent.orientation != "vertical"):
                return
            self._pathbar_done = True

            # Deferred: Widget.add_widget sets .parent BEFORE it inserts the
            # child, so adding the bar right here would land it in the wrong
            # slot. One frame later the layout is stable.
            def _add(dt):
                try:
                    if self.parent is parent:
                        bar = PathBar(self)
                        parent.add_widget(bar, index=len(parent.children))
                except Exception as exc:
                    print(f"pathbar skipped: {exc}")
            Clock.schedule_once(_add, 0)

    fc.FileChooserIconView = FileChooserIconView
    _installed = True
