# core/kivy_patches.py - workarounds for Kivy / Android behaviour.
#
# These replace or wrap Kivy internals (underscore methods such as
# ButtonBehavior._do_release and Spinner._toggle_dropdown), so they are only
# known to be right for the Kivy release listed in TESTED_KIVY (the one
# buildozer.spec and requirements-desktop.txt pin). apply() checks that the
# internals still exist and logs a warning instead of failing silently when
# Kivy has moved on.
#
# NOTE: Kivy's Clock/bind look callbacks up by function __name__, so every
# replacement keeps the name of the method it replaces.
import os

TESTED_KIVY = "2.3.1"

# (module, class, attribute) that the patches below rely on
INTERNALS = (
    ("kivy.uix.textinput", "TextInput", "long_touch"),
    ("kivy.uix.textinput", "TextInput", "cancel_long_touch_event"),
    ("kivy.uix.spinner", "Spinner", "_toggle_dropdown"),
    ("kivy.uix.modalview", "ModalView", "open"),
    ("kivy.uix.modalview", "ModalView", "dismiss"),
    ("kivy.uix.behaviors.button", "ButtonBehavior", "_do_release"),
    ("kivy.uix.behaviors.button", "ButtonBehavior", "_do_press"),
)


def missing_internals():
    """The INTERNALS entries this Kivy no longer has."""
    import importlib
    out = []
    for mod, cls, attr in INTERNALS:
        try:
            if not hasattr(getattr(importlib.import_module(mod), cls), attr):
                out.append(f"{cls}.{attr}")
        except Exception:
            out.append(f"{cls}.{attr}")
    return out


def check(log=None):
    """Log a warning when Kivy is not the tested release or lost an internal."""
    import kivy
    problems = []
    if kivy.__version__ != TESTED_KIVY:
        problems.append(f"Kivy {kivy.__version__}, patches tested on {TESTED_KIVY}")
    gone = missing_internals()
    if gone:
        problems.append("missing: " + ", ".join(gone))
    for p in problems:
        (log or print)(f"kivy_patches: {p}")
    return problems


def apply_android(Window, _bl=None):
    """Install the Android-only patches (call once, before building the UI)."""
    check(_bl.log if _bl else None)
    from kivy.uix.textinput import TextInput as _TextInput

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
        from kivy.metrics import dp as _dp, sp as _sp

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
                         font_size=_sp(14), halign="left", valign="middle",
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
            from core.logs import logs_dir as _logs_dir
            _tl = open(os.path.join(_logs_dir(), "Srboli_touch.log"), "a", buffering=1)
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
                    from core.logs import append_capped
                    append_capped("Srboli_crash.log",
                                  f"\n--- {_dt.datetime.now()} ---\n"
                                  + "".join(_tb.format_exception(
                                      type(inst), inst, inst.__traceback__)))
                except Exception:
                    pass
                try:
                    from core.toast import toast
                    toast(f"Something went wrong: {type(inst).__name__}. "
                          "The app kept running (see Settings > logs).")
                except Exception:
                    pass
                return ExceptionManager.PASS
        ExceptionManager.add_handler(_CrashLogger())
    except Exception as _e:
        print(f'crash logger skipped: {_e}')
