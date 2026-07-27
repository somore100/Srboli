# screens/quickswitcher_screen.py
# Quick Switcher — assign keybinds to jump to any Srboli screen instantly
# Also supports a "lock / log out" keybind that returns to dashboard

import os, json

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp

import app_data

# All available Srboli routes (must match SCREENS in main.py)
ALL_ROUTES = [
    "dashboard", "loading_timer", "text_editor", "script_mode",
    "full_editor", "basic_tools", "system_stats", "gallery",
    "music", "random_tools", "image_text", "morse", "backrooms",
    "spin", "unhelpful_calc", "shape_gen", "metadata", "quickswitcher",
]

ROUTE_LABELS = {
    "dashboard":      "Dashboard (home)",
    "loading_timer":  "Loading / Timer",
    "text_editor":    "Text Editor",
    "script_mode":    "Script Mode",
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

MODIFIERS = ["ctrl", "alt", "shift", "ctrl+shift", "ctrl+alt", "alt+shift"]
KEYS_ALPHA = list("abcdefghijklmnopqrstuvwxyz")
KEYS_NUM   = [str(i) for i in range(0, 10)]
KEYS_F     = [f"f{i}" for i in range(1, 13)]
ALL_KEYS   = KEYS_ALPHA + KEYS_NUM + KEYS_F

CONFIG_FILE_NAME = "quickswitcher.json"


def _load_config():
    path = os.path.join(app_data.subdir("config"), CONFIG_FILE_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"binds": [], "enabled": True}


def _save_config(data):
    path = os.path.join(app_data.subdir("config"), CONFIG_FILE_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _key_matches(bind, key_str, modifiers_set):
    """Check if a key event matches a bind dict."""
    bmod = set(bind.get("modifier", "").split("+")) - {""}
    bkey = bind.get("key", "").lower()
    return bmod == modifiers_set and bkey == key_str.lower()


class QuickSwitcherScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._config  = _load_config()
        self._enabled = self._config.get("enabled", True)

        root = BoxLayout(orientation="vertical", padding=8, spacing=6)

        # ── header ────────────────────────────────────────────────────────
        hdr = BoxLayout(size_hint_y=None, height=dp(38), spacing=8)
        hdr.add_widget(Label(
            text="Quick Switcher", font_size=17, bold=True,
            size_hint_x=0.5))
        self._enable_btn = ToggleButton(
            text="Enabled" if self._enabled else "Disabled",
            state="down" if self._enabled else "normal",
            size_hint_x=None, width=dp(100), font_size=13)
        self._enable_btn.bind(on_release=self._toggle_enabled)
        hdr.add_widget(self._enable_btn)
        root.add_widget(hdr)

        root.add_widget(Label(
            text="Assign keyboard shortcuts to jump to any screen.\n"
                 "Shortcuts work from any screen when Quick Switcher is enabled.",
            size_hint_y=None, height=dp(36), font_size=11, halign="left"))

        # ── add bind row ──────────────────────────────────────────────────
        add_box = BoxLayout(size_hint_y=None, height=dp(44), spacing=5)

        add_box.add_widget(Label(text="Modifier:", size_hint_x=None,
                                 width=dp(66), font_size=12))
        self._mod_sp = Spinner(text="ctrl", values=MODIFIERS,
                               size_hint_x=None, width=dp(110), font_size=12)
        add_box.add_widget(self._mod_sp)

        add_box.add_widget(Label(text="+", size_hint_x=None,
                                 width=dp(14), font_size=16))

        self._key_sp = Spinner(text="1", values=ALL_KEYS,
                               size_hint_x=None, width=dp(72), font_size=12)
        add_box.add_widget(self._key_sp)

        add_box.add_widget(Label(text="->", size_hint_x=None,
                                 width=dp(22), font_size=14))

        self._dest_sp = Spinner(
            text="basic_tools",
            values=ALL_ROUTES,
            font_size=12)
        add_box.add_widget(self._dest_sp)

        add_btn = Button(text="Add", size_hint_x=None, width=dp(60),
                         font_size=13, background_color=(0.2,0.6,0.2,1))
        add_btn.bind(on_release=self._add_bind)
        add_box.add_widget(add_btn)
        root.add_widget(add_box)

        # ── special: log out / go home bind ──────────────────────────────
        logout_box = BoxLayout(size_hint_y=None, height=dp(38), spacing=5)
        logout_box.add_widget(Label(text="Log out / Home bind:",
                                    size_hint_x=None, width=dp(150),
                                    font_size=12))
        self._logout_mod = Spinner(text="ctrl", values=MODIFIERS,
                                   size_hint_x=None, width=dp(100),
                                   font_size=12)
        logout_box.add_widget(self._logout_mod)
        logout_box.add_widget(Label(text="+", size_hint_x=None,
                                    width=dp(12), font_size=14))
        self._logout_key = Spinner(text="q", values=ALL_KEYS,
                                   size_hint_x=None, width=dp(66),
                                   font_size=12)
        logout_box.add_widget(self._logout_key)
        set_lo = Button(text="Set", size_hint_x=None, width=dp(54),
                        font_size=12)
        set_lo.bind(on_release=self._set_logout)
        logout_box.add_widget(set_lo)
        self._logout_lbl = Label(
            text=self._logout_bind_str(), font_size=11,
            color=(0.8, 0.8, 0.5, 1))
        logout_box.add_widget(self._logout_lbl)
        root.add_widget(logout_box)

        # ── binds list ────────────────────────────────────────────────────
        root.add_widget(Label(text="Current shortcuts:", size_hint_y=None,
                              height=dp(22), font_size=13, bold=True))
        sv = ScrollView()
        self._binds_grid = GridLayout(cols=1, spacing=3, size_hint_y=None)
        self._binds_grid.bind(minimum_height=self._binds_grid.setter("height"))
        sv.add_widget(self._binds_grid)
        root.add_widget(sv)

        # ── status ────────────────────────────────────────────────────────
        self._status = Label(text="", size_hint_y=None, height=dp(24),
                             font_size=12, color=(0.4, 1, 0.4, 1))
        root.add_widget(self._status)

        back = Button(text="Back", size_hint_y=None, height=dp(42))
        back.bind(on_release=lambda *a: setattr(
            self.manager, "current", "dashboard"))
        root.add_widget(back)

        self.add_widget(root)
        self._refresh_binds_ui()

    # ── bind management ───────────────────────────────────────────────────
    def _add_bind(self, *a):
        mod  = self._mod_sp.text
        key  = self._key_sp.text
        dest = self._dest_sp.text
        bind = {"modifier": mod, "key": key, "dest": dest}
        # check for duplicate
        for b in self._config.get("binds", []):
            if b.get("modifier") == mod and b.get("key") == key:
                self._status.text = (f"Conflict: {mod}+{key} already bound "
                                     f"to {b['dest']}")
                return
        self._config.setdefault("binds", []).append(bind)
        _save_config(self._config)
        self._refresh_binds_ui()
        self._status.text = (f"Added: {mod}+{key} -> "
                             f"{ROUTE_LABELS.get(dest, dest)}")

    def _remove_bind(self, idx):
        binds = self._config.get("binds", [])
        if 0 <= idx < len(binds):
            removed = binds.pop(idx)
            _save_config(self._config)
            self._refresh_binds_ui()
            self._status.text = (f"Removed: {removed['modifier']}+"
                                 f"{removed['key']}")

    def _set_logout(self, *a):
        mod = self._logout_mod.text
        key = self._logout_key.text
        self._config["logout_bind"] = {"modifier": mod, "key": key}
        _save_config(self._config)
        self._logout_lbl.text = self._logout_bind_str()
        self._status.text = f"Log out bind set: {mod}+{key}"

    def _logout_bind_str(self):
        lb = self._config.get("logout_bind")
        if lb:
            return f"Current: {lb.get('modifier')}+{lb.get('key')}"
        return "Not set"

    def _toggle_enabled(self, btn):
        self._enabled = btn.state == "down"
        btn.text = "Enabled" if self._enabled else "Disabled"
        self._config["enabled"] = self._enabled
        _save_config(self._config)
        self._status.text = ("Quick switcher ON" if self._enabled
                             else "Quick switcher OFF")

    def _refresh_binds_ui(self):
        self._binds_grid.clear_widgets()
        binds = self._config.get("binds", [])
        if not binds:
            self._binds_grid.add_widget(Label(
                text="No shortcuts set. Add one above.",
                size_hint_y=None, height=dp(26), font_size=12))
            return
        for i, bind in enumerate(binds):
            mod  = bind.get("modifier", "")
            key  = bind.get("key", "")
            dest = bind.get("dest", "")
            row  = BoxLayout(size_hint_y=None, height=dp(30), spacing=5)
            row.add_widget(Label(
                text=f"{mod}+{key}",
                size_hint_x=None, width=dp(120),
                font_size=13, bold=True, color=(0.9, 0.9, 0.4, 1)))
            row.add_widget(Label(
                text=f"-> {ROUTE_LABELS.get(dest, dest)}",
                font_size=12, halign="left"))
            rm = Button(text="Remove", size_hint_x=None, width=dp(78),
                        font_size=11, background_color=(0.6,0.15,0.15,1))
            rm.bind(on_release=lambda inst, idx=i: self._remove_bind(idx))
            row.add_widget(rm)
            self._binds_grid.add_widget(row)

    # ── global key handler (registered on enter/leave) ────────────────────
    def on_enter(self, *a):
        Window.bind(on_key_down=self._on_key)

    def on_leave(self, *a):
        Window.unbind(on_key_down=self._on_key)

    def _on_key(self, window, key, scancode, codepoint, modifiers):
        # This is also called for OTHER screens via the global handler
        # registered in main.py — see _install_global_switcher()
        pass


# ── Global switcher installer — call this from main.py build() ───────────────
def install_global_switcher(screen_manager):
    """
    Installs a global key handler on the Window that responds to quick
    switcher binds from any screen.
    """
    def _on_key(window, key, scancode, codepoint, modifiers):
        config = _load_config()
        if not config.get("enabled", True):
            return

        mod_set = set(modifiers) if modifiers else set()

        # normalise modifier names
        mod_str = "+".join(sorted(m for m in mod_set
                                  if m in ("ctrl","alt","shift")))

        # key name
        key_name = codepoint.lower() if codepoint else ""
        if not key_name:
            # try scancode for function keys
            fkey_map = {282:"f1",283:"f2",284:"f3",285:"f4",
                        286:"f5",287:"f6",288:"f7",289:"f8",
                        290:"f9",291:"f10",292:"f11",293:"f12"}
            key_name = fkey_map.get(key, "")

        if not key_name:
            return

        # check logout bind
        lb = config.get("logout_bind")
        if lb:
            lb_mod = lb.get("modifier","")
            lb_key = lb.get("key","").lower()
            if lb_key == key_name and lb_mod == mod_str:
                screen_manager.current = "dashboard"
                return

        # check screen binds
        for bind in config.get("binds", []):
            b_mod = bind.get("modifier","")
            b_key = bind.get("key","").lower()
            dest  = bind.get("dest","")
            if b_key == key_name and b_mod == mod_str:
                if dest in [s.name for s in screen_manager.screens]:
                    screen_manager.current = dest
                return

    Window.bind(on_key_down=_on_key)
