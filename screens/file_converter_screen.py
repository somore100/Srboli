# screens/file_converter_screen.py
#
# File Converter UI. The conversions themselves live in core/converter_core.py
# (Kivy-free and unit-tested); this file is only the screen.
#
#   images   : png jpg webp bmp gif tiff ico pdf          (works everywhere)
#   documents: txt md html docx pdf csv tsv json           (works everywhere)
#   audio/video: mp3 wav ogg flac m4a opus, mp4 webm mkv gif ...
#                needs ffmpeg -> desktop only; on Android the screen says so
#
# Batch: add several files (or a whole folder), pick ONE target format, convert.
# Originals are never touched; outputs never overwrite anything.

import os
import json
import threading

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.slider import Slider
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
from kivy.metrics import dp
from kivy.clock import Clock

import app_data
import core.converter_core as cc
from core.android_storage import shared_storage_root


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def _default_out_dir():
    base = shared_storage_root()
    for name in ("Download", "Downloads"):
        p = os.path.join(base, name)
        if os.path.isdir(p):
            return os.path.join(p, "Srboli converted")
    return os.path.join(base, "Srboli converted")


class FileConverterScreen(Screen):

    def __init__(self, **kw):
        super().__init__(**kw)
        self._files = []
        self._out_dir = self._load_out_dir()
        self._running = False
        self._cancel = threading.Event()

        root = BoxLayout(orientation="vertical", padding=dp(6),
                         spacing=dp(5))

        # -- add / clear ---------------------------------------------------
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for text, cb in (("Add files", self._pick_files),
                         ("Add folder", self._pick_folder),
                         ("Clear", self._clear)):
            b = Button(text=text, font_size=13)
            b.bind(on_release=lambda inst, f=cb: f())
            row.add_widget(b)
        root.add_widget(row)

        # -- file list -------------------------------------------------------
        self._count_lbl = Label(text="", font_size=12, size_hint_y=None,
                                height=dp(22), halign="left", valign="middle",
                                color=(0.7, 0.9, 1, 1))
        self._count_lbl.bind(size=self._fit_text)
        root.add_widget(self._count_lbl)
        sv = ScrollView(bar_width=dp(4))
        self._list = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
        self._list.bind(minimum_height=self._list.setter("height"))
        sv.add_widget(self._list)
        root.add_widget(sv)

        # -- target + options -------------------------------------------------
        trow = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        trow.add_widget(Label(text="Convert to:", font_size=13,
                              size_hint_x=None, width=dp(86)))
        self._target = Spinner(text="-", values=(), font_size=14)
        self._target.bind(text=lambda *a: self._on_target())
        trow.add_widget(self._target)
        root.add_widget(trow)

        self._opts = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self._q_lbl = Label(text="Quality 90", font_size=12,
                            size_hint_x=None, width=dp(84))
        self._quality = Slider(min=10, max=100, value=90, step=1)
        self._quality.bind(value=lambda i, v: setattr(
            self._q_lbl, "text", f"Quality {int(v)}"))
        self._maxside = TextInput(
            multiline=False, hint_text="max px", input_filter="int",
            font_size=13, size_hint_x=None, width=dp(80),
            foreground_color=(1, 1, 1, 1), hint_text_color=(.6, .6, .6, 1),
            background_color=(.12, .12, .12, 1), cursor_color=(.4, .75, 1, 1),
            padding=(dp(8), dp(10)))
        for w in (self._q_lbl, self._quality, self._maxside):
            self._opts.add_widget(w)
        root.add_widget(self._opts)

        self._notice = Label(text="", font_size=12, size_hint_y=None,
                             height=0, halign="left", valign="top",
                             color=(1, 0.65, 0.4, 1))
        self._notice.bind(size=self._fit_text)
        root.add_widget(self._notice)

        # -- output folder ----------------------------------------------------
        orow = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self._out_lbl = Label(text="", font_size=11, halign="left",
                              valign="middle", shorten=True,
                              shorten_from="left")
        self._out_lbl.bind(size=self._fit_text)
        ob = Button(text="Output folder", font_size=12, size_hint_x=None,
                    width=dp(112))
        ob.bind(on_release=lambda *a: self._pick_out_dir())
        orow.add_widget(self._out_lbl)
        orow.add_widget(ob)
        root.add_widget(orow)

        # -- convert / cancel + progress ----------------------------------------
        crow = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self._go = Button(text="Convert", font_size=15, disabled=True)
        self._go.bind(on_release=lambda *a: self._start())
        self._stop = Button(text="Cancel", font_size=13, size_hint_x=None,
                            width=dp(86), disabled=True)
        self._stop.bind(on_release=lambda *a: self._cancel.set())
        crow.add_widget(self._go)
        crow.add_widget(self._stop)
        root.add_widget(crow)

        self._bar = ProgressBar(max=100, value=0, size_hint_y=None,
                                height=dp(8))
        root.add_widget(self._bar)
        self._status = Label(text="", font_size=12, size_hint_y=None,
                             height=dp(20), halign="left", valign="middle")
        self._status.bind(size=self._fit_text)
        root.add_widget(self._status)

        rsv = ScrollView(size_hint_y=None, height=dp(110), bar_width=dp(4))
        self._results = Label(text="", font_size=11, size_hint_y=None,
                              halign="left", valign="top",
                              color=(0.85, 0.85, 0.85, 1))
        self._results.bind(
            width=lambda i, w: setattr(i, "text_size", (w, None)),
            texture_size=lambda i, ts: setattr(i, "height", ts[1]))
        rsv.add_widget(self._results)
        root.add_widget(rsv)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(
            self.manager, "current", "dashboard"))
        root.add_widget(back)
        self.add_widget(root)

        self._refresh()

    @staticmethod
    def _fit_text(inst, size):
        inst.text_size = (size[0], size[1] if inst.height else None)

    # ── persistence ───────────────────────────────────────────────────────
    def _settings_path(self):
        return os.path.join(app_data.subdir("converter"), "settings.json")

    def _load_out_dir(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                p = json.load(f).get("out_dir")
            if p:
                return p
        except Exception:
            pass
        return _default_out_dir()

    def _save_out_dir(self):
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump({"out_dir": self._out_dir}, f)
        except OSError:
            pass

    # ── file list ─────────────────────────────────────────────────────────
    def _add_paths(self, paths):
        have = set(self._files)
        added = skipped = 0
        for p in paths:
            if p in have or not os.path.isfile(p):
                continue
            if cc.kind_of(p):
                self._files.append(p)
                have.add(p)
                added += 1
            else:
                skipped += 1
        self._refresh()
        if skipped:
            self._status.text = f"Skipped {skipped} unsupported file(s)."

    def _clear(self):
        if self._running:
            return
        self._files = []
        self._results.text = ""
        self._bar.value = 0
        self._status.text = ""
        self._refresh()

    def _remove(self, path):
        if not self._running and path in self._files:
            self._files.remove(path)
            self._refresh()

    def _common_targets(self):
        sets = [cc.targets_for(p) for p in self._files]
        if not sets:
            return []
        first = sets[0]
        return [t for t in first if all(t in s for s in sets[1:])]

    def _refresh(self):
        self._list.clear_widgets()
        kinds = {}
        for p in self._files:
            k = cc.kind_of(p)
            kinds[k] = kinds.get(k, 0) + 1
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
            try:
                size = _human(os.path.getsize(p))
            except OSError:
                size = "?"
            lbl = Label(text=f"{os.path.basename(p)}   [{size}]",
                        font_size=12, halign="left", valign="middle",
                        shorten=True, shorten_from="right")
            lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
            x = Button(text="X", font_size=12, size_hint_x=None, width=dp(40))
            x.bind(on_release=lambda inst, pp=p: self._remove(pp))
            row.add_widget(lbl)
            row.add_widget(x)
            self._list.add_widget(row)
        if self._files:
            desc = ", ".join(f"{n} {cc.KIND_LABEL[k].lower()}"
                             for k, n in kinds.items())
            self._count_lbl.text = f"{len(self._files)} file(s): {desc}"
        else:
            self._count_lbl.text = ("No files yet. Add files or a folder - "
                                    "images, documents, audio, video.")
        targets = self._common_targets()
        keep = self._target.text if self._target.text in targets else \
            (targets[0] if targets else "-")
        self._target.values = tuple(targets)
        self._target.text = keep
        self._out_lbl.text = "Saves to: " + self._out_dir
        self._on_target()

    def _on_target(self):
        t = self._target.text
        kinds = {cc.kind_of(p) for p in self._files}
        is_img = kinds == {"image"}
        show = is_img and t in ("jpg", "webp", "png", "gif", "tiff", "ico",
                                "bmp", "pdf")
        q_ok = is_img and t in ("jpg", "webp")
        self._opts.height = dp(40) if show else 0
        self._opts.opacity = 1 if show else 0
        self._opts.disabled = not show
        self._q_lbl.opacity = 1 if q_ok else 0.35
        self._quality.disabled = not q_ok
        # why can't we convert?
        msg = ""
        if self._files and t == "-":
            msg = ("These files have no format in common. Clear the list and "
                   "convert one kind at a time (e.g. only images).")
        elif self._files and t != "-":
            for p in self._files:
                why = cc.unavailable_reason(p, t)
                if why:
                    msg = why
                    break
        self._notice.text = msg
        self._notice.height = dp(52) if msg else 0
        self._go.disabled = (self._running or not self._files or t == "-"
                             or bool(msg))

    # ── pickers ───────────────────────────────────────────────────────────
    def _pick_files(self):
        if self._running:
            return
        chooser = FileChooserIconView(
            path=shared_storage_root(), multiselect=True,
            filters=[lambda folder, name: os.path.isdir(
                os.path.join(folder, name)) or bool(cc.kind_of(name))])
        layout = BoxLayout(orientation="vertical", spacing=dp(4))
        layout.add_widget(chooser)
        sel_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        all_b = Button(text="Select all here", font_size=12)
        none_b = Button(text="Select none", font_size=12)
        sel_row.add_widget(all_b)
        sel_row.add_widget(none_b)
        layout.add_widget(sel_row)
        btn = Button(text="Add selected files", size_hint_y=None,
                     height=dp(46))
        layout.add_widget(btn)
        popup = Popup(title="Tap files to select - tap again to unselect",
                      content=layout, size_hint=(0.94, 0.94))

        def count(*a):
            n = len([p for p in chooser.selection if os.path.isfile(p)])
            btn.text = (f"Add {n} selected file{'s' if n != 1 else ''}"
                        if n else "Add selected files")
        chooser.bind(selection=count)

        def select_all(*a):
            try:
                names = sorted(os.listdir(chooser.path))
            except OSError:
                return
            chooser.selection = [
                os.path.join(chooser.path, n) for n in names
                if os.path.isfile(os.path.join(chooser.path, n))
                and cc.kind_of(n)]
        all_b.bind(on_release=select_all)
        none_b.bind(on_release=lambda *a: setattr(chooser, "selection", []))

        def done(*a):
            popup.dismiss()
            self._add_paths([p for p in chooser.selection
                             if os.path.isfile(p)])
        btn.bind(on_release=done)
        popup.open()

    def _pick_folder(self):
        if self._running:
            return
        chooser = FileChooserIconView(path=shared_storage_root(),
                                      dirselect=True)
        layout = BoxLayout(orientation="vertical", spacing=dp(4))
        layout.add_widget(chooser)
        btn = Button(text="Add every supported file in this folder",
                     size_hint_y=None, height=dp(46))
        layout.add_widget(btn)
        popup = Popup(title="Add folder", content=layout,
                      size_hint=(0.94, 0.94))

        def done(*a):
            folder = chooser.selection[0] if chooser.selection else \
                chooser.path
            popup.dismiss()
            try:
                names = sorted(os.listdir(folder))
            except OSError as e:
                self._status.text = f"Can't read that folder: {e}"
                return
            self._add_paths([os.path.join(folder, n) for n in names])
        btn.bind(on_release=done)
        popup.open()

    def _pick_out_dir(self):
        if self._running:
            return
        start = self._out_dir if os.path.isdir(self._out_dir) else \
            shared_storage_root()
        chooser = FileChooserIconView(path=start, dirselect=True)
        layout = BoxLayout(orientation="vertical", spacing=dp(4))
        layout.add_widget(chooser)
        btn = Button(text="Save converted files here", size_hint_y=None,
                     height=dp(46))
        layout.add_widget(btn)
        popup = Popup(title="Output folder", content=layout,
                      size_hint=(0.94, 0.94))

        def done(*a):
            self._out_dir = chooser.selection[0] if chooser.selection else \
                chooser.path
            self._save_out_dir()
            popup.dismiss()
            self._out_lbl.text = "Saves to: " + self._out_dir
        btn.bind(on_release=done)
        popup.open()

    # ── conversion ────────────────────────────────────────────────────────
    def _start(self):
        if self._running or not self._files:
            return
        target = self._target.text
        files = list(self._files)
        opts = {"quality": int(self._quality.value)}
        try:
            opts["max_side"] = int(self._maxside.text) if \
                self._maxside.text.strip() else 0
        except ValueError:
            opts["max_side"] = 0
        out_dir = self._out_dir
        self._running = True
        self._cancel.clear()
        self._go.disabled = True
        self._stop.disabled = False
        self._bar.value = 0
        self._results.text = ""
        self._status.text = "Starting..."
        threading.Thread(target=self._worker,
                         args=(files, target, out_dir, opts),
                         daemon=True).start()

    def _worker(self, files, target, out_dir, opts):
        ok, bad, lines = 0, 0, []
        total = len(files)
        for i, src in enumerate(files):
            if self._cancel.is_set():
                lines.append("Cancelled.")
                break
            name = os.path.basename(src)
            Clock.schedule_once(
                lambda dt, i=i, n=name: self._progress(i, total, n))
            try:
                dst = cc.convert_file(src, out_dir, target, opts,
                                      cancel=self._cancel)
                ok += 1
                lines.append(f"OK    {name}  ->  {os.path.basename(dst)}")
            except cc.ConvertError as e:
                bad += 1
                lines.append(f"FAIL  {name}: {e}")
                if "Cancel" in str(e):
                    break
            except Exception as e:                # never kill the worker
                bad += 1
                lines.append(f"FAIL  {name}: {type(e).__name__}: {e}")
        Clock.schedule_once(
            lambda dt: self._finished(ok, bad, lines, out_dir))

    def _progress(self, i, total, name):
        self._bar.value = 100.0 * i / max(total, 1)
        self._status.text = f"Converting {i + 1}/{total}: {name}"

    def _finished(self, ok, bad, lines, out_dir):
        self._running = False
        self._stop.disabled = True
        self._bar.value = 100 if ok and not bad else self._bar.value
        self._status.text = (f"Done: {ok} converted"
                             + (f", {bad} failed" if bad else "")
                             + (f".  Saved in {out_dir}" if ok else ""))
        self._results.text = "\n".join(lines)
        self._on_target()

    def on_leave(self, *a):
        # leaving mid-conversion lets it finish in the background; nothing to
        # unbind (no Window/Clock handlers are left registered).
        pass
