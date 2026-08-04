# screens/quickswitcher_screen.py
# Quick Switcher — assign keybinds to jump to any Srboli screen instantly
# Also supports a "lock / log out" keybind that returns to dashboard

import os, sys, json, subprocess

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.filechooser import FileChooserIconView
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


def _home():
    return os.path.expanduser("~")


def _launch_external(path):
    """Launch an external app or script (not one of Srboli's own screens)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            if os.access(path, os.X_OK):
                subprocess.Popen([path])
            else:
                subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"QuickSwitcher: failed to launch {path}: {e}")


def _normalize_mod(mod_str):
    """Canonical form for a modifier combo, e.g. 'alt+ctrl' -> 'ctrl+alt'.
    Used both when saving a bind and when reading the live keypress, so
    the two sides always compare equal regardless of which order the
    modifiers were typed/sorted in."""
    parts = [p for p in mod_str.split("+") if p]
    return "+".join(sorted(parts))


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
            text="Assign keyboard shortcuts to jump to a screen or launch "
                 "an external app/script.\n"
                 "Shortcuts work from any screen when Quick Switcher is enabled.",
            size_hint_y=None, height=dp(36), font_size=11, halign="left"))

        # ── target type toggle ───────────────────────────────────────────
        self._target_type = "screen"   # or "external"
        type_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=5)
        type_row.add_widget(Label(text="Target:", size_hint_x=None,
                                  width=dp(56), font_size=12))
        self._type_screen_btn = ToggleButton(
            text="In-app screen", group="target_type", state="down",
            size_hint_x=None, width=dp(120), font_size=12)
        self._type_ext_btn = ToggleButton(
            text="External app/script", group="target_type",
            size_hint_x=None, width=dp(150), font_size=12)
        self._type_screen_btn.bind(
            on_release=lambda *a: self._set_target_type("screen"))
        self._type_ext_btn.bind(
            on_release=lambda *a: self._set_target_type("external"))
        type_row.add_widget(self._type_screen_btn)
        type_row.add_widget(self._type_ext_btn)
        root.add_widget(type_row)

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

        # this container swaps between the screen spinner and the
        # external-file picker depending on the target type toggle above
        self._dest_container = BoxLayout(spacing=5)
        add_box.add_widget(self._dest_container)

        self._dest_sp = Spinner(
            text="basic_tools",
            values=ALL_ROUTES,
            font_size=12)

        self._ext_path = ""
        self._ext_pick_btn = Button(text="Pick app/script...", font_size=12)
        self._ext_pick_btn.bind(on_release=self._pick_external)
        self._ext_path_lbl = Label(text="(none chosen)", font_size=10,
                                   halign="left", color=(0.7, 0.9, 0.7, 1))
        self._ext_path_lbl.bind(size=self._ext_path_lbl.setter("text_size"))

        self._dest_container.add_widget(self._dest_sp)

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

    # ── target type (in-app screen vs external app/script) ─────────────────
    def _set_target_type(self, kind):
        self._target_type = kind
        self._dest_container.clear_widgets()
        if kind == "screen":
            self._dest_container.add_widget(self._dest_sp)
        else:
            col = BoxLayout(orientation="vertical", spacing=2)
            col.add_widget(self._ext_pick_btn)
            col.add_widget(self._ext_path_lbl)
            self._dest_container.add_widget(col)

    def _pick_external(self, *a):
        chooser = FileChooserIconView(path=_home(), multiselect=False)
        btn = Button(text="Choose this file", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser); layout.add_widget(btn)
        popup = Popup(title="Pick an app or script", content=layout,
                      size_hint=(0.92, 0.92))

        def _sel(*a):
            if chooser.selection:
                self._ext_path = chooser.selection[0]
                self._ext_path_lbl.text = self._ext_path
            popup.dismiss()

        btn.bind(on_release=_sel)
        popup.open()

    # ── bind management ───────────────────────────────────────────────────
    def _add_bind(self, *a):
        mod  = _normalize_mod(self._mod_sp.text)
        key  = self._key_sp.text

        if self._target_type == "external":
            if not self._ext_path:
                self._status.text = "Pick an app/script first."
                return
            dest  = self._ext_path
            btype = "external"
            label = os.path.basename(dest)
        else:
            dest  = self._dest_sp.text
            btype = "screen"
            label = ROUTE_LABELS.get(dest, dest)

        bind = {"modifier": mod, "key": key, "dest": dest, "type": btype}
        # check for duplicate against other binds
        for b in self._config.get("binds", []):
            if b.get("modifier") == mod and b.get("key") == key:
                self._status.text = (f"Conflict: {mod}+{key} already bound "
                                     f"to {b['dest']}")
                return
        # check for duplicate against the logout bind
        lb = self._config.get("logout_bind")
        if lb and _normalize_mod(lb.get("modifier", "")) == mod and lb.get("key") == key:
            self._status.text = f"Conflict: {mod}+{key} is set as the log out / home bind"
            return
        self._config.setdefault("binds", []).append(bind)
        _save_config(self._config)
        self._refresh_binds_ui()
        self._status.text = f"Added: {mod}+{key} -> {label}"

    def _remove_bind(self, idx):
        binds = self._config.get("binds", [])
        if 0 <= idx < len(binds):
            removed = binds.pop(idx)
            _save_config(self._config)
            self._refresh_binds_ui()
            self._status.text = (f"Removed: {removed['modifier']}+"
                                 f"{removed['key']}")

    def _set_logout(self, *a):
        mod = _normalize_mod(self._logout_mod.text)
        key = self._logout_key.text
        for b in self._config.get("binds", []):
            if b.get("modifier") == mod and b.get("key") == key:
                self._status.text = (f"Conflict: {mod}+{key} is already bound "
                                     f"to {ROUTE_LABELS.get(b.get('dest'), b.get('dest'))}")
                return
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
            mod   = bind.get("modifier", "")
            key   = bind.get("key", "")
            dest  = bind.get("dest", "")
            btype = bind.get("type", "screen")
            if btype == "external":
                target_label = f"[app] {os.path.basename(dest)}"
            else:
                target_label = ROUTE_LABELS.get(dest, dest)
            row  = BoxLayout(size_hint_y=None, height=dp(30), spacing=5)
            row.add_widget(Label(
                text=f"{mod}+{key}",
                size_hint_x=None, width=dp(120),
                font_size=13, bold=True, color=(0.9, 0.9, 0.4, 1)))
            row.add_widget(Label(
                text=f"-> {target_label}",
                font_size=12, halign="left"))
            rm = Button(text="Remove", size_hint_x=None, width=dp(78),
                        font_size=11, background_color=(0.6,0.15,0.15,1))
            rm.bind(on_release=lambda inst, idx=i: self._remove_bind(idx))
            row.add_widget(rm)
            self._binds_grid.add_widget(row)


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

        # normalise modifier names (alphabetical order — matches
        # _normalize_mod, so it lines up with whatever was saved)
        mod_str = _normalize_mod("+".join(m for m in mod_set
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
            lb_mod = _normalize_mod(lb.get("modifier",""))
            lb_key = lb.get("key","").lower()
            if lb_key == key_name and lb_mod == mod_str:
                screen_manager.current = "dashboard"
                return

        # check binds — either switch to an in-app screen, or launch an
        # external app/script
        for bind in config.get("binds", []):
            b_mod = _normalize_mod(bind.get("modifier",""))
            b_key = bind.get("key","").lower()
            dest  = bind.get("dest","")
            btype = bind.get("type", "screen")
            if b_key == key_name and b_mod == mod_str:
                if btype == "external":
                    _launch_external(dest)
                elif dest in [s.name for s in screen_manager.screens]:
                    screen_manager.current = dest
                return

    Window.bind(on_key_down=_on_key)
