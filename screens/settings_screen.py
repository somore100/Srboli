# screens/settings_screen.py
# Settings — manage which screens show up on the Dashboard and in what
# order, plus a few app-wide behaviour toggles (currently: lazy loading).
#
# Persisted to <data_dir>/config/app_settings.json:
#   {
#     "order":      [route, route, ...],   # dashboard menu order
#     "hidden":     [route, route, ...],   # routes hidden from the menu
#     "lazy_load":  bool                   # build screens on first visit (default True)
#   }
#
# Hidden screens are NOT removed from the app — they're just left out of
# the Dashboard's button list. They stay reachable via Quick Switcher
# shortcuts (and via the "settings" route itself, always). That keeps
# hiding a screen from silently breaking any keybind someone already set
# up for it.

import os, json, threading, time

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.checkbox import CheckBox
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp

import app_data
from screens.registry import SCREENS, LABELS, default_route_order
from core.daemon_ipc import send_command, daemon_launch_cmd, spawn_detached
import core.autostart as autostart

CONFIG_FILE_NAME = "app_settings.json"


def _config_path():
    return os.path.join(app_data.subdir("config"), CONFIG_FILE_NAME)


def load_settings():
    try:
        with open(_config_path(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
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
    data["preload_bg"] = bool(data.get("preload_bg", True))
    return data


def save_settings(data):
    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Settings save error: {e}")


def effective_menu_order():
    """Ordered list of (route, label) for routes NOT hidden — what the
    Dashboard should render as buttons."""
    cfg = load_settings()
    hidden = set(cfg["hidden"])
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

        self._lbl = Label(text=label, font_size=13, halign="left",
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
                              font_size=20, size_hint_y=None, height=dp(32)))

        root.add_widget(Label(
            text="Reorder or hide screens on the Dashboard. Click a row to "
                 "select it, then use the arrows (or Up/Down keys) to move "
                 "it. Hidden screens stay reachable via Quick Switcher.",
            font_size=11, halign="left", size_hint_y=None, height=dp(48),
            color=(0.7, 0.7, 0.7, 1)))
        root.children[-1].bind(size=root.children[-1].setter("text_size"))

        # ── reorder controls ────────────────────────────────────────────
        move_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=6)
        up_btn = Button(text="\u25b2 Move Up", font_size=12)
        down_btn = Button(text="\u25bc Move Down", font_size=12)
        up_btn.bind(on_release=lambda *a: self._move_selected(-1))
        down_btn.bind(on_release=lambda *a: self._move_selected(1))
        move_row.add_widget(up_btn)
        move_row.add_widget(down_btn)
        root.add_widget(move_row)

        # ── screen list ──────────────────────────────────────────────────
        sv = ScrollView()
        self._grid = GridLayout(cols=1, spacing=2, size_hint_y=None, padding=(0, 4))
        self._grid.bind(minimum_height=self._grid.setter("height"))
        sv.add_widget(self._grid)
        root.add_widget(sv)

        reset_btn = Button(text="Reset screen list to defaults",
                           size_hint_y=None, height=dp(38), font_size=12,
                           background_color=(0.45, 0.3, 0.1, 1))
        reset_btn.bind(on_release=self._reset_defaults)
        root.add_widget(reset_btn)

        # ── other settings ──────────────────────────────────────────────
        root.add_widget(Label(text="[b]Other settings[/b]", markup=True,
                              font_size=15, size_hint_y=None, height=dp(26)))

        lazy_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        self._lazy_cb = CheckBox(active=self._cfg.get("lazy_load", True),
                                 size_hint=(None, None), size=(dp(24), dp(24)))
        self._lazy_cb.bind(active=self._toggle_lazy)
        lazy_row.add_widget(self._lazy_cb)
        lazy_lbl = Label(
            text="Lazy-load screens (build each screen only when you first "
                 "open it, instead of all at startup) - on by default now, "
                 "for a faster launch. Takes effect after restarting Srboli.",
            font_size=11, halign="left", valign="middle")
        lazy_lbl.bind(size=lazy_lbl.setter("text_size"))
        lazy_row.add_widget(lazy_lbl)
        root.add_widget(lazy_row)

        pre_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        self._pre_cb = CheckBox(active=self._cfg.get("preload_bg", True),
                                size_hint=(None, None), size=(dp(24), dp(24)))
        self._pre_cb.bind(active=self._toggle_preload)
        pre_row.add_widget(self._pre_cb)
        pre_lbl = Label(
            text="Preload screens in the background (show the dashboard "
                 "first, then build the other screens one by one while "
                 "idle). Needs lazy-loading on. Applies after a restart.",
            font_size=11, halign="left", valign="middle")
        pre_lbl.bind(size=pre_lbl.setter("text_size"))
        pre_row.add_widget(pre_lbl)
        root.add_widget(pre_row)

        # ── background service ──────────────────────────────────────────
        root.add_widget(Label(text="[b]Background service[/b]", markup=True,
                              font_size=15, size_hint_y=None, height=dp(26)))
        svc_desc = Label(
            text="A small process that can run reminders, watch folders, "
                 "and answer hotkeys even when Srboli's window is closed. "
                 "Off by default — nothing runs in the background unless "
                 "you start it here.",
            font_size=11, halign="left", valign="top",
            size_hint_y=None, height=dp(46), color=(0.7, 0.7, 0.7, 1))
        svc_desc.bind(size=svc_desc.setter("text_size"))
        root.add_widget(svc_desc)

        svc_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
        self._daemon_status_lbl = Label(text="Checking...", font_size=12,
                                        halign="left", valign="middle")
        self._daemon_status_lbl.bind(
            size=self._daemon_status_lbl.setter("text_size"))
        svc_row.add_widget(self._daemon_status_lbl)
        self._daemon_refresh_btn = Button(text="Refresh", size_hint_x=None,
                                          width=dp(72), font_size=11)
        self._daemon_start_btn = Button(text="Start", size_hint_x=None,
                                        width=dp(72), font_size=12,
                                        background_color=(0.2, 0.55, 0.2, 1))
        self._daemon_stop_btn = Button(text="Stop", size_hint_x=None,
                                       width=dp(72), font_size=12,
                                       background_color=(0.55, 0.2, 0.2, 1))
        self._daemon_refresh_btn.bind(
            on_release=lambda *a: self._refresh_daemon_status())
        self._daemon_start_btn.bind(on_release=self._start_daemon)
        self._daemon_stop_btn.bind(on_release=self._stop_daemon)
        svc_row.add_widget(self._daemon_refresh_btn)
        svc_row.add_widget(self._daemon_start_btn)
        svc_row.add_widget(self._daemon_stop_btn)
        root.add_widget(svc_row)

        if autostart.is_supported():
            auto_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
            self._autostart_cb = CheckBox(size_hint=(None, None),
                                          size=(dp(26), dp(26)))
            self._autostart_cb.bind(active=self._toggle_autostart)
            auto_row.add_widget(self._autostart_cb)
            auto_lbl = Label(
                text="Start the background service automatically when I log in",
                font_size=12, halign="left", valign="middle")
            auto_lbl.bind(size=auto_lbl.setter("text_size"))
            auto_row.add_widget(auto_lbl)
            root.add_widget(auto_row)
        else:
            self._autostart_cb = None

        self._status = Label(text="", size_hint_y=None, height=dp(22),
                             font_size=11, color=(0.4, 1, 0.4, 1))
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
        for route in self._cfg["order"]:
            label = LABELS.get(route, route)
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
        i = order.index(self._selected)
        j = i + direction
        if j < 0 or j >= len(order):
            return
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

    def _toggle_preload(self, inst, active):
        self._cfg["preload_bg"] = active
        save_settings(self._cfg)
        self._status.text = ("Background preload ON — restart Srboli to apply."
                             if active else
                             "Background preload OFF — restart Srboli to apply.")

    # ── keyboard reorder (Up/Down while this screen is active) ─────────────
    def on_enter(self, *a):
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
