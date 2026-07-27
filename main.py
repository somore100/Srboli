# main.py — Srboli v2.4
import sys, os

app_dir = os.path.dirname(os.path.abspath(__file__))
for p in (app_dir, os.path.join(app_dir, "_internal")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from kivy.config import Config
Config.set("input", "mouse", "mouse,disable_multitouch")
Config.set("kivy", "exit_on_escape", "0")

from kivy.core.text import LabelBase
# Register NotoColorEmoji so emoji render properly
_EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
if os.path.exists(_EMOJI_FONT):
    LabelBase.register("NotoEmoji", _EMOJI_FONT)

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.metrics import dp

import app_data


def try_import(module_path, class_name):
    try:
        import importlib
        cls = getattr(importlib.import_module(module_path), class_name)
        print(f"OK  {class_name}")
        return cls
    except Exception as exc:
        msg = str(exc)
        print(f"!!  {class_name}: {msg}")
        class Placeholder(Screen):
            def __init__(self, **kw):
                super().__init__(**kw)
                b = BoxLayout(orientation="vertical", padding=20, spacing=10)
                b.add_widget(Label(
                    text=f"[b]{class_name}[/b]\nnot available\n\n{msg}",
                    markup=True, font_size=13, halign="center"))
                btn = Button(text="Back", size_hint_y=None, height=48)
                btn.bind(on_release=lambda *a: setattr(
                    self.manager, "current", "dashboard"))
                b.add_widget(btn)
                self.add_widget(b)
        return Placeholder


SCREENS = [
    ("loading_timer",  "screens.loading_timer_screen",    "LoadingTimerScreen"),
    ("text_editor",    "screens.text_editor_screen",      "TextEditorScreen"),
    ("script_mode",    "screens.script_mode_screen",      "ScriptModeScreen"),
    ("full_editor",    "screens.full_editor_screen",      "FullEditorScreen"),
    ("basic_tools",    "screens.basic_tools_screen",      "BasicToolsScreen"),
    ("system_stats",   "screens.system_stats_screen",     "SystemStatsScreen"),
    ("gallery",        "screens.gallery_sorter_screen",   "GallerySorterScreen"),
    ("music",          "screens.music_screen",            "MusicScreen"),
    ("random_tools",   "screens.randomizer",              "UtilityToolsScreen"),
    ("image_text",     "screens.image_text_screen",       "ImageTextScreen"),
    ("morse",          "screens.morse_screen",            "MorseScreen"),
    ("backrooms",      "screens.backrooms_screen",        "BackroomsScreen"),
    ("spin",           "screens.spin_screen",             "SpinScreen"),
    ("unhelpful_calc", "screens.unhelpful_calc_screen",   "UnhelpfulCalcScreen"),
    ("shape_gen",      "screens.shape_generator_screen",  "ShapeGeneratorScreen"),
    ("metadata",       "screens.metadata_screen",         "MetadataScreen"),
    ("quickswitcher",  "screens.quickswitcher_screen",    "QuickSwitcherScreen"),
]

LABELS = {
    "loading_timer":  "Loading / Timer",
    "text_editor":    "Text Editor",
    "script_mode":    "Script / Teleprompter",
    "full_editor":    "Full Editor",
    "basic_tools":    "Basic Tools",
    "system_stats":   "System Stats",
    "gallery":        "Gallery Sorter",
    "music":          "Music Player",
    "random_tools":   "Random Tools",
    "image_text":     "Image to Text",
    "morse":          "Morse Converter",
    "backrooms":      "Backrooms",
    "spin":           "Wheel of Names",
    "unhelpful_calc": "Unhelpful Calc",
    "shape_gen":      "Shape Generator",
    "metadata":       "Metadata Inspector",
    "quickswitcher":  "Quick Switcher",
}


class Dashboard(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._build()

    def _build(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        hdr = BoxLayout(orientation="vertical", size_hint_y=None, height=70)
        hdr.add_widget(Label(text="[b]Srboli[/b]", markup=True,
                             font_size=32, size_hint_y=None, height=48))
        hdr.add_widget(Label(text="your pocket swiss-knife",
                             font_size=11, size_hint_y=None, height=18))
        root.add_widget(hdr)

        dir_row = BoxLayout(size_hint_y=None, height=dp(28), spacing=6)
        self._dir_lbl = Label(
            text=f"Data: {app_data.get_data_dir()}",
            font_size=10, halign="left", color=(0.5, 0.8, 1, 1))
        self._dir_lbl.bind(size=self._dir_lbl.setter("text_size"))
        chg = Button(text="Change", size_hint_x=None,
                     width=dp(72), font_size=11)
        chg.bind(on_release=self._change_dir)
        dir_row.add_widget(self._dir_lbl)
        dir_row.add_widget(chg)
        root.add_widget(dir_row)

        sv = ScrollView()
        grid = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=(6,6))
        grid.bind(minimum_height=grid.setter("height"))
        for route, label in LABELS.items():
            btn = Button(text=label, size_hint_y=None, height=50, font_size=14)
            btn.bind(on_release=lambda inst, r=route: setattr(
                self.manager, "current", r))
            grid.add_widget(btn)
        sv.add_widget(grid)
        root.add_widget(sv)

        root.add_widget(Label(text="Srboli v2.4", font_size=9,
                              size_hint_y=None, height=18))
        self.add_widget(root)

    def on_enter(self, *a):
        if hasattr(self, "_dir_lbl"):
            self._dir_lbl.text = f"Data: {app_data.get_data_dir()}"

    def _change_dir(self, *a):
        chooser = FileChooserIconView(
            path=os.path.expanduser("~"), dirselect=True)
        name_lbl = Label(
            text=f"Current: {app_data.get_data_dir()}",
            size_hint_y=None, height=dp(22), font_size=11,
            color=(0.5, 0.9, 1, 1))
        move_btn  = Button(text="Move data here", size_hint_y=None,
                           height=dp(44), font_size=14,
                           background_color=(0.2, 0.6, 0.2, 1))
        cache_btn = Button(text="Clear cache", size_hint_y=None,
                           height=dp(34), font_size=12,
                           background_color=(0.5, 0.35, 0.1, 1))
        all_btn   = Button(text="Clear ALL data", size_hint_y=None,
                           height=dp(34), font_size=12,
                           background_color=(0.65, 0.1, 0.1, 1))
        status    = Label(text="", size_hint_y=None, height=dp(22),
                          font_size=11, color=(0.4, 1, 0.4, 1))
        layout = BoxLayout(orientation="vertical", spacing=4, padding=6)
        for w in (name_lbl, chooser, move_btn, cache_btn, all_btn, status):
            layout.add_widget(w)
        popup = Popup(title="Data Directory", content=layout,
                      size_hint=(0.92, 0.92))

        def _move(*a):
            folder = (chooser.selection[0]
                      if chooser.selection and os.path.isdir(chooser.selection[0])
                      else chooser.path)
            try:
                new = app_data.set_data_dir(folder, move_old=True)
                name_lbl.text = f"Moved to: {new}"
                status.text   = f"Done: {new}"
                self._dir_lbl.text = f"Data: {new}"
            except Exception as e:
                status.text = f"Error: {e}"

        move_btn.bind(on_release=_move)
        cache_btn.bind(on_release=lambda *a: setattr(
            status, "text",
            f"Freed {app_data.clear_cache()//1024} KB"))
        all_btn.bind(on_release=lambda *a: (
            app_data.clear_all_data(),
            setattr(status, "text", "All data cleared.")))
        popup.open()

    def on_touch_down(self, touch):
        if hasattr(touch, "button"):
            if getattr(touch, "is_mouse_scrolling", False):
                return super().on_touch_down(touch)
            if touch.button != "left":
                return True
        return super().on_touch_down(touch)


class SrboliApp(App):
    def build(self):
        self.title = "Srboli"
        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(Dashboard(name="dashboard"))
        for route, mod, cls_name in SCREENS:
            sm.add_widget(try_import(mod, cls_name)(name=route))
        sm.current = "dashboard"

        # Install global quick switcher (works from any screen)
        try:
            from screens.quickswitcher_screen import install_global_switcher
            install_global_switcher(sm)
        except Exception as e:
            print(f"QuickSwitcher not installed: {e}")

        # Start global FPS writer for overlay (runs regardless of active screen)
        import collections as _col
        import time as _time
        import json as _json

        _frame_times = _col.deque(maxlen=30)
        _overlay_json = os.path.join(app_dir, ".srboli_overlay_data.json")

        def _fps_tick(dt):
            _frame_times.append(_time.monotonic())
            times = list(_frame_times)
            if len(times) >= 2:
                elapsed = times[-1] - times[0]
                fps = (len(times) - 1) / elapsed if elapsed > 0 else 0.0
            else:
                fps = 0.0
            try:
                try:
                    with open(_overlay_json, encoding="utf-8") as f:
                        data = _json.load(f)
                except Exception:
                    data = {}
                data["fps"] = round(fps, 1)
                data["ts"]  = _time.time()
                with open(_overlay_json, "w", encoding="utf-8") as f:
                    _json.dump(data, f)
            except Exception:
                pass

        from kivy.clock import Clock as _Clock
        _Clock.schedule_interval(_fps_tick, 1.0)

        return sm


if __name__ == "__main__":
    SrboliApp().run()
