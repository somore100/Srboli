# main.py — Srboli (version: core/version.py)
import sys, os
# Helper modes (--cover, --cover-cmd, --daemon, --overlay) must not touch Kivy
# before their own dispatch below: Kivy parses sys.argv on import and aborts
# on flags it doesn't know. The boot log imports Kivy indirectly, so it only
# runs for a normal app start.
_HELPER_MODE = len(sys.argv) > 1 and sys.argv[1] in (
    "--cover", "--cover-cmd", "--daemon", "--overlay", "--selftest")
try:
    if _HELPER_MODE:
        raise ImportError("helper mode: no boot log")
    import core.bootlog as _bl
    _bl.log('main.py imported')
except Exception:
    _bl = None
try:
    from core.version import VERSION as _APP_VERSION
except Exception:
    _APP_VERSION = "?"

app_dir = os.path.dirname(os.path.abspath(__file__))
for p in (app_dir, os.path.join(app_dir, "_internal")):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# ── selftest dispatch ────────────────────────────────────────────────────────
# `main.py --selftest [outfile]` imports every registered screen and exits 0/1
# (CI runs it against the built exe/AppImage: a module PyInstaller left out
# shows up here instead of as a "not available" screen on a user's machine).
if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
    from core.selftest import run as _selftest_run
    sys.exit(_selftest_run(sys.argv[2] if len(sys.argv) > 2 else None))

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

# ── cover dispatch ───────────────────────────────────────────────────────────
# `--cover` is the privacy-box / blackout process (tkinter, not Kivy — it
# needs several frameless windows). `--cover-cmd <cmd>` sends one command to
# it (toggle, blackout, ...) and exits; handy as a system keyboard shortcut
# on Wayland where apps cannot register global hotkeys. Neither path may
# import Kivy.
if len(sys.argv) > 1 and sys.argv[1] == "--cover":
    import core.cover_app
    sys.exit(core.cover_app.run())
if len(sys.argv) > 1 and sys.argv[1] == "--cover-cmd":
    import core.cover_app
    sys.exit(core.cover_app.run_cmd(sys.argv[2:]))

# ── daemon dispatch ──────────────────────────────────────────────────────────
# Unlike --overlay above, this path never touches Kivy at all — core/daemon.py
# and everything it imports is plain stdlib + app_data. It must stay that way:
# the whole point of the daemon is to run with no window and no Kivy import,
# so it can sit in the background without a GPU context or a display.
if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
    import core.daemon
    sys.exit(core.daemon.run())

from kivy.config import Config
# disable_on_activity: Android's SDL feeds every tap twice (a real finger touch
# AND a synthesised mouse touch, 1-4 ms apart; see Touch Test). Kivy's own
# fix is to make the mouse provider ignore itself while a finger touch is
# active, so the ghost never reaches any widget. (Real mouse input, e.g.
# Samsung DeX, still works: no finger touch is active then.)
_ON_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_STORAGE" in os.environ
if _ON_ANDROID:
    Config.set("input", "mouse", "mouse,disable_multitouch,disable_on_activity")
else:
    # Desktop: SDL already delivers real touchscreens, and has no ghost taps.
    # With disable_on_activity the mouse is ignored while ANY touch is
    # "active", and Kivy's raw /dev/input reader (the [MTD] lines in the log)
    # can leave one stuck (touchpad / touchscreen), which froze all clicks.
    Config.set("input", "mouse", "mouse,disable_multitouch")
    try:
        Config.remove_option("input", "hid_%(name)s")
    except Exception:
        pass
Config.set("kivy", "exit_on_escape", "0")
try:
    from core import window_state as _ws
    _ws.restore(Config, _ON_ANDROID)        # desktop: last size / position
except Exception as _e:
    print(f"window state skipped: {_e}")

from kivy.core.window import Window
# Fixes a Kivy/Android interaction bug: when a TextInput has focus and the
# on-screen keyboard is up, tapping a Spinner (e.g. Script Mode's "Split
# by:") first dismisses the keyboard. The window resize that follows can
# get read as a "touch outside" by the DropDown that just opened, closing
# it before you can pick anything. "below_target" keeps the window from
# resizing under the focused widget, which avoids that resize-triggered
# dismiss. See screens/script_mode_screen.py for the matching defocus fix.
# (softinput_mode left at Kivy default - see global Spinner fix below)

from kivy.utils import platform as _platform
if _platform == "android":
    from core import kivy_patches as _kp
    _kp.apply_android(Window, _bl)

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
from kivy.uix.textinput import TextInput
# Every folder/file picker gets a type-or-paste path bar (core/pathbar.py).
# Must run BEFORE any screen module imports FileChooserIconView.
try:
    import core.pathbar
    core.pathbar.install()
except Exception as _e:
    print(f"pathbar install skipped: {_e}")
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.metrics import dp, sp

import app_data
from core import theme
theme.install()


def try_import(module_path, class_name):
    try:
        import importlib
        cls = getattr(importlib.import_module(module_path), class_name)
        print(f"OK  {class_name}")
        return cls
    except Exception as exc:
        msg = str(exc)
        if isinstance(exc, ModuleNotFoundError) and exc.name:
            pkg = {"PIL": "Pillow", "cv2": "opencv-python",
                   "yaml": "PyYAML"}.get(exc.name.split(".")[0],
                                         exc.name.split(".")[0])
            msg = (f"Needs the '{exc.name}' module.\n"
                   f"Install it with:  pip install {pkg}")
        print(f"!!  {class_name}: {msg}")
        class Placeholder(Screen):
            def __init__(self, **kw):
                super().__init__(**kw)
                b = BoxLayout(orientation="vertical", padding=20, spacing=10)
                b.add_widget(Label(
                    text=f"[b]{class_name}[/b]\nnot available\n\n{msg}",
                    markup=True, font_size=sp(13), halign="center"))
                btn = Button(text="Back", size_hint_y=None, height=dp(48))
                btn.bind(on_release=lambda *a: setattr(
                    self.manager, "current", "dashboard"))
                b.add_widget(btn)
                self.add_widget(b)
        return Placeholder


from screens.registry import SCREENS, LABELS, GROUPS
from screens.dashboard_screen import Dashboard
from core.navigation import GuardedScreenManager, open_screen, install_keys
from core import permissions
from screens.settings_screen import (load_settings, effective_menu_order,
                                     update_dashboard_state)

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
            import time as _t
            _t0 = _t.monotonic()
            sm.add_widget(try_import(mod, cls_name)(name=route))
            try:
                import core.advlog as _al
                _al.did(f"built screen {route} in {_t.monotonic() - _t0:.2f}s",
                        "build")
            except Exception:
                pass
            return True
    return False


class SrboliApp(App):
    _asked_permissions = set()

    def _open_route(self, route):
        """Open a tool: 'Loading...' first if it must be built, then ask for
        the Android permission it needs (in context, once)."""
        open_screen(self.root, route,
                    lambda r: ensure_screen_loaded(self.root, r),
                    after=self._ask_permission)

    def _ask_permission(self, route):
        try:
            from core import android_storage as _as
            kind = permissions.needed(
                route, _ON_ANDROID, _as.has_full_storage_access(), False,
                self._asked_permissions)
            if not kind:
                return
            self._asked_permissions.add(kind)
            from screens.dialogs import confirm_popup

            def allow():
                if kind == "storage":
                    _as.request_basic_permissions()
                    _as.request_full_storage_access()
                else:
                    _as.request_notification_permission()
            confirm_popup("Permission needed", permissions.REASONS[kind],
                          allow, yes_text="Allow")
        except Exception as e:
            print(f"permission prompt skipped: {e}")

    def _first_run_setup(self, dt):
        """First launch: choose which tools the Dashboard shows (Settings can
        change it later; hidden tools stay reachable via the Quick Switcher)."""
        try:
            if load_settings().get("onboarded"):
                return
            from screens.onboarding import open_onboarding
            open_onboarding(on_done=lambda: self.root.get_screen(
                "dashboard").on_enter())
        except Exception as e:
            print(f"first-run setup skipped: {e}")

    def on_stop(self):
        try:
            from core import window_state
            window_state.save(Window, _ON_ANDROID)
        except Exception as e:
            print(f"window state not saved: {e}")

    def _back_at_home(self):
        if _platform == "android":
            self.stop()
            return True
        return False

    def _android_reminder_tick(self, dt):
        try:
            import datetime
            import core.reminders_core as rc
            from core import notify
            reminders = rc.load_reminders()
            state = rc.load_state()
            now = datetime.datetime.now()
            due = rc.scan_due(reminders, state, now)
            for r in due:
                notify.send_notification(r["title"], r.get("notes") or "Reminder")
                rc.mark_fired(r, state, now)
            if due:
                rc.prune_state(reminders, state)
                rc.save_state(state)
        except Exception as e:
            print(f"Reminder tick failed: {e}")

    def build(self):
        if _bl:
            _bl.log("App.build start")
            _bl.start_watchdog()
        self.title = "Srboli"
        sm = GuardedScreenManager(transition=NoTransition())
        sm.add_widget(Dashboard(open_route=self._open_route,
                                version=_APP_VERSION, name="dashboard"))
        sm.add_widget(try_import(SETTINGS_ROUTE[1], SETTINGS_ROUTE[2])(
            name=SETTINGS_ROUTE[0]))

        settings_cfg = load_settings()
        lazy = settings_cfg.get("lazy_load", True)
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

        try:
            import core.advlog as _advlog
            _advlog.install(Window, sm)
            _advlog.set_enabled(settings_cfg.get("advanced_logging", False))
        except Exception as _e:
            print(f"advanced logging unavailable: {_e}")

        # Show the dashboard first, then build the remaining screens one at
        # a time in idle time (Kivy widgets must be built on the main thread,
        # so this is spread over frames rather than done in one long freeze).
        # Opening a screen that isn't built yet still builds it on demand.
        if _bl and _bl.flag("Srboli_safe_mode"):
            _bl.log("safe mode: background preload skipped")
        elif lazy and settings_cfg.get("preload_bg", False):
            from kivy.clock import Clock as _PClock
            _pending = [r for r, _m, _c in SCREENS]
            _last_input = [_PClock.get_time()]

            def _note_input(*a):
                _last_input[0] = _PClock.get_time()
            Window.bind(on_touch_down=_note_input, on_touch_move=_note_input,
                        on_touch_up=_note_input, on_key_down=_note_input,
                        on_mouse_pos=_note_input)

            def _preload_step(dt):
                while _pending and sm.has_screen(_pending[0]):
                    _pending.pop(0)
                if not _pending:
                    return False
                # Building a screen blocks the UI for as long as it takes, so
                # only do it when the user has been idle for a moment.
                if _PClock.get_time() - _last_input[0] < 2.0:
                    return True
                route = _pending.pop(0)
                if _bl:
                    _bl.log(f"preload start {route}")
                try:
                    ensure_screen_loaded(sm, route)
                except Exception as e:
                    print(f"Preload of {route} failed: {e}")
                    if _bl:
                        _bl.log(f"preload FAILED {route}: {e}")
                if _bl:
                    _bl.log(f"preload done  {route}")
                return bool(_pending)

            _PClock.schedule_once(
                lambda dt: _PClock.schedule_interval(_preload_step, 0.5), 3.0)

        # Android permissions are no longer requested here: a tool asks the
        # first time it is opened (SrboliApp._ask_permission), with a reason.

        # Android has no background daemon, so check for due reminders from
        # inside the app (works while the app is open or still alive in the
        # background; not after Android kills the process).
        if _platform == "android":
            try:
                from kivy.clock import Clock
                Clock.schedule_interval(self._android_reminder_tick, 20)
            except Exception as e:
                print(f"Android reminder ticker not started: {e}")

        # Install global quick switcher (works from any screen)
        try:
            from screens.quickswitcher_screen import install_global_switcher
            install_global_switcher(
                sm, ensure_loader=(lambda r: ensure_screen_loaded(sm, r)),
                opener=self._open_route)
        except Exception as e:
            print(f"QuickSwitcher not installed: {e}")

        install_keys(Window, sm,
                     focus_search=lambda: sm.get_screen("dashboard").focus_search(),
                     on_back_at_home=self._back_at_home)
        from kivy.clock import Clock as _OC
        _OC.schedule_once(self._first_run_setup, 0.5)

        if _bl:
            _bl.log("App.build end (dashboard ready)")
            from kivy.clock import Clock as _FC
            _FC.schedule_once(lambda dt: _bl.log("first frame after build"), 0)
            _seen_touch = []

            def _first_touch(win, touch, *a):
                if not _seen_touch:
                    _seen_touch.append(1)
                    _bl.log(f"first touch reached the window "
                            f"(device={touch.device})")
            Window.bind(on_touch_down=_first_touch)
        return sm


if __name__ == "__main__":
    # Two copies would race on the same config / data files (desktop only;
    # Android already runs one activity).
    if not _ON_ANDROID:
        from core import single_instance
        if not single_instance.acquire(os.path.join(
                os.path.dirname(app_data._CONFIG_FILE), ".srboli.lock")):
            print("Srboli is already running.")
            sys.exit(0)
    SrboliApp().run()
