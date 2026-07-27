# screens/converted/loading_timer_screen.py
# Cross-platform: Windows shutdown + Linux shutdown/suspend

import sys
import os
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle


class LoadingTimerScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation="vertical", padding=20, spacing=12)

        # ── title ──
        layout.add_widget(Label(text="[b]Loading / Timer[/b]", markup=True,
                                size_hint_y=None, height=36, font_size=18))

        # ── time inputs ──
        time_layout = BoxLayout(orientation="horizontal", spacing=10,
                                size_hint_y=None, height=44)
        for attr, hint in (("hours_input", "Hours"), ("minutes_input", "Minutes"),
                           ("seconds_input", "Seconds")):
            ti = TextInput(hint_text=hint, multiline=False, input_filter="int",
                           halign="center")
            setattr(self, attr, ti)
            time_layout.add_widget(ti)
        layout.add_widget(time_layout)

        # ── preset buttons ──
        presets = BoxLayout(size_hint_y=None, height=36, spacing=6)
        for label, s in (("5 min", 300), ("10 min", 600),
                         ("30 min", 1800), ("1 hr", 3600)):
            b = Button(text=label, font_size=12)
            b.bind(on_release=lambda inst, sec=s: self._apply_preset(sec))
            presets.add_widget(b)
        layout.add_widget(presets)

        # ── on-complete action ──
        action_row = BoxLayout(size_hint_y=None, height=36, spacing=10)
        action_row.add_widget(Label(text="On complete:", size_hint_x=None,
                                    width=110, font_size=13))
        self.action_spinner = Spinner(
            text="Nothing",
            values=("Nothing", "Shutdown", "Suspend", "Notify only"),
            size_hint_x=0.5, font_size=13,
        )
        action_row.add_widget(self.action_spinner)
        layout.add_widget(action_row)

        # ── start / pause / reset ──
        ctrl = BoxLayout(size_hint_y=None, height=44, spacing=8)
        self.start_btn = Button(text=">  Start")
        self.start_btn.bind(on_release=self.start_timer)
        self.pause_btn = Button(text="||  Pause", disabled=True)
        self.pause_btn.bind(on_release=self.toggle_pause)
        self.reset_btn = Button(text="↺  Reset", disabled=True)
        self.reset_btn.bind(on_release=self.reset_timer)
        for b in (self.start_btn, self.pause_btn, self.reset_btn):
            ctrl.add_widget(b)
        layout.add_widget(ctrl)

        # ── time remaining ──
        self.time_label = Label(text="00:00:00", font_size=32,
                                size_hint_y=None, height=48)
        layout.add_widget(self.time_label)

        # ── progress bar ──
        self.canvas_area = BoxLayout(size_hint_y=None, height=22)
        layout.add_widget(self.canvas_area)

        # ── status message ──
        self.status_label = Label(text="", font_size=13,
                                  size_hint_y=None, height=28)
        layout.add_widget(self.status_label)

        # ── back ──
        back = Button(text="< Back", size_hint_y=None, height=44)
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "dashboard"))
        layout.add_widget(back)

        self.add_widget(layout)

        # internal state
        self._progress = 0.0
        self._duration = 0
        self._elapsed = 0.0
        self._event = None
        self._paused = False

    # ── preset helper ────────────────────────────────────────────────────────
    def _apply_preset(self, total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        self.hours_input.text   = str(h) if h else ""
        self.minutes_input.text = str(m) if m else ""
        self.seconds_input.text = str(s) if s else ""

    # ── timer control ────────────────────────────────────────────────────────
    def start_timer(self, *args):
        h = int(self.hours_input.text)   if self.hours_input.text.isdigit()   else 0
        m = int(self.minutes_input.text) if self.minutes_input.text.isdigit() else 0
        s = int(self.seconds_input.text) if self.seconds_input.text.isdigit() else 0
        self._duration = h * 3600 + m * 60 + s

        if self._duration <= 0:
            self.status_label.text = "⚠  Enter a valid time first."
            return

        self._elapsed = 0.0
        self._progress = 0.0
        self._paused = False
        self.status_label.text = ""
        self.pause_btn.disabled = False
        self.reset_btn.disabled = False
        self.start_btn.disabled = True
        self.pause_btn.text = "||  Pause"

        if self._event:
            Clock.unschedule(self._event)
        self._event = Clock.schedule_interval(self._update_timer, 0.1)

    def toggle_pause(self, *args):
        if self._paused:
            self._paused = False
            self.pause_btn.text = "||  Pause"
            self._event = Clock.schedule_interval(self._update_timer, 0.1)
            self.status_label.text = ""
        else:
            self._paused = True
            self.pause_btn.text = ">  Resume"
            if self._event:
                Clock.unschedule(self._event)
            self.status_label.text = "Paused"

    def reset_timer(self, *args):
        if self._event:
            Clock.unschedule(self._event)
        self._event = None
        self._elapsed = 0.0
        self._progress = 0.0
        self._paused = False
        self.time_label.text = "00:00:00"
        self.status_label.text = ""
        self.start_btn.disabled = False
        self.pause_btn.disabled = True
        self.pause_btn.text = "||  Pause"
        self.reset_btn.disabled = True
        self._draw_progress()

    def _update_timer(self, dt):
        self._elapsed += dt
        self._progress = min(1.0, self._elapsed / self._duration)
        self._draw_progress()

        remaining = max(0, int(self._duration - self._elapsed))
        h = remaining // 3600
        m = (remaining % 3600) // 60
        s = remaining % 60
        self.time_label.text = f"{h:02d}:{m:02d}:{s:02d}"

        if self._elapsed >= self._duration:
            Clock.unschedule(self._event)
            self._event = None
            self.start_btn.disabled = False
            self.pause_btn.disabled = True
            self.reset_btn.disabled = False
            self._on_complete()

    def _on_complete(self):
        action = self.action_spinner.text
        self.status_label.text = f"OK  Done! Action: {action}"

        if action == "Shutdown":
            if sys.platform.startswith("win"):
                os.system("shutdown /s /t 5")
            else:
                os.system("systemctl poweroff")

        elif action == "Suspend":
            if sys.platform.startswith("win"):
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            else:
                os.system("systemctl suspend")

        # "Notify only" and "Nothing" just update the label (already done above)

    def _draw_progress(self, *a):
        self.canvas_area.canvas.clear()
        with self.canvas_area.canvas:
            w = max(10, self.canvas_area.width - 20)
            h = self.canvas_area.height
            x = self.canvas_area.x + 10
            y = self.canvas_area.y

            Color(0.18, 0.18, 0.20, 1)
            Rectangle(pos=(x, y), size=(w, h))

            # colour shifts green > yellow > red as it fills
            p = self._progress
            r = min(1.0, p * 2)
            g = min(1.0, (1.0 - p) * 2)
            Color(r, g, 0.15, 1)
            Rectangle(pos=(x, y), size=(w * p, h))
