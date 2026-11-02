# core/selftest.py - `Srboli --selftest [outfile]`: can every tool be loaded?
#
# Imports each screen in screens.registry.SCREENS and looks up its class,
# exactly what main.try_import does, without opening a window. Results go to
# outfile too (a windowed Windows exe has no console). The last line is
# "SELFTEST OK" or "SELFTEST FAILED"; the exit code is 0 / 1.
import importlib
import os
import sys
import traceback


def check_screens(screens):
    """[(route, error text)] for every screen that can't be loaded."""
    failures = []
    for route, mod, cls in screens:
        try:
            getattr(importlib.import_module(mod), cls)
        except Exception as e:
            failures.append((route, f"{mod}.{cls}: {type(e).__name__}: {e}"))
    return failures


def check_data_files():
    """Runtime data files the screens look for."""
    problems = []
    try:
        from screens.backrooms_screen import find_levels_json
        if not find_levels_json():
            problems.append("backrooms_data.json not found")
    except Exception as e:
        problems.append(f"backrooms data check: {e}")
    try:
        from core.feedback import make_config
        cfg = make_config()
        if not cfg.endpoint:
            problems.append("feedback.json missing or has no endpoint")
    except Exception as e:
        problems.append(f"feedback check: {e}")
    return problems


def _no_window():
    """Make `from kivy.core.window import Window` hand out a stand-in instead of opening a real OpenGL window.

    The self-test only needs to know that every screen *imports*. CI runners cannot always open a window: the Windows
    runner only has the GDI software renderer (OpenGL 1.1, Kivy needs 2.0) and the macOS runner has no GPU / pixel
    format, so the first screen that imports Window made Kivy abort the whole process before any result was written.
    Set SRBOLI_SELFTEST_WINDOW=1 to test with the real window instead."""
    if os.environ.get("SRBOLI_SELFTEST_WINDOW") == "1":
        return
    import types
    from unittest import mock
    mod = types.ModuleType("kivy.core.window")
    mod.Window = mock.MagicMock(name="Window")
    mod.__getattr__ = lambda name: mock.MagicMock(name=name)          # any other name a screen imports (PEP 562)
    sys.modules["kivy.core.window"] = mod
    from kivy.metrics import Metrics            # dp()/sp() at import time would otherwise ask the (missing) window for its DPI
    Metrics.dpi = 96.0
    Metrics.density = 1.0


def run(outfile=None):
    os.environ.setdefault("KIVY_NO_ARGS", "1")
    _no_window()
    lines = []
    try:
        from screens.registry import SCREENS
        fails = check_screens(SCREENS)
        for route, why in fails:
            lines.append(f"FAIL {route}: {why}")
        for p in check_data_files():
            fails.append(("data", p))
            lines.append(f"FAIL data: {p}")
        lines.append(f"{len(SCREENS) - len([f for f in fails if f[0] != 'data'])}"
                     f"/{len(SCREENS)} screens load")
        ok = not fails
    except Exception:
        lines.append("FAIL selftest crashed:\n" + traceback.format_exc())
        ok = False
    lines.append("SELFTEST OK" if ok else "SELFTEST FAILED")
    text = "\n".join(lines) + "\n"
    try:
        sys.stdout.write(text)
    except Exception:
        pass
    if outfile:
        with open(outfile, "w", encoding="utf-8") as f:
            f.write(text)
    return 0 if ok else 1
