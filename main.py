# main.py — Srboli v2.4
import sys, os

app_dir = os.path.dirname(os.path.abspath(__file__))
for p in (app_dir, os.path.join(app_dir, "_internal")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# ── overlay dispatch ─────────────────────────────────────────────────────────
# In a PyInstaller build, sys.executable IS Srboli itself (there's no
# separate python interpreter to hand a script path to). So system_stats
# launches the overlay as `Srboli --overlay` instead of `python _overlay_app.py`
# when frozen. This has to be checked and handled BEFORE any Kivy Config
# calls below — Kivy only supports one Window per process, so the overlay
# (which sets its own small always-on-top window config) must take over this
# process completely rather than running after the main app's config exists.
if len(sys.argv) > 1 and sys.argv[1] == "--overlay":
    sys.path.insert(0, os.path.join(app_dir, "screens"))
    import _overlay_app  # noqa: F401 — runs OverlayApp().run() itself
    sys.exit(0)

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


from screens.registry import SCREENS, LABELS
from screens.settings_screen import load_settings, effective_menu_order

# "settings" is a core route like "dashboard" — always eager-loaded,
# not part of the manageable/hideable list in registry.SCREENS.
SETTINGS_ROUTE = ("settings", "screens.settings_screen", "SettingsScreen")


def ensure_screen_loaded(sm, route):
    """Build + add a screen to the ScreenManager if it isn't already
    present. Used both eagerly (non-lazy startup) and on-demand (lazy
    mode, or a Quick Switcher bind targeting a not-yet-built screen).
    Returns True if the screen is present after this call."""
    if sm.has_screen(route):
        return True
    for r, mod, cls_name in SCREENS:
        if r == route:
            sm.add_widget(try_import(mod, cls_name)(name=route))
            return True
    return False


class Dashboard(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._build()

    def _build(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        hdr = BoxLayout(size_hint_y=None, height=70)
        title_col = BoxLayout(orientation="vertical")
        title_col.add_widget(Label(text="[b]Srboli[/b]", markup=True,
                             font_size=32, size_hint_y=None, height=48))
        title_col.add_widget(Label(text="your pocket swiss-knife",
                             font_size=11, size_hint_y=None, height=18))
        hdr.add_widget(title_col)
        gear = Button(text="\u2699 Settings", size_hint=(None, None),
                     width=100, height=40, font_size=12,
                     pos_hint={"center_y": 0.5})
        gear.bind(on_release=lambda *a: setattr(self.manager, "current", "settings"))
        hdr.add_widget(gear)
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
        for route, label in effective_menu_order():
            btn = Button(text=label, size_hint_y=None, height=50, font_size=14)
            btn.bind(on_release=lambda inst, r=route: self._goto(r))
            grid.add_widget(btn)
        sv.add_widget(grid)
        root.add_widget(sv)

        root.add_widget(Label(text="Srboli v2.4", font_size=9,
                              size_hint_y=None, height=18))
        self.add_widget(root)

    def _goto(self, route):
        ensure_screen_loaded(self.manager, route)
        self.manager.current = route

    def on_enter(self, *a):
        # rebuild fully so screen-list reorders/hides made in Settings
        # show up immediately on returning to the dashboard
        self._build()

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
        sm.add_widget(try_import(SETTINGS_ROUTE[1], SETTINGS_ROUTE[2])(
            name=SETTINGS_ROUTE[0]))

        settings_cfg = load_settings()
        lazy = settings_cfg.get("lazy_load", False)
        if lazy:
            # Only "quickswitcher" is eager-loaded besides dashboard/settings
            # (it needs to exist for its own config-editing screen; the
            # global keybind listener itself doesn't need the screen built).
            # Everything else is built on first navigation via
            # ensure_screen_loaded(), called from Dashboard._goto() and
            # from the Quick Switcher's key dispatcher.
            ensure_screen_loaded(sm, "quickswitcher")
        else:
            for route, mod, cls_name in SCREENS:
                sm.add_widget(try_import(mod, cls_name)(name=route))
        sm.current = "dashboard"

        # Install global quick switcher (works from any screen)
        try:
            from screens.quickswitcher_screen import install_global_switcher
            install_global_switcher(
                sm, ensure_loader=(lambda r: ensure_screen_loaded(sm, r)))
        except Exception as e:
            print(f"QuickSwitcher not installed: {e}")

        return sm


if __name__ == "__main__":
    SrboliApp().run()
