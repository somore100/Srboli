# tests/test_pomodoro_screen.py - xvfb-run -a python3 tests/test_pomodoro_screen.py  (kivy screens.)
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from screens.pomodoro_screen import PomodoroScreen
from core import pomodoro_core as core
core.save = lambda *a, **k: None            # never touch the real saved settings

sc = PomodoroScreen()
sc.days = {}
sc.spinners["work"].text = "Focus: 1 min"
assert sc.timer.settings["work"] == 1 and sc.time_label.text == "01:00"
sc.toggle(); assert sc.timer.running and sc.go_btn.text == "Pause" and sc._ev is not None
sc.timer._last -= 61                       # pretend 61 seconds went by
sc._tick(0)
assert sc.timer.phase == core.SHORT and sum(d["rounds"] for d in sc.days.values()) == 1
assert "1 focus rounds" in sc.info.text
sc.toggle(); assert not sc.timer.running and sc._ev is None
sc.toggle_auto(); assert sc.timer.settings["auto"] is False and "off" in sc.auto_btn.text
sc.reset(); assert sc.timer.phase == core.WORK and sc.time_label.text == "01:00"
print("pomodoro screen OK")
