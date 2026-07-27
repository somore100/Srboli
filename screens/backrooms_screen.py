# screens/converted/backrooms_screen.py
# Linux + Windows compatible. FileChooser starts at home dir.

import os
import json

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout

POSSIBLE_FILENAMES = ("backrooms_data.json", "backrooms_levels.json")
PATH_SAVE = os.path.join(os.path.expanduser("~"), ".srboli_backrooms_path.txt")


def find_levels_json():
    # 1) saved path
    if os.path.exists(PATH_SAVE):
        p = open(PATH_SAVE, encoding="utf-8").read().strip()
        if p and os.path.exists(p):
            return p

    # 2) cwd
    for fn in POSSIBLE_FILENAMES:
        if os.path.exists(fn):
            return os.path.abspath(fn)

    # 3) two levels up (project root)
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    for fn in POSSIBLE_FILENAMES:
        p = os.path.join(base, fn)
        if os.path.exists(p):
            return p

    # 4) same dir as this file
    for fn in POSSIBLE_FILENAMES:
        p = os.path.join(os.path.dirname(__file__), fn)
        if os.path.exists(p):
            return p

    return None


class BackroomsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.levels = {}
        self.json_path = None

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        # ── search bar ──
        top = BoxLayout(size_hint_y=None, height=44, spacing=8)
        self.search_input = TextInput(
            hint_text="Level number or nickname", multiline=False
        )
        search_btn = Button(text="Search", size_hint_x=None, width=110)
        search_btn.bind(on_release=self.perform_search)
        locate_btn = Button(text=" Locate JSON", size_hint_x=None, width=130)
        locate_btn.bind(on_release=self.open_file_chooser)
        top.add_widget(self.search_input)
        top.add_widget(search_btn)
        top.add_widget(locate_btn)
        root.add_widget(top)

        self.info_label = Label(text="", size_hint_y=None, height=26,
                                font_size=11)
        root.add_widget(self.info_label)

        sv = ScrollView()
        self.grid = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=6)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        sv.add_widget(self.grid)
        root.add_widget(sv)

        back = Button(text="< Back", size_hint_y=None, height=44)
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)
        self.try_load_json()

    def try_load_json(self):
        self.json_path = find_levels_json()
        if self.json_path and os.path.exists(self.json_path):
            try:
                with open(self.json_path, encoding="utf-8") as f:
                    raw = json.load(f)
                self.levels = {str(k): v for k, v in raw.items()}
                self.info_label.text = f"OK  Loaded: {self.json_path}"
                # show first entry
                first = next(iter(self.levels.values()))
                self.display_level(first)
                return
            except Exception as e:
                self.info_label.text = f"⚠  Parse error: {e}"
        else:
            self.info_label.text = "JSON not found — use  Locate JSON"

        self.grid.clear_widgets()
        self.grid.add_widget(Label(
            text="No backrooms data loaded.\nUse 'Locate JSON' to find your file.",
            size_hint_y=None, height=60, halign="center",
        ))

    def open_file_chooser(self, *a):
        chooser = FileChooserIconView(
            path=os.path.expanduser("~"),
            filters=["*.json"],
            multiselect=False,
        )
        btn = Button(text="Select", size_hint_y=None, height=44)
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Locate backrooms .json", content=layout,
                      size_hint=(0.92, 0.92))

        def _select(inst):
            if chooser.selection:
                chosen = os.path.abspath(chooser.selection[0])
                with open(PATH_SAVE, "w", encoding="utf-8") as f:
                    f.write(chosen)
                popup.dismiss()
                self.try_load_json()
            else:
                popup.dismiss()

        btn.bind(on_release=_select)
        popup.open()

    def perform_search(self, *a):
        q = self.search_input.text.strip().lower()
        if not q:
            return
        entry = None
        if q.isdigit():
            entry = self.levels.get(q)
        if not entry:
            for k, v in self.levels.items():
                nick = str(v.get("nickname", "")).lower()
                if q in nick or q == k:
                    entry = v
                    break
        if not entry:
            self.grid.clear_widgets()
            self.grid.add_widget(Label(text=f"No results for '{q}'.",
                                       size_hint_y=None, height=36))
            return
        self.display_level(entry)

    def display_level(self, level):
        self.grid.clear_widgets()

        def row(text, height=28):
            lbl = Label(text=text, markup=True, size_hint_y=None,
                        height=height, halign="left", valign="top")
            lbl.bind(size=lbl.setter("text_size"))
            self.grid.add_widget(lbl)

        row(f"[b]{level.get('nickname', 'Unnamed')}[/b]", 32)
        row(f"Danger:      {level.get('danger', 'Unknown')}")
        row(f"Expectation: {level.get('expectation', '')}")

        entities = level.get("entities", [])
        if isinstance(entities, list):
            entities = ", ".join(str(e) for e in entities)
        row(f"Entities:    {entities}")

        row("[b]Description:[/b]", 24)
        desc = level.get("description", "")
        # wrap long description
        desc_lbl = Label(text=desc, size_hint_y=None, halign="left",
                         valign="top", markup=True)
        desc_lbl.bind(
            texture_size=lambda inst, ts: setattr(inst, "height", ts[1]),
            width=lambda inst, w: setattr(inst, "text_size", (w, None)),
        )
        self.grid.add_widget(desc_lbl)

        tips = level.get("tips", [])
        if tips:
            row("[b]Tips:[/b]", 24)
            for tip in tips:
                row(f"  • {tip}")

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"

    def on_touch_down(self, touch):
        if hasattr(touch, "button") and touch.button == "right":
            return True
        return super().on_touch_down(touch)
