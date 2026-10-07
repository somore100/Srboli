# tests/test_loading_timer_logic.py — needs Kivy + a display (run under
# xvfb-run on a headless box). Checks the action is read at FINISH time,
# pause/resume timing, and that Android-only restrictions hold.
import os, sys
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import screens.loading_timer_screen as lt

fails = 0
def check(name, got, want):
    global fails
    if got != want:
        fails += 1; print(f"FAIL {name}\n  got : {got!r}\n  want: {want!r}")
    else:
        print(f"ok   {name}")

calls = []
lt.os.system = lambda c: calls.append(c) or 0
lt.threading.Thread = lambda target, daemon=None: type(
    "T", (), {"start": lambda s: calls.append("notify")})()

clock = [1000.0]
sc = lt.LoadingTimerScreen()
sc._now = lambda: clock[0]
sc.seconds_input.text = "20"

# the user's scenario: start with Nothing, switch to Shutdown mid-run
sc.start_timer()
clock[0] += 15; sc._update_timer(0)
check("mid-run label", sc.time_label.text, "00:00:05")
sc.action_spinner.text = "Shutdown"
check("switch is acknowledged", sc.status_label.text, "On finish: Shutdown")
clock[0] += 5; sc._update_timer(0)
check("shutdown ran after switch", calls, ["systemctl poweroff"])
check("start re-enabled", sc.start_btn.disabled, False)

# pause/resume doesn't count paused time
calls.clear(); sc.action_spinner.text = "Nothing"
sc.start_timer(); clock[0] += 10; sc._update_timer(0)
sc.toggle_pause(); clock[0] += 500
sc.toggle_pause(); clock[0] += 9; sc._update_timer(0)
check("paused time ignored", sc.time_label.text, "00:00:01")
clock[0] += 1; sc._update_timer(0)
check("finished, Nothing does nothing", calls, [])

# frames skipped (app paused in background) still finish on resume
sc.reset_timer(); sc.start_timer(); clock[0] += 3600; sc._update_timer(0)
check("late frame completes", sc.status_label.text.startswith("Done!"), True)

# notify path
sc.reset_timer(); sc.action_spinner.text = "Notify only"
sc.start_timer(); clock[0] += 21; sc._update_timer(0)
check("notify fired", calls, ["notify"])

# android values
check("desktop has shutdown", "Shutdown" in lt.ACTIONS_DESKTOP, True)
check("android has no shutdown", "Shutdown" in lt.ACTIONS_ANDROID, False)
print("\nFAILED" if fails else "\nall passed"); sys.exit(1 if fails else 0)
