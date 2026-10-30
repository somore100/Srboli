# screens/data_location.py - where Srboli keeps its data: show it, move it,
# clear the cache, wipe everything. Lives in Settings.
#
# Moving runs in a thread (it can be a lot of files); app_data.set_data_dir
# copies with verification and only switches once every file is safe.

import os
import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.label import Label
from kivy.uix.popup import Popup

import app_data
from core.android_storage import shared_storage_root
from screens.dialogs import confirm_popup, message_popup


class DataLocation(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(150), spacing=dp(6), **kw)
        self._label = Label(font_size=11, halign="left", valign="middle",
                            color=(0.5, 0.8, 1, 1), size_hint_y=None,
                            height=dp(40))
        self._label.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
        self.add_widget(self._label)
        row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        self._buttons = []
        for text, cb, color in (
                ("Move data...", self._choose_folder, (0.2, 0.45, 0.2, 1)),
                ("Clear cache", self._clear_cache, (0.5, 0.35, 0.1, 1)),
                ("Clear ALL data", self._clear_all, (0.65, 0.1, 0.1, 1))):
            b = Button(text=text, font_size=12, background_color=color)
            b.bind(on_release=cb)
            row.add_widget(b)
            self._buttons.append(b)
        self.add_widget(row)
        self._status = Label(font_size=11, halign="left", valign="middle",
                             size_hint_y=None, height=dp(40),
                             color=(0.6, 1, 0.6, 1))
        self._status.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
        self.add_widget(self._status)
        self.refresh()

    def refresh(self):
        self._label.text = f"Data folder: {app_data.get_data_dir()}"

    def _busy(self, busy):
        for b in self._buttons:
            b.disabled = busy

    # ── move ─────────────────────────────────────────────────────────────
    def _choose_folder(self, *a):
        chooser = FileChooserIconView(path=shared_storage_root(), dirselect=True)
        go = Button(text="Move data here", size_hint_y=None, height=dp(44),
                    background_color=(0.2, 0.6, 0.2, 1))
        box = BoxLayout(orientation="vertical", spacing=dp(4))
        box.add_widget(chooser)
        box.add_widget(go)
        pop = Popup(title="Move data to (a 'srboli_data' folder is created)",
                    content=box, size_hint=(0.92, 0.92))

        def _go(*_):
            folder = (chooser.selection[0] if chooser.selection
                      and os.path.isdir(chooser.selection[0]) else chooser.path)
            pop.dismiss()
            self._start_move(folder)

        go.bind(on_release=_go)
        pop.open()

    def _start_move(self, folder, use_existing=False):
        self._busy(True)
        self._status.color = (0.9, 0.9, 0.5, 1)
        self._status.text = "Moving... 0%"

        def progress(done, total):
            pct = int(100 * done / total) if total else 100
            Clock.schedule_once(lambda dt: setattr(
                self._status, "text", f"Moving... {pct}% ({done}/{total} files)"))

        def work():
            try:
                new = app_data.set_data_dir(folder, move_old=True,
                                            use_existing=use_existing,
                                            progress=progress)
                Clock.schedule_once(lambda dt: self._moved(new, use_existing))
            except app_data.DataDirExists as e:
                Clock.schedule_once(lambda dt, e=e: self._exists(folder, e.path))
            except app_data.MoveFailed as e:
                Clock.schedule_once(lambda dt, e=e: self._failed(e))
            except Exception as e:
                Clock.schedule_once(lambda dt, e=e: self._error(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _done(self):
        self._busy(False)
        self.refresh()

    def _moved(self, new, repointed):
        self._done()
        self._status.color = (0.4, 1, 0.4, 1)
        self._status.text = (f"Now using {new}. Your old data was left where "
                             "it was. " if repointed else f"Moved to {new}. ") + \
            "Restart Srboli so every screen uses the new folder."

    def _exists(self, folder, path):
        self._done()
        self._status.text = "Nothing was moved."
        confirm_popup(
            "That folder already has data",
            f"{path}\nalready contains data. Nothing will be overwritten.\n"
            "Use the data that is there? (Your current data stays where it is.)",
            lambda: self._start_move(folder, use_existing=True),
            yes_text="Use existing data")

    def _failed(self, err):
        self._done()
        self._status.color = (1, 0.5, 0.4, 1)
        self._status.text = "Move failed. Still using the old folder, nothing lost."
        lines = "\n".join(f"{os.path.basename(p)}: {why}" for p, why in err.failures[:8])
        more = len(err.failures) - 8
        message_popup("Couldn't move everything",
                      lines + (f"\n...and {more} more" if more > 0 else ""),
                      size_hint=(0.9, 0.5))

    def _error(self, text):
        self._done()
        self._status.color = (1, 0.5, 0.4, 1)
        self._status.text = f"Not moved: {text}"

    # ── clear ────────────────────────────────────────────────────────────
    def _clear_cache(self, *a):
        freed = app_data.clear_cache()
        self._status.color = (1, 0.85, 0.3, 1)
        self._status.text = f"Cache cleared, freed {freed // 1024} KB."

    def _clear_all(self, *a):
        folder = app_data.get_data_dir()
        confirm_popup(
            "Delete ALL app data?",
            "Playlists, sort rules, autosaves, documents and settings\n"
            "will be deleted. This cannot be undone.",
            lambda: confirm_popup(
                "Really delete everything?",
                f"Last chance. This permanently deletes everything in\n{folder}",
                self._do_clear_all, yes_text="Yes, delete it all"),
            yes_text="Continue")

    def _do_clear_all(self):
        try:
            app_data.clear_all_data()
            self._status.color = (1, 0.5, 0.5, 1)
            self._status.text = "All data cleared."
        except OSError as e:
            self._status.text = f"Couldn't clear everything: {e}"
