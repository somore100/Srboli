# screens/pomodoro_screen.py - Pomodoro: focus rounds with short and long breaks. It keeps
# running while you use other tools, tells you with a notification when a phase ends, keeps
# the screen on while running, and counts today's finished rounds. Logic: core/pomodoro_core.py.
import time

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

from core import notify
from core import pomodoro_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)
CHOICES = {"work": [15, 20, 25, 30, 45, 50, 60, 90], "short": [3, 5, 10, 15],
           "long": [10, 15, 20, 30], "rounds": [2, 3, 4, 5, 6]}
LABEL = {"work": "Focus", "short": "Short", "long": "Long", "rounds": "Rounds"}


class PomodoroScreen(ToolScreen):
    title = "Pomodoro"

    def __init__(self, **kw):
        super().__init__(**kw)
        settings, self.days = core.load()
        self.timer = core.Pomodoro(settings)
        self._ev = None

        self.body.add_widget(Widget(size_hint_y=0.1))
        self.phase_label = Label(text="", font_size=sp(22), bold=True, size_hint_y=None,
                                 height=dp(40))
        self.body.add_widget(self.phase_label)
        self.time_label = Label(text="25:00", font_size=sp(84), bold=True)
        self.body.add_widget(self.time_label)
        self.bar = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(10))
        self.body.add_widget(self.bar)
        self.info = Label(text="", font_size=sp(13), color=theme.MUTED, size_hint_y=None,
                          height=dp(44), halign="center", valign="middle")
        self.info.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.info)

        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.go_btn = Button(text="Start", font_size=sp(17))
        self.go_btn.bind(on_release=lambda *a: self.toggle())
        skip = Button(text="Skip", font_size=sp(14), size_hint_x=0.4)
        skip.bind(on_release=lambda *a: self.skip())
        reset = Button(text="Reset", font_size=sp(14), size_hint_x=0.4)
        reset.bind(on_release=lambda *a: self.reset())
        for b in (self.go_btn, skip, reset):
            row.add_widget(b)
        self.body.add_widget(row)

        self.spinners = {}
        srow = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
        for key in ("work", "short", "long", "rounds"):
            unit = "" if key == "rounds" else " min"
            sp_ = Spinner(text=f"{LABEL[key]}: {self.timer.settings[key]}{unit}",
                          values=[f"{LABEL[key]}: {v}{unit}" for v in CHOICES[key]],
                          font_size=sp(11))
            sp_.bind(text=lambda w, t, k=key: self._setting_changed(k, t))
            srow.add_widget(sp_)
            self.spinners[key] = sp_
        self.body.add_widget(srow)
        self.auto_btn = Button(text="", size_hint_y=None, height=dp(38), font_size=sp(12))
        self.auto_btn.bind(on_release=lambda *a: self.toggle_auto())
        self.body.add_widget(self.auto_btn)
        self.body.add_widget(Widget(size_hint_y=0.1))
        self._refresh()

    # ----- controls -----
    def toggle(self):
        if self.timer.running:
            self.timer.pause(time.monotonic())
            self._stop_ticking()
        else:
            self.timer.start(time.monotonic())
            self._start_ticking()
        self._refresh()

    def skip(self):
        self.timer.skip(time.monotonic())
        self._refresh()

    def reset(self):
        self.timer.reset()
        self._stop_ticking()
        self._refresh()

    def toggle_auto(self):
        s = dict(self.timer.settings)
        s["auto"] = not s["auto"]
        self._apply(s)

    def _setting_changed(self, key, text):
        try:
            value = int(text.split(":")[1].split()[0])
        except (IndexError, ValueError):
            return
        s = dict(self.timer.settings)
        s[key] = value
        self._apply(s)

    def _apply(self, settings):
        self.timer.configure(settings)
        core.save(self.timer.settings, self.days)
        self._refresh()

    # ----- ticking -----
    def _start_ticking(self):
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, 0.25)
        try:
            Window.allow_screensaver = False          # keep the screen on while it runs
        except Exception:
            pass

    def _stop_ticking(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        try:
            Window.allow_screensaver = True
        except Exception:
            pass

    def _tick(self, dt):
        events = self.timer.tick(time.monotonic())
        for kind, value in events:
            if kind == "work_done":
                core.add_focus(self.days, value)
                core.save(self.timer.settings, self.days)
            elif kind == "phase":
                self._announce(value)
        if not self.timer.running:
            self._stop_ticking()
        self._refresh()

    def _announce(self, phase):
        msg = {core.WORK: "Break over. Time to focus.",
               core.SHORT: "Focus round done. Take a short break.",
               core.LONG: "Great work! Take a long break."}[phase]
        try:
            notify.send_notification("Srboli Pomodoro", msg)
        except Exception:
            pass

    # ----- display -----
    def on_pre_enter(self, *a):
        self._refresh()

    def _refresh(self):
        t = self.timer
        self.phase_label.text = core.PHASE_NAMES[t.phase]
        self.phase_label.color = theme.ACCENT if t.phase == core.WORK else theme.SUCCESS
        self.time_label.text = core.fmt(t.remaining)
        self.bar.value = t.progress()
        self.go_btn.text = "Pause" if t.running else ("Resume" if t.progress() > 0 else "Start")
        today = self.days.get(time.strftime("%Y-%m-%d"), {"rounds": 0, "minutes": 0})
        self.info.text = (f"Round {t.round} of {t.settings['rounds']}\n"
                          f"Today: {today['rounds']} focus rounds, {today['minutes']} min")
        for key, sp_ in self.spinners.items():
            unit = "" if key == "rounds" else " min"
            text = f"{LABEL[key]}: {t.settings[key]}{unit}"
            if sp_.text != text:
                sp_.text = text
        self.auto_btn.text = ("Start the next phase automatically: on" if t.settings["auto"]
                              else "Start the next phase automatically: off")
        self.auto_btn.background_color = theme.ACCENT if t.settings["auto"] else OFF
