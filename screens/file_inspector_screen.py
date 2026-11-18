# screens/file_inspector_screen.py - File Inspector.
# Choose (or paste the path of) a file; three tabs: Info (real type from the
# contents, size, dates, permissions), Checksums (MD5/SHA-1/SHA-256/SHA-512 and
# "does it match the one I was given?") and Preview (text or hex). Read-only:
# nothing here changes a file. Logic is in core/file_inspect_core.py.

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
from kivy.uix.progressbar import ProgressBar
from kivy.uix.textinput import TextInput

from core import file_inspect_core as core
from core import theme
from screens.scaffold import ToolScreen

TABS = [("info", "Info"), ("hash", "Checksums"), ("preview", "Preview")]
ON = (0.2, 0.45, 0.75, 1)
OFF = (0.25, 0.25, 0.25, 1)
GREEN = (0.2, 0.55, 0.2, 1)


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(6))


class FileInspectorScreen(ToolScreen):
    title = "File Inspector"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tab = "info"
        self.path = ""
        self.info = None
        self.digests = {}
        self._cancel = False
        self._busy = False
        self.mode = "text"
        root = self.body

        r = _row()
        self.path_in = TextInput(multiline=False, font_size=sp(12),
                                 hint_text="path of a file or folder (or press Choose)")
        self.path_in.bind(on_text_validate=lambda *a: self.inspect(self.path_in.text))
        r.add_widget(self.path_in)
        pick = Button(text="Choose...", size_hint_x=None, width=dp(100), font_size=sp(12))
        pick.bind(on_release=lambda *a: self.choose())
        r.add_widget(pick)
        go = Button(text="Inspect", size_hint_x=None, width=dp(84), font_size=sp(12),
                    background_color=GREEN)
        go.bind(on_release=lambda *a: self.inspect(self.path_in.text))
        r.add_widget(go)
        root.add_widget(r)

        tabs = _row(38)
        self.tab_btns = {}
        for key, label in TABS:
            b = Button(text=label, font_size=sp(12), background_normal="",
                       background_color=OFF)
            b.bind(on_release=lambda i, k=key: self.show_tab(k))
            self.tab_btns[key] = b
            tabs.add_widget(b)
        root.add_widget(tabs)

        # per-tab option rows
        self.hash_row = _row(40)
        self.calc_btn = Button(text="Calculate", font_size=sp(12), background_color=GREEN)
        self.calc_btn.bind(on_release=lambda *a: self.calculate())
        self.stop_btn = Button(text="Stop", font_size=sp(12), disabled=True,
                               size_hint_x=None, width=dp(80))
        self.stop_btn.bind(on_release=lambda *a: setattr(self, "_cancel", True))
        self.hash_row.add_widget(self.calc_btn)
        self.hash_row.add_widget(self.stop_btn)
        self.verify_row = _row(40)
        self.expected = TextInput(multiline=False, font_size=sp(12),
                                  hint_text="paste the checksum you were given")
        self.expected.bind(text=lambda *a: self._auto_verify())
        self.verify_row.add_widget(self.expected)
        self.bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(8))

        self.prev_row = _row(40)
        for text, mode in (("Text", "text"), ("Hex", "hex")):
            b = Button(text=text, font_size=sp(12))
            b.bind(on_release=lambda i, m=mode: self.set_mode(m))
            self.prev_row.add_widget(b)

        self.opt_holder = BoxLayout(orientation="vertical", size_hint_y=None,
                                    height=0, spacing=dp(4))
        root.add_widget(self.opt_holder)

        self.output = TextInput(readonly=True, font_size=sp(12),
                                hint_text="Choose a file to inspect it",
                                font_name="RobotoMono-Regular")
        root.add_widget(self.output)

        self.status = Label(text="", font_size=sp(11), color=theme.MUTED,
                            size_hint_y=None, height=dp(34), halign="left",
                            valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.status)

        r = _row(40)
        cp = Button(text="Copy", font_size=sp(12))
        cp.bind(on_release=lambda *a: self.copy())
        r.add_widget(cp)
        root.add_widget(r)
        self.show_tab("info")

    # ── choosing ────────────────────────────────────────────────────────
    def choose(self):
        start = os.path.dirname(self.path) if self.path else os.path.expanduser("~")
        try:
            from core.android_storage import shared_storage_root
            if not self.path:
                start = shared_storage_root() or start
        except Exception:
            pass
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        chooser = FileChooserIconView(path=start, dirselect=True)
        use = Button(text="Inspect this", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Choose a file or folder", content=lay, size_hint=(0.92, 0.92))

        def _use(*a):
            if not chooser.selection:
                return
            pop.dismiss()
            self.inspect(chooser.selection[0])

        use.bind(on_release=_use)
        pop.open()

    def inspect(self, path):
        self._cancel = True               # stop a running checksum of the old file
        self.digests = {}
        self.expected.text = ""
        self.bar.value = 0
        try:
            self.info = core.inspect(path)
        except core.InspectError as e:
            self.info, self.path = None, ""
            self.output.text = ""
            self.status.text = str(e)
            return
        self.path = self.info["path"]
        self.path_in.text = self.path
        self.status.text = ""
        self.show_tab(self.tab)

    # ── tabs ────────────────────────────────────────────────────────────
    def show_tab(self, key):
        self.tab = key
        for k, b in self.tab_btns.items():
            b.background_color = ON if k == key else OFF
        holder = self.opt_holder
        holder.clear_widgets()
        rows = {"info": [], "hash": [self.hash_row, self.bar, self.verify_row],
                "preview": [self.prev_row]}[key]
        for r in rows:
            holder.add_widget(r)
        holder.height = sum(r.height for r in rows) + dp(4) * max(0, len(rows) - 1)
        if not self.info:
            self.output.text = ""
            return
        if key == "info":
            self.output.text = core.report(self.info)
        elif key == "hash":
            self.output.text = (core.hash_report(self.digests) if self.digests else
                                "Press Calculate. Big files take a while.")
            self._auto_verify()
        else:
            self._preview()

    def set_mode(self, mode):
        self.mode = mode
        if self.tab == "preview":
            self._preview()

    def _preview(self):
        if not self.info or self.info.get("kind") != "File":
            self.output.text = "Previews are for files."
            return
        try:
            self.output.text = (core.text_preview(self.path) if self.mode == "text"
                                else core.hex_dump(self.path))
            self.status.text = ("Showing the start of the file."
                                if self.mode == "text" else
                                f"Showing the first {core.HEX_BYTES} bytes.")
        except core.InspectError as e:
            self.output.text = ""
            self.status.text = str(e)

    # ── checksums ───────────────────────────────────────────────────────
    def calculate(self):
        if self._busy:
            return
        if not self.info or self.info.get("kind") != "File":
            self.status.text = "Checksums are for files. Choose a file first."
            return
        self._busy, self._cancel = True, False
        path = self.path
        self.calc_btn.disabled, self.stop_btn.disabled = True, False
        self.status.text = "Calculating..."
        self.bar.value = 0

        def progress(done, total):
            pct = 100.0 * done / total if total else 100
            Clock.schedule_once(lambda dt: setattr(self.bar, "value", pct))

        def run():
            result = err = None
            try:
                result = core.hash_file(path, progress=progress,
                                        cancelled=lambda: self._cancel)
            except core.InspectError as e:
                err = str(e)
            Clock.schedule_once(lambda dt: self._hash_done(path, result, err))

        threading.Thread(target=run, daemon=True).start()

    def _hash_done(self, path, result, err):
        self._busy = False
        self.calc_btn.disabled, self.stop_btn.disabled = False, True
        if path != self.path:             # another file was chosen meanwhile
            return
        if err:
            self.status.text = err
        elif result is None:
            self.status.text = "Stopped."
        else:
            self.digests = result
            self.bar.value = 100
            self.status.text = "Done."
            if self.tab == "hash":
                self.output.text = core.hash_report(result)
            self._auto_verify()

    def _auto_verify(self):
        if self.tab != "hash" or not self.expected.text.strip() or not self.digests:
            return
        try:
            ok, msg = core.verify(self.expected.text, self.digests)
        except core.InspectError as e:
            self.status.text = str(e)
            return
        self.status.text = msg
        self.status.color = (0.5, 0.9, 0.5, 1) if ok else (1, 0.45, 0.45, 1)

    def copy(self):
        if self.output.text:
            Clipboard.copy(self.output.text)
            self.status.text = "Copied."
            self.status.color = theme.MUTED
