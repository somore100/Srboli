# screens/disk_space_screen.py - Disk Space: where did the space go?
# Pick a folder (or a whole drive), scan it once, then look at three tabs:
# Folders (tap one to go inside, "Up" to come back), Largest files, and By kind.
# Read-only: it never deletes anything. Logic: core/disk_usage_core.py.

import os
import threading

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core import disk_usage_core as core
from core import theme
from core.file_inspect_core import human_size
from screens.scaffold import ToolScreen

TABS = [("folders", "Folders"), ("files", "Largest files"), ("types", "By kind")]
ON = (0.2, 0.45, 0.75, 1)
OFF = (0.25, 0.25, 0.25, 1)
GREEN = (0.2, 0.55, 0.2, 1)
MONO = "RobotoMono-Regular"


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(6))


class DiskSpaceScreen(ToolScreen):
    title = "Disk Space"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tab = "folders"
        self.result = None
        self.expanded = set()          # paths of the folders opened in the tree
        self._cancel = False
        self._busy = False
        root = self.body

        r = _row()
        self.path_in = TextInput(multiline=False, font_size=sp(12),
                                 hint_text="folder or drive to look at")
        self.path_in.bind(on_text_validate=lambda *a: self.start(self.path_in.text))
        r.add_widget(self.path_in)
        pick = Button(text="Choose...", size_hint_x=None, width=dp(96), font_size=sp(12))
        pick.bind(on_release=lambda *a: self.choose())
        r.add_widget(pick)
        self.scan_btn = Button(text="Scan", size_hint_x=None, width=dp(76),
                               font_size=sp(12), background_color=GREEN)
        self.scan_btn.bind(on_release=lambda *a: self._scan_or_stop())
        r.add_widget(self.scan_btn)
        root.add_widget(r)

        self.summary = Label(text="", font_size=sp(12), size_hint_y=None, height=dp(40),
                             halign="left", valign="middle")
        self.summary.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.summary)

        tabs = _row(38)
        self.tab_btns = {}
        for key, label in TABS:
            b = Button(text=label, font_size=sp(12), background_normal="",
                       background_color=OFF)
            b.bind(on_release=lambda i, k=key: self.show_tab(k))
            self.tab_btns[key] = b
            tabs.add_widget(b)
        root.add_widget(tabs)

        self.nav = _row(36)
        for text, fn in (("Open the big ones", lambda: self.open_big()),
                         ("Open all", lambda: self.open_all()),
                         ("Close all", lambda: self.close_all())):
            b = Button(text=text, font_size=sp(11))
            b.bind(on_release=lambda i, f=fn: f())
            self.nav.add_widget(b)
        root.add_widget(self.nav)

        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(2))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        sv = ScrollView(do_scroll_x=False)
        sv.add_widget(self.list_box)
        root.add_widget(sv)

        self.status = Label(text="Choose a folder and press Scan. Nothing is deleted or changed.",
                            font_size=sp(11), color=theme.MUTED, size_hint_y=None,
                            height=dp(34), halign="left", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.status)

        r = _row(40)
        cp = Button(text="Copy report", font_size=sp(12))
        cp.bind(on_release=lambda *a: self.copy())
        r.add_widget(cp)
        root.add_widget(r)
        self.show_tab("folders")

    # ── choosing and scanning ───────────────────────────────────────────
    def choose(self):
        start = self.path_in.text if os.path.isdir(self.path_in.text) else os.path.expanduser("~")
        try:
            from core.android_storage import shared_storage_root
            if not os.path.isdir(self.path_in.text):
                start = shared_storage_root() or start
        except Exception:
            pass
        chooser = FileChooserIconView(path=start, dirselect=True)
        use = Button(text="Scan this folder", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Choose a folder", content=lay, size_hint=(0.92, 0.92))

        def _use(*a):
            folder = chooser.selection[0] if chooser.selection else chooser.path
            if os.path.isfile(folder):
                folder = os.path.dirname(folder)
            pop.dismiss()
            self.start(folder)

        use.bind(on_release=_use)
        pop.open()

    def _scan_or_stop(self):
        if self._busy:
            self._cancel = True
            self.status.text = "Stopping..."
        else:
            self.start(self.path_in.text)

    def start(self, folder):
        if self._busy:
            return
        folder = os.path.expanduser(folder.strip().strip('"'))
        if not os.path.isdir(folder):
            self.status.text = "That isn't a folder."
            return
        self.path_in.text = folder
        self._busy, self._cancel = True, False
        self.scan_btn.text = "Stop"
        self.scan_btn.background_color = (0.7, 0.3, 0.3, 1)
        self.result = None
        self.expanded = set()
        self.summary.text = "Scanning..."
        self.show_tab(self.tab)

        def progress(files, size):
            Clock.schedule_once(lambda dt: setattr(
                self.status, "text", f"Counted {files:,} files so far, {human_size(size)}..."))

        def run():
            res = err = None
            try:
                res = core.scan(folder, progress=progress,
                                cancelled=lambda: self._cancel)
            except Exception as e:                   # never crash the app
                err = str(e) or "The scan failed."
            Clock.schedule_once(lambda dt: self._done(res, err))

        threading.Thread(target=run, daemon=True).start()

    def _done(self, res, err):
        self._busy = False
        self.scan_btn.text = "Scan"
        self.scan_btn.background_color = GREEN
        if err:
            self.summary.text = ""
            self.status.text = err
            return
        self.result = res
        self.expanded = core.big_paths(res.root)
        r = res
        disk = (f"   Disk: {human_size(r.free)} free of {human_size(r.disk_total)}"
                if r.free is not None else "")
        self.summary.text = f"{human_size(r.total)} in {r.files:,} files{disk}"
        notes = []
        if r.stopped == "cancelled":
            notes.append("Stopped early, so these numbers are partial.")
        elif r.stopped == "limit":
            notes.append("Too many files; the numbers are partial.")
        if r.errors:
            notes.append(f"{r.errors} item(s) couldn't be read.")
        self.status.text = " ".join(notes) or "Done. Tap a folder to open or close it."
        self.show_tab(self.tab)

    # ── tabs ────────────────────────────────────────────────────────────
    def show_tab(self, key):
        self.tab = key
        for k, b in self.tab_btns.items():
            b.background_color = ON if k == key else OFF
        show_nav = key == "folders"
        self.nav.opacity = 1 if show_nav else 0
        self.nav.disabled = not show_nav
        self.nav.size_hint_y = None
        self.nav.height = dp(36) if show_nav else 0
        self.list_box.clear_widgets()
        if not self.result:
            return
        {"folders": self._show_folders, "files": self._show_files,
         "types": self._show_types}[key]()

    def _line(self, text, on_tap=None, h=34):
        b = Button(text=text, font_size=sp(11), font_name=MONO, halign="left",
                   valign="middle", size_hint_y=None, height=dp(h),
                   background_normal="", background_color=(0.16, 0.16, 0.16, 1)
                   if on_tap else (0.12, 0.12, 0.12, 1), shorten=True, shorten_from="right")
        b.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(10), v[1])))
        if on_tap:
            b.bind(on_release=lambda *a: on_tap())
        else:
            b.disabled_color = b.color
            b.disabled = True
        self.list_box.add_widget(b)

    def _show_folders(self):
        lines = core.flatten(self.result.root, self.expanded)
        if not lines:
            self._line("(empty)")
        for depth, label, size, share, node, kind in lines:
            if node is not None and node.children:
                mark = "[-]" if node.path in self.expanded else "[+]"
            else:
                mark = "   "
            text = (f"{'  ' * min(depth, 8)}{mark} {human_size(size):>9} "
                    f"{share * 100:3.0f}% {core.bar(share, 6)} {label}")
            self._line(text, (lambda n=node: self.toggle(n))
                       if node is not None and node.children else None)

    def toggle(self, node):
        if node.path in self.expanded:
            self.expanded.discard(node.path)
        else:
            self.expanded.add(node.path)
        self.show_tab("folders")

    def open_big(self):
        if self.result:
            self.expanded = core.big_paths(self.result.root)
            self.show_tab("folders")

    def open_all(self):
        if not self.result:
            return
        stack, found = [self.result.root], set()
        while stack:
            n = stack.pop()
            if n.children:
                found.add(n.path)
                stack.extend(n.children)
        self.expanded = found
        self.show_tab("folders")

    def close_all(self):
        self.expanded = set()
        self.show_tab("folders")

    def _show_files(self):
        if not self.result.largest:
            self._line("(no files)")
        base = self.result.root.path
        for size, path in self.result.largest:
            rel = os.path.relpath(path, base)
            self._line(f"{human_size(size):>10}  {rel}",
                       lambda p=path: self._say_path(p))

    def _say_path(self, path):
        self.status.text = path
        Clipboard.copy(path)
        self.status.text = path + "   (path copied)"

    def _show_types(self):
        for kind, size, count, share in core.type_rows(self.result):
            self._line(f"{human_size(size):>10} {share * 100:4.0f}% {core.bar(share, 8)} "
                       f"{kind} ({count:,} files)")

    def copy(self):
        if self.result:
            Clipboard.copy(core.report(self.result))
            self.status.text = "Report copied."
