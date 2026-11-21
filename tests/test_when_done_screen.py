# tests/test_when_done_screen.py - xvfb-run -a python3 tests/test_when_done_screen.py
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from unittest.mock import patch
from screens.when_done_screen import WhenDoneScreen
from core import when_done_core as core

class Ps:
    def __init__(s): s.cpu = 50.0; s.procs = ["rclone"]
    def cpu_percent(s, interval=None): return s.cpu
    def process_iter(s, attrs):
        class P:
            def __init__(p, n): p.info = {"name": n}
        return [P(n) for n in s.procs]
ps = Ps()
orig = core.Sampler.__init__
with patch.object(core.Sampler, "__init__", lambda self, m=None: orig(self, ps)):
    s = WhenDoneScreen()
    s.set_kind("cpu"); assert s.limit.text == "10"
    s.limit.text = "10"; s.quiet.text = "0.01"            # 0.6 s quiet
    s.action.text = "Only notify"
    s.start(); assert s._ev and s.start_btn.text == "Stop watching"
    s.tick(100.0); assert "Busy" in s.big.text
    ps.cpu = 1.0
    s.tick(101.0); assert "Quiet for" in s.big.text
    with patch("core.notify.send_notification"):
        s.tick(102.0)
    assert s.monitor.done and not s._ev and s.big.text == "The task is done."
    # shut down: countdown shows, Cancel stops it, nothing is run
    s.action.text = "Shut down"; ran = []
    with patch.object(core, "run_action", lambda a: ran.append(a)), patch("core.notify.send_notification"):
        s.start(); s.tick(200.0); ps.cpu = 99.0; s.tick(201.0); ps.cpu = 0.0; s.tick(202.0); s.tick(203.0)
        assert s._pop is not None and "Shut down in 60 seconds" in s.big.text, s.big.text
        s._cancel_fn(); assert s._pop is None and s._count_ev is None and "Cancelled" in s.big.text and not ran
        # let it run out: the action runs exactly once
        s.start(); s.tick(300.0); ps.cpu = 99.0; s.tick(301.0); ps.cpu = 0.0; s.tick(302.0); s.tick(303.0)
        s._left = 2; s._tick_fn(0); assert not ran
        s._tick_fn(0); assert ran == ["Shut down"] and s._pop is None
    # process mode needs a pick
    s.set_kind("process"); assert "rclone" in s.proc.values
    s.start(); assert "Pick a program" in s.big.text
    s.proc.text = "rclone"; s.start(); s.tick(400.0); assert "still running" in s.big.text
    ps.procs = []
    with patch("core.notify.send_notification"), patch.object(core, "run_action"):
        s.action.text = "Only notify"; s.tick(401.0)
    assert s.big.text == "The task is done."
print("when done screen OK")
