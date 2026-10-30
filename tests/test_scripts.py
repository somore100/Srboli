# Runs every tests/test_*.py script as its own pytest case.
#   pytest -m "not display"      Kivy-free core tests (what CI runs on every push)
#   xvfb-run -a pytest           everything (the screen tests need a display)
import glob
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THIS = os.path.basename(__file__)


def _needs_display(path):
    src = open(path, encoding="utf-8").read()
    return "kivy" in src or "screens." in src


def _cases():
    for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
        name = os.path.basename(path)
        if name == THIS:
            continue
        marks = [pytest.mark.display] if _needs_display(path) else []
        yield pytest.param(path, id=name[:-3], marks=marks)


@pytest.mark.parametrize("path", list(_cases()))
def test_script(path):
    if _needs_display(path) and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("needs a display (run under xvfb-run)")
    env = dict(os.environ, KIVY_NO_ARGS="1", PYTHONPATH=ROOT)
    r = subprocess.run([sys.executable, path], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, (r.stdout[-1500:] + r.stderr[-1500:])
