# screens/data_dir_screen.py
# First-launch + settings screen for app data directory.
# Shown on every launch; cannot be skipped on first run.

import os
import shutil

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.metrics import dp

import app_data


def _fmt_bytes(b):
    if b < 1024:       return f"{b} B"
    elif b < 1048576:  return f"{b/1024:.1f} KB"
    else:              return f"{b/1048576:.1f} MB"


class DataDirScreen(Screen):
    """
    Shown on every launch.
    - First launch: cannot proceed until a dir is chosen or
      'Save next to app' is clicked.
    - Subsequent launches: shows current dir, can change/clear/continue.
    """

    def __init__(self, on_continue, first_launch=False, **kw):
        super().__init__(**kw)
        self._on_continue  = on_continue
        self._first_launch = first_launch

        root = BoxLayout(orientation="vertical", padding=16, spacing=10)

        # ── header ──
        if first_launch:
            header_text = ("[b]Welcome to Srboli![/b]\n"
                           "Choose where the app stores its data.\n"
                           "You can change this later from the dashboard.")
        else:
            header_text = ("[b]Srboli — Data Directory[/b]\n"
                           "Change where the app saves playlists, "
                           "sort configs, autosaves, and other data.")
        hdr = Label(text=header_text, markup=True,
                    size_hint_y=None, height=dp(72),
                    font_size=14, halign="center", valign="middle")
        hdr.bind(size=hdr.setter("text_size"))
        root.add_widget(hdr)

        # ── current path display ──
        cur = app_data.get_data_dir()
        self._path_label = Label(
            text=f"Current: {cur}",
            size_hint_y=None, height=dp(28),
            font_size=12, halign="left", color=(0.7, 0.9, 1, 1))
        self._path_label.bind(size=self._path_label.setter("text_size"))
        root.add_widget(self._path_label)

        # ── choose folder ──
        choose_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        choose_btn = Button(text="📁 Choose Folder", font_size=14)
        choose_btn.bind(on_release=self._pick_folder)
        same_btn = Button(text="📌 Save next to app", font_size=13)
        same_btn.bind(on_release=self._use_app_dir)
        choose_row.add_widget(choose_btn)
        choose_row.add_widget(same_btn)
        root.add_widget(choose_row)

        # ── move toggle ──
        move_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=8)
        self._move_cb = ToggleButton(text="Move existing data",
                                     state="down", size_hint_x=None,
                                     width=dp(180), font_size=13)
        move_row.add_widget(self._move_cb)
        move_row.add_widget(Label(
            text="(copies old data to new location)",
            font_size=11, halign="left"))
        root.add_widget(move_row)

        # ── status ──
        self._status = Label(text="", size_hint_y=None, height=dp(26),
                             font_size=12, color=(0.6, 1, 0.6, 1))
        root.add_widget(self._status)

        # ── danger zone ──
        root.add_widget(Label(text="[b]Data management[/b]", markup=True,
                              size_hint_y=None, height=dp(28), font_size=13))
        danger = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        cache_btn = Button(text="🗑 Clear cache / temp files",
                           font_size=12,
                           background_color=(0.6, 0.4, 0.1, 1))
        all_btn   = Button(text="☢ Clear ALL data",
                           font_size=12,
                           background_color=(0.7, 0.1, 0.1, 1))
        cache_btn.bind(on_release=self._clear_cache)
        all_btn.bind(on_release=self._clear_all)
        danger.add_widget(cache_btn)
        danger.add_widget(all_btn)
        root.add_widget(danger)

        root.add_widget(Label())  # spacer

        # ── continue button ──
        cont_text = "▶ Continue to Srboli" if not first_launch else "✅ Save & Start Srboli"
        self._cont_btn = Button(
            text=cont_text,
            size_hint_y=None, height=dp(54),
            font_size=16,
            background_color=(0.2, 0.6, 0.2, 1),
        )
        self._cont_btn.bind(on_release=self._continue)
        root.add_widget(self._cont_btn)

        self.add_widget(root)

    # ── actions ──────────────────────────────────────────────────────────────
    def _pick_folder(self, *a):
        chooser = FileChooserIconView(
            path=os.path.expanduser("~"),
            dirselect=True, multiselect=False,
        )
        btn = Button(text="Select this folder", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Choose data folder", content=layout,
                      size_hint=(0.92, 0.92))

        def _sel(inst):
            folder = chooser.path
            if chooser.selection and os.path.isdir(chooser.selection[0]):
                folder = chooser.selection[0]
            popup.dismiss()
            self._apply_dir(folder)

        btn.bind(on_release=_sel)
        popup.open()

    def _use_app_dir(self, *a):
        app_dir = os.path.dirname(os.path.abspath(__file__))
        self._apply_dir(app_dir)

    def _apply_dir(self, folder):
        move = self._move_cb.state == "down"
        try:
            new_path = app_data.set_data_dir(folder, move_old=move)
            self._path_label.text = f"Current: {new_path}"
            self._status.text = f"✅ Set to: {new_path}"
            self._status.color = (0.4, 1, 0.4, 1)
        except Exception as e:
            self._status.text = f"Error: {e}"
            self._status.color = (1, 0.4, 0.4, 1)

    def _clear_cache(self, *a):
        freed = app_data.clear_cache()
        self._status.text = f"Cache cleared — freed {_fmt_bytes(freed)}"
        self._status.color = (1, 0.85, 0.3, 1)

    def _clear_all(self, *a):
        layout = BoxLayout(orientation="vertical", padding=10, spacing=8)
        layout.add_widget(Label(
            text="Delete ALL app data?\n(playlists, sort configs, autosaves…)\nThis cannot be undone.",
            halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        yes = Button(text="Yes, delete everything",
                     background_color=(0.8, 0.1, 0.1, 1))
        no  = Button(text="Cancel")
        row.add_widget(yes); row.add_widget(no)
        layout.add_widget(row)
        popup = Popup(title="Confirm", content=layout,
                      size_hint=(0.7, 0.44))

        def _do(*a):
            app_data.clear_all_data()
            self._status.text = "All data cleared."
            self._status.color = (1, 0.5, 0.5, 1)
            popup.dismiss()

        yes.bind(on_release=_do)
        no.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    def _continue(self, *a):
        self._on_continue()
