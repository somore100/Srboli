# screens/settings_screen.py
# Settings — manage which screens show up on the Dashboard and in what
# order, plus a few app-wide behaviour toggles (currently: lazy loading).
#
# Persisted to <data_dir>/config/app_settings.json:
#   {
#     "order":      [route, route, ...],   # dashboard menu order
#     "hidden":     [route, route, ...],   # routes hidden from the menu
#     "removed":    [route, ...],          # routes removed for good (Manage tools screen)
#     "lazy_load":  bool,                  # build screens on first visit (default True)
#     "transition": "fade" | "none",       # screen change effect (default fade)
#     "loading_style": "text" | "logo" | "none",  # what shows while a tool builds
#     "rounded": bool,                     # rounded buttons (default True)
#     "theme": "dark" | "blue" | "light",   # colour preset, applied at startup
#     "show_recent": bool,                 # show the Dashboard "Recent" row (default True)
#     "recent":     [route, ...],          # last used tools (Dashboard "Recent" row)
#     "collapsed":  [group key, ...]       # Dashboard sections folded shut
#   }
# "recent" and "collapsed" belong to the Dashboard (update_dashboard_state);
# this screen never overwrites them with its own, possibly stale, copy.
#
# Hidden screens are NOT removed from the app — they're just left out of
# the Dashboard's button list. They stay reachable via Quick Switcher
# shortcuts (and via the "settings" route itself, always). That keeps
# hiding a screen from silently breaking any keybind someone already set
# up for it.

import copy, os, json, threading, time

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.checkbox import CheckBox
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp

import app_data
from core.jsonio import read_json, write_json_atomic
from screens.registry import SCREENS, LABELS, GROUPS, default_route_order
from core import dashboard_core as dash
from core import tool_removal
from core.daemon_ipc import send_command, daemon_launch_cmd, spawn_detached
import core.autostart as autostart

CONFIG_FILE_NAME = "app_settings.json"
# written only by the Dashboard / onboarding; save_settings keeps them as on disk
TRANSITIONS = {"fade": "Fade", "none": "Instant"}
LOADING_STYLES = {"text": "Plain text", "logo": "Logo",
                  "none": "Stay on screen"}
DASHBOARD_KEYS = ("recent", "collapsed", "pinned", "onboarded", "removed")


def _config_path():
    return os.path.join(app_data.subdir("config"), CONFIG_FILE_NAME)


_cache = {"path": None, "data": None}


def _raw_settings():
    """The saved settings, read from disk once and then kept in memory (it is
    called on every search keystroke). Writes go through _write."""
    path = _config_path()
    if _cache["path"] != path:
        data = read_json(path, {})
        _cache["path"], _cache["data"] = path, data if isinstance(data, dict) else {}
    return copy.deepcopy(_cache["data"])


def load_settings():
    data = _raw_settings()
    order  = data.get("order")  or default_route_order()
    hidden = data.get("hidden") or []
    # reconcile against the current registry: keep known routes only,
    # append anything new (e.g. a screen added since this was last saved)
    known = set(default_route_order())
    order = [r for r in order if r in known]
    for r in default_route_order():
        if r not in order:
            order.append(r)
    hidden = [r for r in hidden if r in known]
    data["order"]      = order
    data["hidden"]     = hidden
    data["lazy_load"]  = bool(data.get("lazy_load", True))
    # Background preload froze the UI while heavy screens were built, so it
    # is off by default; saved files from before that change are switched
    # off once ("preload_v2"), after which the user's own choice sticks.
    if not data.get("preload_v2"):
        data["preload_bg"] = False
        data["preload_v2"] = True
    data["preload_bg"] = bool(data.get("preload_bg", False))
    data["advanced_logging"] = bool(data.get("advanced_logging", False))
    data["show_recent"] = bool(data.get("show_recent", True))
    data["recent"], data["collapsed"] = dash.clean_state(
        data.get("recent"), data.get("collapsed"), known,
        [k for k, _t, _r in GROUPS] + [dash.OTHER_KEY])
    data["pinned"] = dash.clean_routes(data.get("pinned"), known)
    data["removed"] = tool_removal.clean(data.get("removed"), known)
    data["onboarded"] = bool(data.get("onboarded", False))
    data["rounded"] = bool(data.get("rounded", True))
    data["transition"] = data.get("transition") if data.get("transition") in TRANSITIONS else "fade"
    data["loading_style"] = data.get("loading_style") if data.get("loading_style") in LOADING_STYLES else "text"
    from core import theme as _theme
    data["theme"] = data.get("theme") if data.get("theme") in _theme.PRESETS \
        else _theme.DEFAULT_THEME
    data["custom_colors"] = _theme.clean_custom(data.get("custom_colors"))
    return data


def _write(data):
    try:
        write_json_atomic(_config_path(), data)
        _cache["path"], _cache["data"] = _config_path(), copy.deepcopy(data)
    except Exception as e:
        print(f"Settings save error: {e}")


def save_settings(data):
    """Save from the Settings screen. The Dashboard's own state ("recent",
    "collapsed") is kept as it is on disk, so a copy loaded earlier can't
    wipe what the Dashboard saved since."""
    current = load_settings()
    merged = dict(data)
    for key in DASHBOARD_KEYS:
        merged[key] = current[key]
    _write(merged)


def update_dashboard_state(recent=None, collapsed=None, pinned=None,
                           onboarded=None, removed=None):
    """Save the Dashboard's own state: recent tools, folded sections, pinned
    tools, first-run done (None = unchanged)."""
    data = load_settings()
    for key, value in (("recent", recent), ("collapsed", collapsed),
                       ("pinned", pinned), ("onboarded", onboarded),
                       ("removed", removed)):
        if value is not None:
            data[key] = value
    _write(data)


def effective_menu_order():
    """Ordered list of (route, label) for routes NOT hidden — what the
    Dashboard should render as buttons."""
    cfg = load_settings()
    hidden = set(cfg["hidden"]) | set(cfg["removed"])
    return [(r, LABELS.get(r, r)) for r in cfg["order"] if r not in hidden]


class _Row(BoxLayout):
    """One screen entry: checkbox + label, selectable/highlightable."""
    def __init__(self, route, label, visible, selected, on_select,
                 on_toggle, **kw):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(38), spacing=6, padding=(6, 0), **kw)
        self.route = route
        self._on_select = on_select

        with self.canvas.before:
            self._bg_color = Color(0.16, 0.16, 0.16, 1)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)
        self.set_selected(selected)

        cb = CheckBox(active=visible, size_hint=(None, None), size=(dp(24), dp(24)))
        cb.bind(active=lambda inst, v: on_toggle(route, v))
        self.add_widget(cb)

        self._lbl = Label(text=label, font_size=sp(13), halign="left",
                          valign="middle",
                          color=(1, 1, 1, 1) if visible else (0.5, 0.5, 0.5, 1))
        self._lbl.bind(size=self._lbl.setter("text_size"))
        self.add_widget(self._lbl)

    def _sync_bg(self, *a):
        self._bg_rect.pos  = self.pos
        self._bg_rect.size = self.size

    def set_visible_style(self, visible):
        self._lbl.color = (1, 1, 1, 1) if visible else (0.5, 0.5, 0.5, 1)

    def set_selected(self, selected):
        self._bg_color.rgba = (0.20, 0.36, 0.55, 1) if selected else (0.16, 0.16, 0.16, 1)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._on_select(self.route)
        return super().on_touch_down(touch)


def _fmt_uptime(seconds):
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


class SettingsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._cfg = load_settings()
        self._selected = None   # currently selected route, for reordering
        self._rows = {}

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        root.add_widget(Label(text="[b]Settings[/b]", markup=True,
                              font_size=sp(20), size_hint_y=None, height=dp(32)))

        # Everything between the title and the Back button scrolls: on a phone
        # the settings are taller than the screen, and the screen list used to
        # be squeezed to nothing. The list keeps its own fixed-height scroll.
        scroll = ScrollView(do_scroll_x=False)
        content = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        root.add_widget(scroll)

        from core import theme as _theme
        from kivy.utils import platform as _p_

        # ── small builders: text that wraps, rows that grow with it ───────
        def head(text, note=""):
            box = BoxLayout(orientation="vertical", size_hint_y=None,
                            height=dp(54 if note else 40), padding=(0, dp(14), 0, 0))
            h = Label(text=f"[b]{text}[/b]", markup=True, font_size=sp(16),
                      halign="left", valign="middle", color=_theme.ACCENT,
                      size_hint_y=None, height=dp(24))
            h.bind(size=lambda w, v: setattr(w, "text_size", v))
            box.add_widget(h)
            if note:
                n = Label(text=note, font_size=sp(11), halign="left",
                          valign="top", color=_theme.MUTED,
                          size_hint_y=None, height=dp(16))
                n.bind(size=lambda w, v: setattr(w, "text_size", v))
                box.add_widget(n)
            content.add_widget(box)

        def wrapped(text, size=12, color=None):
            lbl = Label(text=text, font_size=sp(size), halign="left",
                        valign="middle", size_hint_y=None,
                        color=color or _theme.TEXT)
            lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                     texture_size=lambda w, v: setattr(w, "height", v[1] + dp(6)))
            return lbl

        def check(text, active, handler):
            row = BoxLayout(size_hint_y=None, spacing=dp(10))
            cb = CheckBox(active=active, size_hint=(None, None),
                          size=(dp(28), dp(28)), pos_hint={"center_y": 0.5})
            cb.bind(active=handler)
            lbl = wrapped(text)
            row.add_widget(cb)
            row.add_widget(lbl)
            lbl.bind(height=lambda w, v: setattr(row, "height", max(dp(44), v + dp(8))))
            row.height = dp(44)
            content.add_widget(row)
            return cb

        def choice(title, options, handler, store, key):
            content.add_widget(wrapped(title, 13))
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            for okey, olabel in options:
                b = Button(text=olabel, font_size=sp(12))
                b.bind(on_release=lambda inst, v=okey: handler(v))
                store[okey if key is None else key + (okey,)] = b
                row.add_widget(b)
            content.add_widget(row)

        def action(text, handler, height=42, **kw):
            b = Button(text=text, size_hint_y=None, height=dp(height),
                       font_size=sp(13), **kw)
            b.bind(on_release=handler)
            content.add_widget(b)
            return b

        # ══ Appearance ═══════════════════════════════════════════════════
        head("Appearance", "Changes here apply after you restart Srboli.")
        self._theme_btns = {}
        choice("Theme", [(k, p["label"]) for k, p in _theme.PRESETS.items()],
               self._set_theme, self._theme_btns, None)
        content.add_widget(wrapped("Custom colours (#rrggbb)", 13))
        self._custom_in, self._custom_sw = {}, {}
        saved = self._cfg.get("custom_colors") or {}
        base = _theme.PRESETS["custom"]
        for key, label in _theme.CUSTOM_FIELDS:
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
            row.add_widget(wrapped(label, 12))
            ti = TextInput(text=saved.get(key) or _theme.to_hex(base[key]), multiline=False,
                           font_size=sp(13), size_hint_x=None, width=dp(110))
            sw = Widget(size_hint_x=None, width=dp(40))
            self._custom_in[key], self._custom_sw[key] = ti, sw
            sw.bind(pos=self._swatch_move, size=self._swatch_move)
            ti.bind(text=lambda *_a: self._custom_preview())
            row.add_widget(ti)
            row.add_widget(sw)
            content.add_widget(row)
        self._custom_msg = wrapped("", 11, _theme.MUTED)
        content.add_widget(self._custom_msg)
        action("Use these colours", lambda *a: self._use_custom(), 40)
        self._custom_preview()
        self._rnd_cb = check("Rounded buttons", self._cfg.get("rounded", True),
                             self._toggle_rounded)
        self._pick_btns = {}
        choice("Moving between screens", list(TRANSITIONS.items()),
               lambda v: self._set_pick("transition", v), self._pick_btns,
               ("transition",))
        choice("While a tool is loading", list(LOADING_STYLES.items()),
               lambda v: self._set_pick("loading_style", v), self._pick_btns,
               ("loading_style",))
        self._mark_theme()
        self._mark_picks()

        # ══ Dashboard ════════════════════════════════════════════════════
        head("Dashboard", "Order, hide or remove the tools on the home screen.")
        self._rec_cb = check("Show a \"Recent\" row (the tools you opened last)",
                             self._cfg.get("show_recent", True),
                             self._toggle_recent)
        content.add_widget(wrapped(
            "Tap a tool to select it, then move it up or down inside its "
            "section. Hidden tools stay reachable through Quick Switcher.",
            11, _theme.MUTED))
        move_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        up_btn = Button(text="Move up", font_size=sp(12))
        down_btn = Button(text="Move down", font_size=sp(12))
        up_btn.bind(on_release=lambda *a: self._move_selected(-1))
        down_btn.bind(on_release=lambda *a: self._move_selected(1))
        move_row.add_widget(up_btn)
        move_row.add_widget(down_btn)
        content.add_widget(move_row)
        sv = ScrollView(size_hint_y=None, height=dp(300))
        self._grid = GridLayout(cols=1, spacing=2, size_hint_y=None, padding=(0, 4))
        self._grid.bind(minimum_height=self._grid.setter("height"))
        sv.add_widget(self._grid)
        content.add_widget(sv)
        action("Reset screen list to defaults", self._reset_defaults, 38,
               background_color=(0.45, 0.3, 0.1, 1))
        action("Remove or restore tools permanently...",
               lambda *a: setattr(self.manager, "current", "manage_tools"), 40)

        # ══ Speed and start-up ═══════════════════════════════════════════
        head("Speed and start-up", "Both apply after you restart Srboli.")
        self._lazy_cb = check(
            "Open tools on demand (faster start). Turn off to build every "
            "tool at start-up: slower start, faster opening.",
            self._cfg.get("lazy_load", True), self._toggle_lazy)
        self._pre_cb = check(
            "Prepare tools in the background after start-up, only while you "
            "are not touching the app. May stutter on slow phones. Needs "
            "\"on demand\" on.",
            self._cfg.get("preload_bg", False), self._toggle_preload)

        # ══ Data, permissions and notifications ══════════════════════════
        head("Your data and permissions")
        from screens.data_location import DataLocation
        content.add_widget(DataLocation())
        from core.android_storage import ON_ANDROID
        self._perm_block = None
        if ON_ANDROID:
            from screens.permissions_block import PermissionsBlock
            self._perm_block = PermissionsBlock()
            content.add_widget(self._perm_block)

        # ══ AI ═══════════════════════════════════════════════════════════
        head("AI (optional)", "Off by default. Nothing is sent anywhere until you turn it on.")
        from screens.ai_settings import AISettings
        self._ai_settings = AISettings()
        content.add_widget(self._ai_settings)

        # ══ Background service ═══════════════════════════════════════════
        head("Background service")
        content.add_widget(wrapped(
            "A small process that can run reminders, watch folders, and "
            "answer hotkeys even when Srboli's window is closed. Off by "
            "default: nothing runs in the background unless you start it here.",
            11, _theme.MUTED))
        svc_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
        self._daemon_status_lbl = Label(text="Checking...", font_size=sp(12),
                                        halign="left", valign="middle")
        self._daemon_status_lbl.bind(
            size=self._daemon_status_lbl.setter("text_size"))
        svc_row.add_widget(self._daemon_status_lbl)
        self._daemon_refresh_btn = Button(text="Refresh", size_hint_x=None,
                                          width=dp(72), font_size=sp(11))
        self._daemon_start_btn = Button(text="Start", size_hint_x=None,
                                        width=dp(72), font_size=sp(12),
                                        background_color=(0.2, 0.55, 0.2, 1))
        self._daemon_stop_btn = Button(text="Stop", size_hint_x=None,
                                       width=dp(72), font_size=sp(12),
                                       background_color=(0.55, 0.2, 0.2, 1))
        self._daemon_refresh_btn.bind(
            on_release=lambda *a: self._refresh_daemon_status())
        self._daemon_start_btn.bind(on_release=self._start_daemon)
        self._daemon_stop_btn.bind(on_release=self._stop_daemon)
        svc_row.add_widget(self._daemon_refresh_btn)
        svc_row.add_widget(self._daemon_start_btn)
        svc_row.add_widget(self._daemon_stop_btn)
        content.add_widget(svc_row)
        if autostart.is_supported():
            self._autostart_cb = check(
                "Start the background service automatically when I log in",
                False, self._toggle_autostart)
        else:
            self._autostart_cb = None
        feat_btn = action("Choose what the service may run...",
                          self._open_service_features, 40)
        if _p_ == "android":
            feat_btn.disabled = True
            feat_btn.text = "Background service: desktop only (not on Android yet)"

        # ══ Help and diagnostics ═════════════════════════════════════════
        head("Help and diagnostics")
        from screens.feedback_popup import open_feedback
        action("Leave feedback", open_feedback, 42)
        action("Touch Test (are my taps arriving twice?)",
               self._open_touch_test, 42)
        self._adv_cb = check(
            "Advanced logging: write what the app receives (touches, clicks, "
            "keys; typed letters are not recorded) and what it does to a log "
            "file. Applies immediately.",
            self._cfg.get("advanced_logging", False), self._toggle_adv_log)
        action("Reset all settings to defaults...", self._ask_reset_all, 40,
               background_color=(0.45, 0.3, 0.1, 1))
        from core.version import VERSION as _V
        content.add_widget(wrapped(f"Srboli v{_V}", 11, _theme.MUTED))

        self._status = Label(text="", size_hint_y=None, height=dp(22),
                             font_size=sp(11), color=(0.4, 1, 0.4, 1))
        root.add_widget(self._status)

        back = Button(text="Back", size_hint_y=None, height=dp(42))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "dashboard"))
        root.add_widget(back)

        self.add_widget(root)
        self._refresh_list()

    # ── list rendering ───────────────────────────────────────────────────
    def _refresh_list(self):
        self._grid.clear_widgets()
        self._rows = {}
        hidden = set(self._cfg["hidden"])
        gone = set(self._cfg.get("removed", []))
        menu = [(r, LABELS.get(r, r)) for r in self._cfg["order"] if r not in gone]
        for _key, title, members in dash.group_menu(menu, GROUPS):
            head = Label(text=f"[b]{title}[/b]", markup=True, font_size=sp(12),
                         halign="left", size_hint_y=None, height=dp(26),
                         color=(0.55, 0.8, 1, 1))
            head.bind(size=head.setter("text_size"))
            self._grid.add_widget(head)
            for route, label in members:
                row = _Row(route, label, visible=(route not in hidden),
                           selected=(route == self._selected),
                           on_select=self._select, on_toggle=self._toggle_visible)
                self._rows[route] = row
                self._grid.add_widget(row)

    def _select(self, route):
        self._selected = route
        for r, row in self._rows.items():
            row.set_selected(r == route)

    def _toggle_visible(self, route, active):
        hidden = set(self._cfg["hidden"])
        if active:
            hidden.discard(route)
        else:
            hidden.add(route)
        self._cfg["hidden"] = list(hidden)
        save_settings(self._cfg)
        if route in self._rows:
            self._rows[route].set_visible_style(active)
        self._status.text = f"{'Shown' if active else 'Hidden'}: {LABELS.get(route, route)}"

    def _move_selected(self, direction):
        if self._selected is None:
            self._status.text = "Select a screen first (click a row)."
            return
        order = self._cfg["order"]
        menu = [(r, LABELS.get(r, r)) for r in order]
        # the Dashboard shows each section in the user's order, so a move
        # means: swap with the neighbouring screen of the SAME section
        section = next(([r for r, _l in members]
                        for _k, _t, members in dash.group_menu(menu, GROUPS)
                        if self._selected in dict(members)), [self._selected])
        k = section.index(self._selected) + direction
        if not 0 <= k < len(section):
            return
        i, j = order.index(self._selected), order.index(section[k])
        order[i], order[j] = order[j], order[i]
        self._cfg["order"] = order
        save_settings(self._cfg)
        self._refresh_list()
        self._status.text = f"Moved: {LABELS.get(self._selected, self._selected)}"

    def _reset_defaults(self, *a):
        self._cfg["order"]  = default_route_order()
        self._cfg["hidden"] = []
        self._selected = None
        save_settings(self._cfg)
        self._refresh_list()
        self._status.text = "Screen list reset to defaults."

    def _toggle_lazy(self, inst, active):
        self._cfg["lazy_load"] = active
        save_settings(self._cfg)
        self._status.text = ("Lazy loading ON — restart Srboli to apply."
                             if active else
                             "Lazy loading OFF — restart Srboli to apply.")

    def _mark_theme(self):
        from core import theme as _theme
        for key, b in self._theme_btns.items():
            b.text = _theme.PRESETS[key]["label"]
            b.background_color = (_theme.ACCENT if key == self._cfg.get("theme")
                                  else _theme.SURFACE2)

    def _custom_values(self):
        return {k: ti.text for k, ti in self._custom_in.items()}

    def _custom_preview(self):
        """Colour swatches next to the fields, and a warning for unreadable text."""
        from core import theme as _theme
        cols = {k: _theme.parse_hex(ti.text) for k, ti in self._custom_in.items()}
        for sw in self._custom_sw.values():
            self._swatch_move(sw)
        bad = [lab for k, lab in _theme.CUSTOM_FIELDS if cols[k] is None]
        if bad:
            self._custom_msg.text = "Not a colour: " + ", ".join(bad) + " (use #rrggbb)."
        elif min(_theme.contrast(cols["TEXT"], cols["BG"]),
                 _theme.contrast(cols["TEXT"], cols["SURFACE2"])) < 3:
            self._custom_msg.text = ("Text is hard to read on those backgrounds - "
                                     "pick a lighter or darker text colour.")
        else:
            self._custom_msg.text = "Looks fine. Saved colours apply after you restart Srboli."

    def _swatch_move(self, sw, *a):
        from core import theme as _theme
        from kivy.graphics import Color, Rectangle
        key = next((k for k, w in self._custom_sw.items() if w is sw), None)
        c = _theme.parse_hex(self._custom_in[key].text) if key else None
        sw.canvas.clear()
        with sw.canvas:
            Color(*(c or (0.5, 0.1, 0.1, 1)))
            Rectangle(pos=sw.pos, size=sw.size)

    def _use_custom(self):
        from core import theme as _theme
        vals = self._custom_values()
        if any(_theme.parse_hex(v) is None for v in vals.values()):
            self._status.text = "Fix the colours first (use #rrggbb)."
            return False
        self._cfg["custom_colors"] = _theme.clean_custom(vals)
        self._cfg["theme"] = "custom"
        save_settings(self._cfg)
        self._mark_theme()
        self._status.text = "Custom colours saved - restart Srboli to apply."
        return True

    def _set_theme(self, key):
        self._cfg["theme"] = key
        save_settings(self._cfg)
        self._mark_theme()
        self._status.text = "Theme saved - restart Srboli to apply."

    def _ask_reset_all(self, *a):
        lay = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        lay.add_widget(Label(text="Reset every setting to its default?\n"
                                  "Your files and data are not touched.",
                             font_size=sp(13)))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        pop = Popup(title="Reset settings", content=lay, size_hint=(0.85, None),
                    height=dp(200))
        no = Button(text="Cancel")
        no.bind(on_release=lambda *x: pop.dismiss())
        yes = Button(text="Reset")
        yes.bind(on_release=lambda *x: (pop.dismiss(), self._reset_all()))
        row.add_widget(no)
        row.add_widget(yes)
        lay.add_widget(row)
        pop.open()

    def _reset_all(self):
        _write({})
        self._status.text = "All settings reset - restart Srboli."

    def _mark_picks(self):
        names = {"transition": TRANSITIONS, "loading_style": LOADING_STYLES}
        from core import theme as _theme
        for (key, okey), b in self._pick_btns.items():
            b.text = names[key][okey]
            b.background_color = (_theme.ACCENT if self._cfg.get(key) == okey
                                  else _theme.SURFACE2)

    def _set_pick(self, key, value):
        self._cfg[key] = value
        save_settings(self._cfg)
        self._mark_picks()
        self._status.text = "Saved - restart Srboli to apply."

    def _toggle_rounded(self, inst, active):
        self._cfg["rounded"] = active
        save_settings(self._cfg)
        self._status.text = "Rounded buttons " + ("on" if active else "off") \
            + " - restart Srboli to apply."

    def _toggle_recent(self, inst, active):
        self._cfg["show_recent"] = active
        save_settings(self._cfg)
        self._status.text = ("The Recent row is shown on the Dashboard." if active
                             else "The Recent row is hidden.")

    def _toggle_adv_log(self, inst, active):
        self._cfg["advanced_logging"] = active
        save_settings(self._cfg)
        try:
            import core.advlog as advlog
            advlog.set_enabled(active)
            where = advlog.log_path() or "(no writable folder)"
        except Exception as e:
            where = f"(failed: {e})"
        self._status.text = ("Advanced logging ON: " + where if active
                             else "Advanced logging OFF.")

    def _toggle_preload(self, inst, active):
        self._cfg["preload_bg"] = active
        save_settings(self._cfg)
        self._status.text = ("Background preload ON — restart Srboli to apply."
                             if active else
                             "Background preload OFF — restart Srboli to apply.")

    # ── keyboard reorder (Up/Down while this screen is active) ─────────────
    def on_enter(self, *a):
        self._cfg = load_settings()     # the Dashboard / first-run setup may have changed it
        self._refresh_list()
        if getattr(self, "_perm_block", None) is not None:
            self._perm_block.refresh()      # the user may have just allowed something
        Window.bind(on_key_down=self._on_key)
        self._refresh_daemon_status()
        if self._autostart_cb is not None:
            self._autostart_syncing = True
            self._autostart_cb.active = autostart.is_enabled()
            self._autostart_syncing = False

    def on_leave(self, *a):
        Window.unbind(on_key_down=self._on_key)

    # ── background service ──────────────────────────────────────────────
    def _refresh_daemon_status(self):
        self._daemon_status_lbl.text = "Checking..."
        self._daemon_status_lbl.color = (0.7, 0.7, 0.7, 1)

        def worker():
            resp = send_command("status", timeout=1.5)
            Clock.schedule_once(lambda dt: self._apply_daemon_status(resp))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_daemon_status(self, resp):
        from kivy.utils import platform as _plat
        if _plat == "android":
            # The detached-process daemon is a desktop feature (Android has
            # no way to spawn it this way). Reminders are checked from inside
            # the app instead.
            self._daemon_status_lbl.text = ("Desktop only - on Android, "
                                            "reminders fire while Srboli is open")
            self._daemon_status_lbl.color = (0.75, 0.75, 0.75, 1)
            self._daemon_start_btn.disabled = True
            self._daemon_stop_btn.disabled = True
            self._daemon_refresh_btn.disabled = True
            return
        if resp and resp.get("ok"):
            uptime = _fmt_uptime(resp.get("uptime", 0))
            self._daemon_status_lbl.text = f"Running  (pid {resp.get('pid')}, up {uptime})"
            self._daemon_status_lbl.color = (0.45, 0.85, 0.45, 1)
            self._daemon_start_btn.disabled = True
            self._daemon_stop_btn.disabled = False
        else:
            self._daemon_status_lbl.text = "Not running"
            self._daemon_status_lbl.color = (0.75, 0.75, 0.75, 1)
            self._daemon_start_btn.disabled = False
            self._daemon_stop_btn.disabled = True

    def _start_daemon(self, *a):
        self._daemon_start_btn.disabled = True
        self._daemon_status_lbl.text = "Starting..."
        self._daemon_status_lbl.color = (0.7, 0.7, 0.7, 1)

        def worker():
            try:
                spawn_detached(daemon_launch_cmd())
            except Exception as e:
                msg = str(e)
                def fail(dt, msg=msg):
                    self._daemon_status_lbl.text = f"Couldn't start: {msg}"
                    self._daemon_start_btn.disabled = False
                Clock.schedule_once(fail)
                return
            # give the new process a moment to bind its socket, then
            # confirm over IPC rather than just trusting Popen succeeded
            resp = None
            for _ in range(10):
                time.sleep(0.3)
                resp = send_command("ping", timeout=1.0)
                if resp:
                    break
            Clock.schedule_once(lambda dt: self._apply_daemon_status(resp))
        threading.Thread(target=worker, daemon=True).start()

    def _stop_daemon(self, *a):
        self._daemon_stop_btn.disabled = True
        self._daemon_status_lbl.text = "Stopping..."
        self._daemon_status_lbl.color = (0.7, 0.7, 0.7, 1)

        def worker():
            send_command("stop", timeout=1.5)
            resp = None
            for _ in range(10):
                time.sleep(0.2)
                resp = send_command("ping", timeout=0.5)
                if resp is None:
                    break
            Clock.schedule_once(lambda dt: self._apply_daemon_status(resp))
        threading.Thread(target=worker, daemon=True).start()

    def _open_touch_test(self, *a):
        if not self.manager.has_screen("touch_test"):
            from screens.touch_test_screen import TouchTestScreen
            self.manager.add_widget(TouchTestScreen(name="touch_test"))
        self.manager.current = "touch_test"

    def _open_service_features(self, *a):
        import core.service_config as svc_cfg
        allow = svc_cfg.load()
        layout = BoxLayout(orientation="vertical", padding=dp(10),
                           spacing=dp(8))
        intro = Label(
            text=("The service is a separate process: closing Srboli does "
                  "NOT stop it. Stop it with the Stop button in Settings, "
                  "or it ends when the computer shuts down (unless 'start "
                  "when I log in' is ticked). It is off until you start it.\n\n"
                  "Pick what a running service is allowed to do:"),
            font_size=sp(12), halign="left", valign="top",
            size_hint_y=None, height=dp(120))
        intro.bind(size=lambda i, sz: setattr(i, "text_size", (sz[0], None)))
        layout.add_widget(intro)
        boxes = {}
        for key, (title, desc) in svc_cfg.FEATURES.items():
            row = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(8))
            cb = CheckBox(active=allow.get(key, True), size_hint=(None, None),
                          size=(dp(32), dp(32)))
            boxes[key] = cb
            col = Label(text=f"[b]{title}[/b]\n{desc}", markup=True,
                        font_size=sp(12), halign="left", valign="middle")
            col.bind(size=lambda i, sz: setattr(i, "text_size", (sz[0], None)))
            row.add_widget(cb)
            row.add_widget(col)
            layout.add_widget(row)
        layout.add_widget(Label())
        save_b = Button(text="Save", size_hint_y=None, height=dp(46))
        layout.add_widget(save_b)
        popup = Popup(title="Background service features", content=layout,
                      size_hint=(0.94, 0.8))

        def _save(*_):
            ok = svc_cfg.save({k: c.active for k, c in boxes.items()})
            popup.dismiss()
            self._status.text = ("Saved." if ok else "Couldn't save.")
            threading.Thread(
                target=lambda: send_command("reload", timeout=1.0),
                daemon=True).start()
        save_b.bind(on_release=_save)
        popup.open()

    def _toggle_autostart(self, checkbox, active):
        if getattr(self, "_autostart_syncing", False):
            return          # programmatic set from on_enter, not a user click
        if active:
            ok, err = autostart.enable(daemon_launch_cmd())
        else:
            ok, err = autostart.disable()
        if not ok:
            self._autostart_syncing = True
            checkbox.active = not active     # revert the visual toggle
            self._autostart_syncing = False
            self._status.text = f"Couldn't update autostart: {err}"

    def _on_key(self, window, key, scancode, codepoint, modifiers):
        if key == 273:      # Up arrow
            self._move_selected(-1)
            return True
        if key == 274:      # Down arrow
            self._move_selected(1)
            return True
        return False
