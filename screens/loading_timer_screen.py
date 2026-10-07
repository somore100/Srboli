# screens/loading_timer_screen.py
# Countdown timer with an action on completion.
#  * Desktop: Nothing / Shutdown / Suspend / Notify only.
#  * Android: apps cannot power the phone off or suspend it, so only
#    Nothing / Notify only are offered (Notify posts a real notification).
# The action is read when the timer FINISHES, so you can change it while the
# timer is running. Elapsed time uses a monotonic clock, so it stays correct
# even if frames are skipped or the app was paused for a while.

import sys
import os
import time
import threading

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.utils import platform as _platform

_IS_ANDROID = _platform == "android"
ACTIONS_DESKTOP = ("Nothing", "Shutdown", "Suspend", "Notify only")
ACTIONS_ANDROID = ("Nothing", "Notify only")


class LoadingTimerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation="vertical", padding=dp(14),
                           spacing=dp(10))

        layout.add_widget(Label(text="[b]Loading / Timer[/b]", markup=True,
                                size_hint_y=None, height=dp(40),
                                font_size=18))

        # ── time inputs ──
        time_layout = BoxLayout(orientation="horizontal", spacing=dp(8),
                                size_hint_y=None, height=dp(52))
        for attr, hint in (("hours_input", "Hours"),
                           ("minutes_input", "Minutes"),
                           ("seconds_input", "Seconds")):
            ti = TextInput(hint_text=hint, multiline=False,
                           input_filter="int", halign="center",
                           font_size=18, padding=[dp(6), dp(14), dp(6), dp(6)])
            setattr(self, attr, ti)
            time_layout.add_widget(ti)
        layout.add_widget(time_layout)

        # ── preset buttons ──
        presets = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for label, s in (("5 min", 300), ("10 min", 600),
                         ("30 min", 1800), ("1 hr", 3600)):
            b = Button(text=label, font_size=13)
            b.bind(on_release=lambda inst, sec=s: self._apply_preset(sec))
            presets.add_widget(b)
        layout.add_widget(presets)

        # ── on-complete action ──
        action_row = BoxLayout(size_hint_y=None, height=dp(44),
                               spacing=dp(8))
        lbl = Label(text="On complete:", size_hint_x=0.4, font_size=14,
                    halign="left", valign="middle")
        lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        action_row.add_widget(lbl)
        self.action_spinner = Spinner(
            text="Nothing",
            values=ACTIONS_ANDROID if _IS_ANDROID else ACTIONS_DESKTOP,
            size_hint_x=0.6, font_size=14,
        )
        self.action_spinner.bind(text=self._on_action_changed)
        action_row.add_widget(self.action_spinner)
        layout.add_widget(action_row)

        # ── start / pause / reset ──
        ctrl = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        self.start_btn = Button(text="Start", font_size=15)
        self.start_btn.bind(on_release=self.start_timer)
        self.pause_btn = Button(text="Pause", font_size=15, disabled=True)
        self.pause_btn.bind(on_release=self.toggle_pause)
        self.reset_btn = Button(text="Reset", font_size=15, disabled=True)
        self.reset_btn.bind(on_release=self.reset_timer)
        for b in (self.start_btn, self.pause_btn, self.reset_btn):
            ctrl.add_widget(b)
        layout.add_widget(ctrl)

        # ── time remaining ──
        self.time_label = Label(text="00:00:00", font_size=40,
                                size_hint_y=None, height=dp(64))
        layout.add_widget(self.time_label)

        # ── progress bar (always visible, redrawn on resize) ──
        self.canvas_area = BoxLayout(size_hint_y=None, height=dp(26))
        self.canvas_area.bind(pos=self._draw_progress,
                              size=self._draw_progress)
        layout.add_widget(self.canvas_area)

        # ── status message ──
        self.status_label = Label(text="", font_size=14,
                                  size_hint_y=None, height=dp(36))
        layout.add_widget(self.status_label)

        # spacer keeps everything at the top and Back at the bottom
        layout.add_widget(Widget())

        back = Button(text="< Back", size_hint_y=None, height=dp(48),
                      font_size=15)
        back.bind(on_release=lambda *a: setattr(self.manager, "current",
                                                "dashboard"))
        layout.add_widget(back)

        self.add_widget(layout)

        # internal state
        self._progress = 0.0
        self._duration = 0
        self._base = 0.0            # seconds elapsed before the current run
        self._seg_start = 0.0       # monotonic time the current run began
        self._event = None
        self._paused = False
        self._running = False
        Clock.schedule_once(self._draw_progress, 0)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _now(self):
        return time.monotonic()

    def _elapsed(self):
        if self._running and not self._paused:
            return self._base + (self._now() - self._seg_start)
        return self._base

    def _apply_preset(self, total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        self.hours_input.text   = str(h) if h else ""
        self.minutes_input.text = str(m) if m else ""
        self.seconds_input.text = str(s) if s else ""

    def _on_action_changed(self, inst, text):
        """Switching the action while the timer runs takes effect when it
        finishes; show it so the change is visibly registered."""
        if self._running and not self._paused:
            self.status_label.text = f"On finish: {text}"
        elif self._running:
            self.status_label.text = f"Paused  |  on finish: {text}"

    # ── timer control ────────────────────────────────────────────────────────
    def start_timer(self, *args):
        h = int(self.hours_input.text)   if self.hours_input.text.isdigit()   else 0
        m = int(self.minutes_input.text) if self.minutes_input.text.isdigit() else 0
        s = int(self.seconds_input.text) if self.seconds_input.text.isdigit() else 0
        self._duration = h * 3600 + m * 60 + s

        if self._duration <= 0:
            self.status_label.text = "Enter a valid time first."
            return

        self._base = 0.0
        self._seg_start = self._now()
        self._progress = 0.0
        self._paused = False
        self._running = True
        self.status_label.text = f"On finish: {self.action_spinner.text}"
        self.pause_btn.disabled = False
        self.reset_btn.disabled = False
        self.start_btn.disabled = True
        self.pause_btn.text = "Pause"

        if self._event:
            self._event.cancel()
        self._event = Clock.schedule_interval(self._update_timer, 0.1)

    def toggle_pause(self, *args):
        if not self._running:
            return
        if self._paused:
            self._paused = False
            self._seg_start = self._now()
            self.pause_btn.text = "Pause"
            self._event = Clock.schedule_interval(self._update_timer, 0.1)
            self.status_label.text = f"On finish: {self.action_spinner.text}"
        else:
            self._base = self._elapsed()
            self._paused = True
            self.pause_btn.text = "Resume"
            if self._event:
                self._event.cancel()
                self._event = None
            self.status_label.text = (
                f"Paused  |  on finish: {self.action_spinner.text}")

    def reset_timer(self, *args):
        if self._event:
            self._event.cancel()
        self._event = None
        self._base = 0.0
        self._progress = 0.0
        self._paused = False
        self._running = False
        self.time_label.text = "00:00:00"
        self.status_label.text = ""
        self.start_btn.disabled = False
        self.pause_btn.disabled = True
        self.pause_btn.text = "Pause"
        self.reset_btn.disabled = True
        self._draw_progress()

    def _update_timer(self, dt):
        elapsed = self._elapsed()
        self._progress = min(1.0, elapsed / self._duration)
        self._draw_progress()

        remaining = max(0, int(self._duration - elapsed + 0.999))
        h = remaining // 3600
        m = (remaining % 3600) // 60
        s = remaining % 60
        self.time_label.text = f"{h:02d}:{m:02d}:{s:02d}"

        if elapsed >= self._duration:
            if self._event:
                self._event.cancel()
            self._event = None
            self._running = False
            self._base = float(self._duration)
            self.start_btn.disabled = False
            self.pause_btn.disabled = True
            self.reset_btn.disabled = False
            self._on_complete()

    def _on_complete(self):
        # Read NOW, not at Start: the user may have switched the action
        # while the timer was running.
        action = self.action_spinner.text
        self.status_label.text = f"Done!  Action: {action}"

        if action == "Notify only":
            threading.Thread(target=self._notify, daemon=True).start()

        elif action == "Shutdown" and not _IS_ANDROID:
            if sys.platform.startswith("win"):
                os.system("shutdown /s /t 5")
            else:
                os.system("systemctl poweroff")

        elif action == "Suspend" and not _IS_ANDROID:
            if sys.platform.startswith("win"):
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            else:
                os.system("systemctl suspend")

    def _notify(self):
        try:
            import core.notify as notify
            notify.send_notification("Srboli timer", "Time's up!")
        except Exception as e:
            print(f"Srboli timer: notification failed ({e})")

    def _draw_progress(self, *a):
        ca = self.canvas_area
        ca.canvas.clear()
        with ca.canvas:
            w = max(10, ca.width)
            h = ca.height
            x = ca.x
            y = ca.y

            Color(0.18, 0.18, 0.20, 1)
            Rectangle(pos=(x, y), size=(w, h))

            # colour shifts green > yellow > red as it fills
            p = self._progress
            r = min(1.0, p * 2)
            g = min(1.0, (1.0 - p) * 2)
            Color(r, g, 0.15, 1)
            Rectangle(pos=(x, y), size=(w * p, h))
