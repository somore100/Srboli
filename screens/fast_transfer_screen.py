# screens/fast_transfer_screen.py
#
# Fast (parallel/batched) file transfer.
#
# The problem this solves: copying/moving a folder one file at a time
# means file 2 waits for file 1 to fully finish, even on a source/dest
# pair that could easily sustain several transfers running at once.
# This screen collects the file list up front, then keeps up to N of
# them "in flight" at the same time (a rolling window, not rigid
# discrete batches - as soon as one finishes, the next one starts,
# rather than waiting for a whole group of N to complete first).
#
# The engine (file collection, the parallel copy/move, the "is it finished?"
# check, auto-tune and the scope note about when this helps and when it hurts)
# lives in core/transfer_core.py, Kivy-free and tested. This screen is only
# the buttons.

import os, threading, time

from core.android_storage import shared_storage_root

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.metrics import dp

from core.file_sorter_core import _fmt_size
from core.transfer_core import (
    collect_files_with_relpaths, detect_rotational, recommend_concurrency,
    run_transfer, autotune, clamp_workers,
)

MODES = ["Copy", "Move"]


EXPLAIN_TEXT = (
    "[b]How this is different from a normal copy/move[/b]\n"
    "Copying files one at a time means file 2 waits for file 1 to fully "
    "finish, even though your system can usually handle several transfers "
    "at once. This screen scans the folder first, then keeps a chosen number "
    "of transfers running at the same time.\n\n"
    "[b]Best for:[/b] folders with lots of smaller files - extracted "
    "projects, photo dumps, source trees.\n"
    "[b]Won't help much (sometimes hurts):[/b] a handful of very large "
    "files, or a spinning hard drive, which has to seek between simultaneous "
    "writes. More than about 16 never helps: the disk only serves so many "
    "requests at once.\n\n"
    "[b]Auto-tune[/b] copies a small sample of YOUR files into a temporary "
    "folder on the destination with 1, 2, 4, 8 and 16 workers and picks the "
    "fewest that are about as fast as the best. That is a measurement, not a "
    "guess. Files that are still being written, empty, or open in another "
    "program are left alone (moves are checked before the original is "
    "deleted).\n\n"
    "[i]There's no OS setting for a true 'max simultaneous transfers' number; "
    "the concurrency below is a recommendation you can change.[/i]"
)


class FastTransferScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._source = ""
        self._dest = ""
        self._pairs = None          # last Analyze result
        self._busy = False
        self._stop_requested = False
        self._transferred_bytes = 0
        self._done_count = 0
        self._error_lines = []

        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        root.add_widget(Label(text="[b]Fast File Transfer[/b] (parallel/batched)",
                              markup=True, font_size=18, size_hint_y=None,
                              height=dp(30)))

        explain = Label(text=EXPLAIN_TEXT, markup=True, font_size=11,
                        halign="left", valign="top", size_hint_y=None,
                        color=(0.75, 0.85, 0.95, 1))
        explain.bind(width=lambda *a: setattr(
            explain, "text_size", (explain.width, None)))
        explain.bind(texture_size=lambda *a: setattr(
            explain, "height", explain.texture_size[1] + dp(8)))
        root.add_widget(explain)

        # source / destination
        src_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
        self._src_lbl = Label(text="(no source folder chosen)", font_size=11,
                              halign="left", color=(0.7, 0.9, 0.7, 1))
        self._src_lbl.bind(size=self._src_lbl.setter("text_size"))
        pick_src = Button(text="Pick Source", size_hint_x=None, width=dp(120))
        pick_src.bind(on_release=lambda *a: self._pick_folder("source"))
        src_row.add_widget(pick_src)
        src_row.add_widget(self._src_lbl)
        root.add_widget(src_row)

        dst_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
        self._dst_lbl = Label(text="(no destination folder chosen)", font_size=11,
                              halign="left", color=(0.7, 0.9, 0.7, 1))
        self._dst_lbl.bind(size=self._dst_lbl.setter("text_size"))
        pick_dst = Button(text="Pick Destination", size_hint_x=None, width=dp(120))
        pick_dst.bind(on_release=lambda *a: self._pick_folder("dest"))
        dst_row.add_widget(pick_dst)
        dst_row.add_widget(self._dst_lbl)
        root.add_widget(dst_row)

        # options
        opt_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        opt_row.add_widget(Label(text="Mode:", size_hint_x=None, width=dp(50),
                                 font_size=12))
        self._mode_spinner = Spinner(text="Copy", values=MODES,
                                     size_hint_x=None, width=dp(90))
        self._mode_spinner.bind(text=lambda *a: self._mark_stale())
        opt_row.add_widget(self._mode_spinner)

        self._recursive_cb = CheckBox(active=True, size_hint=(None, None),
                                      size=(dp(24), dp(24)))
        self._recursive_cb.bind(active=lambda *a: self._mark_stale())
        opt_row.add_widget(self._recursive_cb)
        opt_row.add_widget(Label(text="Include subfolders", font_size=12,
                                 size_hint_x=None, width=dp(120)))

        self._overwrite_cb = CheckBox(active=False, size_hint=(None, None),
                                      size=(dp(24), dp(24)))
        opt_row.add_widget(self._overwrite_cb)
        opt_row.add_widget(Label(text="Overwrite existing", font_size=12))
        root.add_widget(opt_row)

        # concurrency
        conc_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        conc_row.add_widget(Label(text="Concurrency:", size_hint_x=None,
                                  width=dp(90), font_size=12))
        self._concurrency_input = TextInput(text="4", multiline=False,
                                            input_filter="int", font_size=12,
                                            size_hint_x=None, width=dp(60))
        conc_row.add_widget(self._concurrency_input)
        self._recommend_lbl = Label(text="Run Analyze to get a recommendation.",
                                    font_size=11, halign="left",
                                    color=(0.8, 0.8, 0.5, 1))
        self._recommend_lbl.bind(size=self._recommend_lbl.setter("text_size"))
        conc_row.add_widget(self._recommend_lbl)
        root.add_widget(conc_row)

        # actions
        act_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self._analyze_btn = Button(text="Analyze")
        self._analyze_btn.bind(on_release=self._run_analyze)
        self._tune_btn = Button(text="Auto-tune", disabled=True)
        self._tune_btn.bind(on_release=self._run_tune)
        self._start_btn = Button(text="Start Transfer", disabled=True)
        self._start_btn.bind(on_release=self._run_transfer)
        self._stop_btn = Button(text="Stop", disabled=True, size_hint_x=None,
                                width=dp(70))
        self._stop_btn.bind(on_release=self._request_stop)
        act_row.add_widget(self._analyze_btn)
        act_row.add_widget(self._tune_btn)
        act_row.add_widget(self._start_btn)
        act_row.add_widget(self._stop_btn)
        root.add_widget(act_row)

        self._status = Label(text="", size_hint_y=None, height=dp(20),
                             font_size=11, color=(0.6, 0.8, 1, 1))
        root.add_widget(self._status)

        log_sv = ScrollView(size_hint_y=0.32)
        self._log_lbl = Label(text="", font_size=10, halign="left",
                              valign="top", size_hint_y=None, markup=False)
        self._log_lbl.bind(texture_size=lambda *a: setattr(
            self._log_lbl, "height", self._log_lbl.texture_size[1]))
        self._log_lbl.bind(width=lambda *a: setattr(
            self._log_lbl, "text_size", (self._log_lbl.width, None)))
        log_sv.add_widget(self._log_lbl)
        root.add_widget(log_sv)

        back = Button(text="< Back", size_hint_y=None, height=dp(40))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    # ── folder picking ──────────────────────────────────────────────────
    def _pick_folder(self, which):
        chooser = FileChooserIconView(path=shared_storage_root(),
                                      dirselect=True)
        popup = Popup(title="Choose a folder", content=BoxLayout(),
                      size_hint=(0.9, 0.9))

        def _use(*a):
            if chooser.selection:
                folder = chooser.selection[0]
                if os.path.isfile(folder):
                    folder = os.path.dirname(folder)
                if which == "source":
                    self._source = folder
                    self._src_lbl.text = folder
                else:
                    self._dest = folder
                    self._dst_lbl.text = folder
                self._mark_stale()
            popup.dismiss()

        btn_row = BoxLayout(size_hint_y=None, height=dp(40))
        use_btn = Button(text="Use this folder")
        use_btn.bind(on_release=_use)
        cancel_btn = Button(text="Cancel")
        cancel_btn.bind(on_release=lambda *a: popup.dismiss())
        btn_row.add_widget(use_btn)
        btn_row.add_widget(cancel_btn)
        wrapper = BoxLayout(orientation="vertical")
        wrapper.add_widget(chooser)
        wrapper.add_widget(btn_row)
        popup.content = wrapper
        popup.open()

    def _mark_stale(self):
        self._pairs = None
        self._start_btn.disabled = True
        self._tune_btn.disabled = True

    # ── analyze ──────────────────────────────────────────────────────────
    def _run_analyze(self, *a):
        if self._busy:
            return
        if not self._source or not self._dest:
            self._status.text = "Pick a source and destination folder first."
            return
        if os.path.abspath(self._source) == os.path.abspath(self._dest):
            self._status.text = "Source and destination can't be the same folder."
            return

        self._busy = True
        self._analyze_btn.disabled = True
        self._start_btn.disabled = True
        self._tune_btn.disabled = True
        self._status.text = "Analyzing..."
        self._log_lbl.text = ""
        recursive = self._recursive_cb.active
        source, dest = self._source, self._dest

        def worker():
            pairs = collect_files_with_relpaths(source, recursive)
            total_size = sum(
                (os.path.getsize(p) for p, _ in pairs if os.path.exists(p)),
                0)
            avg_size = (total_size / len(pairs)) if pairs else 0
            rotational = detect_rotational(dest)
            concurrency, reason = recommend_concurrency(
                len(pairs), avg_size, rotational)
            Clock.schedule_once(lambda dt: self._on_analyze_done(
                pairs, total_size, avg_size, rotational, concurrency, reason))

        threading.Thread(target=worker, daemon=True).start()

    def _on_analyze_done(self, pairs, total_size, avg_size, rotational,
                          concurrency, reason):
        self._busy = False
        self._analyze_btn.disabled = False
        self._pairs = pairs
        self._start_btn.disabled = (len(pairs) == 0)
        self._tune_btn.disabled = (len(pairs) == 0)
        self._concurrency_input.text = str(concurrency)

        disk_note = {True: "spinning hard drive (or reports as one)",
                     False: "SSD/NVMe-like (non-rotational)",
                     None: "couldn't determine"}[rotational]
        self._recommend_lbl.text = (
            f"Recommended: {concurrency} - {reason}")
        self._status.text = (
            f"{len(pairs)} files, {_fmt_size(total_size)} total, "
            f"avg {_fmt_size(avg_size)}/file. Destination: {disk_note}. "
            "Press Auto-tune to measure the best number of workers.")
        self._log_lbl.text = (
            "Analyze complete. Auto-tune (optional), then Start Transfer."
            if pairs else
            "No files found in the source folder.")

    # ── auto-tune ────────────────────────────────────────────────────────
    def _run_tune(self, *a):
        if self._busy or not self._pairs:
            return
        self._busy = True
        self._stop_requested = False
        for b in (self._analyze_btn, self._tune_btn, self._start_btn):
            b.disabled = True
        self._stop_btn.disabled = False
        self._log_lbl.text = ""
        pairs, dest = self._pairs, self._dest

        def status(text):
            Clock.schedule_once(lambda dt: setattr(self._status, "text", text))

        def worker():
            try:
                out = autotune(
                    pairs, dest, stop_check=lambda: self._stop_requested,
                    progress=lambda w, i, n: status(
                        f"Auto-tune: trying {w} worker(s) ({i + 1}/{n})..."))
                err = None
            except Exception as e:
                out, err = None, str(e)
            Clock.schedule_once(lambda dt: self._on_tune_done(out, err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_tune_done(self, out, err):
        self._busy = False
        self._analyze_btn.disabled = False
        self._tune_btn.disabled = False
        self._start_btn.disabled = not self._pairs
        self._stop_btn.disabled = True
        if err:
            self._status.text = f"Auto-tune failed: {err}"
            return
        if out is None:
            self._status.text = ("Auto-tune stopped." if self._stop_requested
                                 else "Auto-tune needs at least 8 smaller files "
                                      "to measure - use the recommendation above.")
            return
        self._concurrency_input.text = str(out["best"])
        rows = "   ".join(f"{w}: {mbs:.0f} MB/s" for w, _sec, mbs in out["results"])
        self._recommend_lbl.text = f"Measured best: {out['best']}"
        self._status.text = (f"Auto-tune on {out['sample_files']} of your files "
                             f"({_fmt_size(out['sample_bytes'])}) - using "
                             f"{out['best']} workers.")
        self._log_lbl.text = f"Workers: MB/s\n{rows}"

    # ── transfer ─────────────────────────────────────────────────────────
    def _run_transfer(self, *a):
        if self._busy or not self._pairs:
            return
        concurrency, warning = clamp_workers(self._concurrency_input.text or "1")
        self._concurrency_input.text = str(concurrency)

        self._busy = True
        self._stop_requested = False
        self._analyze_btn.disabled = True
        self._tune_btn.disabled = True
        self._start_btn.disabled = True
        self._stop_btn.disabled = False
        self._transferred_bytes = 0
        self._done_count = 0
        self._error_lines = []
        self._log_lbl.text = warning or ""

        pairs = self._pairs
        dest = self._dest
        mode = "move" if self._mode_spinner.text == "Move" else "copy"
        overwrite = self._overwrite_cb.active
        total = len(pairs)
        t_start = time.time()

        def log(msg):
            pass  # per-file waiting chatter isn't shown live; errors and
                  # skipped files are surfaced via on_result below instead

        def on_result(status, abs_path, dest_path, extra):
            if status == "done":
                self._done_count += 1
                self._transferred_bytes += (extra or 0)
            elif status == "error":
                self._error_lines.append(f"ERROR {abs_path}: {extra}")
            elif status == "skipped":
                self._error_lines.append(f"SKIPPED {abs_path}: {extra}")
            elapsed = max(time.time() - t_start, 1e-6)
            speed = (self._transferred_bytes / elapsed) / (1024 * 1024)
            Clock.schedule_once(lambda dt: setattr(
                self._status, "text",
                f"Transferring... {self._done_count}/{total} files, "
                f"{speed:.1f} MB/s"))

        def worker():
            run_transfer(pairs, dest, mode, concurrency, overwrite=overwrite,
                        stop_check=lambda: self._stop_requested,
                        log=log, on_result=on_result)
            Clock.schedule_once(lambda dt: self._on_transfer_done())

        threading.Thread(target=worker, daemon=True).start()

    def _request_stop(self, *a):
        self._stop_requested = True
        self._stop_btn.disabled = True
        self._status.text = "Stopping... (finishing files already in flight)"

    def _on_transfer_done(self):
        self._busy = False
        self._analyze_btn.disabled = False
        self._stop_btn.disabled = True
        self._pairs = None
        self._start_btn.disabled = True
        n_errors = len(self._error_lines)
        self._status.text = (
            f"Done. {self._done_count} transferred"
            f"{f', {n_errors} error/skipped' if n_errors else ''}. "
            f"Re-run Analyze before transferring again.")
        self._log_lbl.text = ("\n".join(self._error_lines) if self._error_lines
                              else "All files transferred with no errors.")

    # ── nav ──────────────────────────────────────────────────────────────
    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
