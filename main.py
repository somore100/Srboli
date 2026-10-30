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

from kivy.core.window import Window
# Fixes a Kivy/Android interaction bug: when a TextInput has focus and the
# on-screen keyboard is up, tapping a Spinner (e.g. Script Mode's "Split
# by:") first dismisses the keyboard. The window resize that follows can
# get read as a "touch outside" by the DropDown that just opened, closing
# it before you can pick anything. "below_target" keeps the window from
# resizing under the focused widget, which avoids that resize-triggered
# dismiss. See screens/script_mode_screen.py for the matching defocus fix.
# (softinput_mode left at Kivy default - see global Spinner fix below)

# Kivy treats plain-int font_size as pixels, so on a high-density phone the
# app's font_size=12/14 text is tiny (and rows look cramped/cut off). The
# code sizes widgets in dp(), so scale ints by screen density on Android to
# match. Must run before any screen module creates widgets.
from kivy.utils import platform as _platform
if _platform == "android":
    from kivy.metrics import Metrics as _Metrics
    from kivy.uix.label import Label as _Label
    from kivy.uix.textinput import TextInput as _TextInput

    def _scale_font_ints(cls):
        _orig = cls.__init__

        def __init__(self, *a, **kw):
            fs = kw.get("font_size")
            if isinstance(fs, (int, float)):
                kw["font_size"] = int(round(fs * _Metrics.density))
            _orig(self, *a, **kw)
        cls.__init__ = __init__

    _scale_font_ints(_Label)
    _scale_font_ints(_TextInput)

    try:
        # Kivy shows the Select All / Paste bubble after a 0.5 s hold, which a
        # normal tap on a phone often exceeds. Require ~1 s instead.
        from kivy.clock import Clock as _Clock
        _orig_long = _TextInput.long_touch
        _orig_cancel = _TextInput.cancel_long_touch_event

        # NOTE: Kivy's Clock stores callbacks by function __name__ and looks
        # them up on the object later (WeakMethod), so these replacements MUST
        # be named exactly like the methods they replace.
        def long_touch(self, dt):
            if not getattr(self, "_lt_second", False):
                self._lt_second = True
                self._long_touch_ev = _Clock.schedule_once(self.long_touch, 0.55)
                return
            self._lt_second = False
            _orig_long(self, dt)

        def cancel_long_touch_event(self):
            self._lt_second = False
            _orig_cancel(self)

        _TextInput.long_touch = long_touch
        _TextInput.cancel_long_touch_event = cancel_long_touch_event
    except Exception as _e:
        print(f'long-press patch skipped: {_e}')

    # Any Spinner tapped while a TextInput has focus: drop focus first, so
    # the keyboard dismissal doesn't close the just-opened dropdown.
    try:
        from kivy.uix.spinner import Spinner as _Spinner
        from kivy.core.window import Window as _W
        _orig_sp_touch = _Spinner.on_touch_down

        def _sp_touch(self, touch):
            if self.collide_point(*touch.pos):
                try:
                    from kivy.uix.textinput import TextInput as _TI
                    for top in list(_W.children):
                        for w in top.walk():
                            if isinstance(w, _TI) and w.focus:
                                w.focus = False
                except Exception:
                    pass
            return _orig_sp_touch(self, touch)
        _Spinner.on_touch_down = _sp_touch
    except Exception as _e:
        print(f'spinner patch skipped: {_e}')

    # Kivy's DropDown opens and vanishes immediately on this phone (every
    # Spinner: Export format, Split by, File Sorter fields...). Popups opened
    # from the same kind of tap work fine, so on Android a Spinner shows its
    # options in a ModalView list instead. Setting .text is exactly what the
    # DropDown path does, so all existing bind(text=...) callbacks still fire.
    try:
        from kivy.uix.spinner import Spinner as _Spinner2
        from kivy.uix.modalview import ModalView as _MV
        from kivy.uix.scrollview import ScrollView as _SV
        from kivy.uix.boxlayout import BoxLayout as _BL
        from kivy.uix.button import Button as _Btn
        from kivy.metrics import dp as _dp

        def _spinner_pick_list(self, *a):
            values = list(self.values or [])
            if not values:
                return
            row_h = _dp(52)
            box = _BL(orientation="vertical", size_hint_y=None, spacing=2)
            box.bind(minimum_height=box.setter("height"))
            view = _MV(size_hint=(0.86, None), auto_dismiss=True,
                       background_color=(0, 0, 0, 0.75))
            view.height = min(row_h * len(values) + _dp(8), Window.height * 0.7)

            def _choose(v):
                def _do(*_):
                    self.text = v
                    view.dismiss()
                return _do

            for v in values:
                b = _Btn(text=str(v), size_hint_y=None, height=row_h,
                         font_size=14, halign="left", valign="middle",
                         background_color=((0.2, 0.55, 0.8, 1)
                                           if v == self.text
                                           else (0.25, 0.25, 0.25, 1)))
                b.bind(width=lambda inst, w: setattr(
                    inst, "text_size", (w - _dp(16), None)))
                b.bind(on_release=_choose(v))
                box.add_widget(b)
            sv = _SV(do_scroll_x=False)
            sv.add_widget(box)
            view.add_widget(sv)
            view.open()

        _Spinner2._toggle_dropdown = _spinner_pick_list
    except Exception as _e:
        print(f'spinner picker skipped: {_e}')

    # Popups (Popup/ModalView) fade in/out via Kivy Animation, and are only
    # removed from the window when that animation reaches its last frame. A
    # popup that "stays after the button was tapped" is consistent with that
    # final step not happening. Skip the animation so open/dismiss take effect
    # immediately. NOTE: replacement functions keep the ORIGINAL method names
    # (Kivy's Clock/bind look callbacks up by __name__).
    try:
        from kivy.uix.modalview import ModalView as _MVx
        _orig_mv_open = _MVx.open
        _orig_mv_dismiss = _MVx.dismiss

        def open(self, *a, **kw):
            kw.setdefault("animation", False)
            return _orig_mv_open(self, *a, **kw)

        def dismiss(self, *a, **kw):
            kw.setdefault("animation", False)
            return _orig_mv_dismiss(self, *a, **kw)

        _MVx.open = open
        _MVx.dismiss = dismiss
    except Exception as _e:
        print(f"modal patch skipped: {_e}")

    # Duplicate-tap filter (core/touch_dedupe.py). OFF by default: turn it on
    # in the Touch Test screen. It switches itself off again if taps stop
    # working. Flag files (Srboli_no_dedupe / Srboli_safe_mode) still force it
    # off when the app can read them.
    try:
        import core.touch_dedupe as _td
        _td_log = None
        try:
            from core.android_storage import shared_storage_root as _ssr3
            _tp = os.path.join(_ssr3(), "Srboli_debug_touch")
            if os.path.exists(_tp):
                _tlog = open(os.path.join(_ssr3(), "Srboli_touch.log"), "a",
                             buffering=1)
                import time as _t3
                _td_log = lambda m: _tlog.write(f"{_t3.time():.3f} {m}\n")
        except Exception:
            pass
        _forced_off = _bl and (_bl.flag("Srboli_no_dedupe")
                               or _bl.flag("Srboli_safe_mode"))
        if not _forced_off and _td.decide_at_startup(
                _bl.log if _bl else None):
            _td.install(_td_log)
            # first button that really reacts proves taps work
            from kivy.uix.behaviors.button import ButtonBehavior as _BB2
            _orig_rel = _BB2._do_release

            _marked = [False]

            # Stays installed (restoring _orig_rel would also remove any
            # wrapper added after this one, e.g. the touch trace); the flag
            # makes mark_healthy() run once. Kivy finds the callback by
            # __name__, so the function keeps the name _do_release.
            def _do_release(self, *a):
                if not _marked[0]:
                    _marked[0] = True
                    try:
                        _td.mark_healthy()
                    except Exception:
                        pass
                return _orig_rel(self, *a)
            _BB2._do_release = _do_release
            if _bl:
                _bl.log("touch dedupe installed (enabled in Touch Test)")
        elif _bl:
            _bl.log("touch dedupe OFF")
    except Exception as _e:
        if _bl:
            _bl.log(f"touch dedupe NOT installed: {_e}")

    # Ghost-press guard (core/tap_guard.py): one physical tap reaches a widget
    # twice a few ms apart on this phone; ignore the second press of the same
    # button. Conservative (it can only ignore, never block the first tap).
    try:
        import core.tap_guard as _tg
        if _bl and _bl.flag("Srboli_safe_mode"):
            raise RuntimeError("safe mode")
        _tg.install()
        if _bl:
            _bl.log("tap guard installed")
    except Exception as _e:
        if _bl:
            _bl.log(f"tap guard NOT installed: {_e}")

    # Opt-in touch trace for the "needs two taps" bug. Create an EMPTY file
    # named Srboli_debug_touch in the phone's storage root, restart the app,
    # reproduce, then send Srboli_touch.log. No file = no logging, no cost.
    try:
        from core.android_storage import shared_storage_root as _ssr2
        _root2 = _ssr2()
        if os.path.exists(os.path.join(_root2, "Srboli_debug_touch")):
            import time as _t
            _tl = open(os.path.join(_root2, "Srboli_touch.log"), "a", buffering=1)
            _tl.write("\n=== touch trace start ===\n")

            def _mk(kind):
                def _h(win, touch, *a):
                    try:
                        _tl.write(f"{_t.time():.3f} {kind} id={touch.uid} "
                                  f"pos=({touch.x:.0f},{touch.y:.0f}) "
                                  f"prof={','.join(touch.profile)}\n")
                    except Exception:
                        pass
                return _h
            Window.bind(on_touch_down=_mk("DOWN"), on_touch_up=_mk("UP"))

            from kivy.uix.behaviors.button import ButtonBehavior as _BB
            _o_press, _o_rel = _BB._do_press, _BB._do_release

            def _do_press(self, *a):
                _tl.write(f"{_t.time():.3f} PRESS {type(self).__name__} "
                          f"{getattr(self, 'text', '')!r}\n")
                return _o_press(self, *a)

            def _do_release(self, *a):
                _tl.write(f"{_t.time():.3f} RELEASE {type(self).__name__} "
                          f"{getattr(self, 'text', '')!r}\n")
                return _o_release(self, *a)
            _o_release = _o_rel
            _BB._do_press, _BB._do_release = _do_press, _do_release
    except Exception as _e:
        print(f"touch trace skipped: {_e}")

    # Crash log + keep the app alive on Python exceptions in UI callbacks.
    try:
        from kivy.base import ExceptionHandler, ExceptionManager
        import traceback as _tb, datetime as _dt

        class _CrashLogger(ExceptionHandler):
            def handle_exception(self, inst):
                try:
                    from core.android_storage import shared_storage_root
                    path = os.path.join(shared_storage_root(),
                                        "Srboli_crash.log")
                    with open(path, "a", encoding="utf-8") as f:
                        f.write(f"\n--- {_dt.datetime.now()} ---\n")
                        f.write("".join(_tb.format_exception(
                            type(inst), inst, inst.__traceback__)))
                except Exception:
                    pass
                return ExceptionManager.PASS
        ExceptionManager.add_handler(_CrashLogger())
    except Exception as _e:
        print(f'crash logger skipped: {_e}')

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


from screens.registry import SCREENS, LABELS, GROUPS
from screens.settings_screen import (load_settings, effective_menu_order,
                                     update_dashboard_state)
from core import dashboard_core as dash

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


class Dashboard(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._build()

    def _build(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        hdr = BoxLayout(size_hint_y=None, height=dp(70))
        title_col = BoxLayout(orientation="vertical")
        title_col.add_widget(Label(text="[b]Srboli[/b]", markup=True,
                             font_size=30, size_hint_y=None, height=dp(48)))
        title_col.add_widget(Label(text="your pocket swiss-knife",
                             font_size=11, size_hint_y=None, height=dp(18)))
        hdr.add_widget(title_col)
        gear = Button(text="Settings", size_hint=(None, None),
                     width=dp(100), height=dp(40), font_size=12,
                     pos_hint={"center_y": 0.5})
        gear.bind(on_release=lambda *a: setattr(self.manager, "current", "settings"))
        hdr.add_widget(gear)
        root.add_widget(hdr)

        # search: type a few letters and only matching tools are listed
        self._search = TextInput(hint_text="Search tools...", multiline=False,
                                 size_hint_y=None, height=dp(38), font_size=14)
        self._search.bind(text=lambda *a: self._fill_list())
        root.add_widget(self._search)

        sv = ScrollView()
        self._grid = GridLayout(cols=1, spacing=5, size_hint_y=None,
                                padding=(6, 6))
        self._grid.bind(minimum_height=self._grid.setter("height"))
        sv.add_widget(self._grid)
        root.add_widget(sv)
        self._list_sig = None
        self._fill_list()

        root.add_widget(Label(text=f"Srboli v{_APP_VERSION}", font_size=9,
                              size_hint_y=None, height=dp(18)))
        self.add_widget(root)
        self._sig = self._signature()

    # ── the tool list: search results, or Recent + collapsible sections ──
    def _tool_button(self, route, label, font_size=14):
        btn = Button(text=label, size_hint_y=None, height=dp(52),
                     font_size=font_size, shorten=True, shorten_from="right")
        btn.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(8), None)))
        btn.bind(on_release=lambda inst, r=route: self._goto(r))
        return btn

    def _section_title(self, text):
        lbl = Label(text=f"[b]{text}[/b]", markup=True, font_size=12,
                    halign="left", size_hint_y=None, height=dp(24),
                    color=(0.55, 0.8, 1, 1))
        lbl.bind(size=lbl.setter("text_size"))
        return lbl

    def _fill_list(self, force=False):
        menu = effective_menu_order()
        query = self._search.text.strip()
        cfg = load_settings()
        recent = dash.visible_recent(cfg["recent"], menu)
        sig = (tuple(menu), query, tuple(recent), tuple(cfg["collapsed"]))
        if sig == self._list_sig and not force:
            return                      # nothing changed: no flash on Back
        self._list_sig = sig
        grid = self._grid
        grid.clear_widgets()

        if query:
            hits = dash.search(menu, query)
            if not hits:
                grid.add_widget(Label(text=f"No tool matches '{query}'.",
                                      size_hint_y=None, height=dp(40),
                                      font_size=13, color=(0.7, 0.7, 0.7, 1)))
            for route, label in hits:
                grid.add_widget(self._tool_button(route, label))
            return

        if recent:
            grid.add_widget(self._section_title("Recent"))
            row = BoxLayout(size_hint_y=None, height=dp(52), spacing=5)
            for route, label in recent:
                row.add_widget(self._tool_button(route, label, font_size=12))
            grid.add_widget(row)

        for key, title, members in dash.group_menu(menu, GROUPS):
            folded = key in cfg["collapsed"]
            head = Button(text=f"[{'+' if folded else '-'}]  {title}  "
                               f"({len(members)})",
                          size_hint_y=None, height=dp(40), font_size=14,
                          halign="left", background_color=(0.2, 0.3, 0.45, 1))
            head.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(12), None)))
            head.bind(on_release=lambda inst, k=key: self._toggle_section(k))
            grid.add_widget(head)
            if not folded:
                for route, label in members:
                    grid.add_widget(self._tool_button(route, label))

    def _toggle_section(self, key):
        update_dashboard_state(collapsed=dash.toggle_collapsed(
            load_settings()["collapsed"], key))
        self._fill_list()

    def _goto(self, route):
        update_dashboard_state(recent=dash.push_recent(
            load_settings()["recent"], route))
        ensure_screen_loaded(self.manager, route)
        self.manager.current = route

    def _signature(self):
        return (tuple(effective_menu_order()), app_data.get_data_dir())

    def on_enter(self, *a):
        # Rebuild only when something the dashboard shows has changed
        # (screen order/hidden list from Settings, or the data dir).
        # Rebuilding on every return tore down and recreated every button,
        # which showed up as a visible flash when pressing Back.
        sig = self._signature()
        if sig != getattr(self, "_sig", None):
            self._build()
        else:
            self._search.text = ""      # leave search mode; Recent may have changed
            self._fill_list()

    def on_touch_down(self, touch):
        if hasattr(touch, "button"):
            if getattr(touch, "is_mouse_scrolling", False):
                return super().on_touch_down(touch)
            if touch.button != "left":
                return True
        return super().on_touch_down(touch)


class SrboliApp(App):
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
        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(Dashboard(name="dashboard"))
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

        # Ask for real filesystem access (Fast Transfer, Gallery Sorter,
        # File Sorter, and the data-dir picker all need this). No-op off
        # Android, and no-op if already granted. This opens a one-time
        # system settings screen rather than a normal popup — see
        # core/android_storage.py for why.
        try:
            from core.android_storage import (
                request_basic_permissions, request_full_storage_access,
                has_full_storage_access,
            )
            request_basic_permissions()
            if not has_full_storage_access():
                request_full_storage_access()
        except Exception as e:
            print(f"Storage permission request skipped: {e}")

        # Android has no background daemon, so check for due reminders from
        # inside the app (works while the app is open or still alive in the
        # background; not after Android kills the process).
        if _platform == "android":
            try:
                from kivy.clock import Clock
                from core.android_storage import request_notification_permission
                request_notification_permission()
                Clock.schedule_interval(self._android_reminder_tick, 20)
            except Exception as e:
                print(f"Android reminder ticker not started: {e}")

        # Install global quick switcher (works from any screen)
        try:
            from screens.quickswitcher_screen import install_global_switcher
            install_global_switcher(
                sm, ensure_loader=(lambda r: ensure_screen_loaded(sm, r)))
        except Exception as e:
            print(f"QuickSwitcher not installed: {e}")

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
    SrboliApp().run()
