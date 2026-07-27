# screens/basic_tools_screen.py
# Basic Tools: Clock, Stopwatch, Alarm, Real Calculator — all in one screen

import time
import math

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard

try:
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False


def _beep():
    """Play a short beep using pygame if available, else print bell."""
    if HAS_PYGAME:
        try:
            # generate a simple sine wave beep
            import numpy as np
            sample_rate = 44100
            duration    = 0.4
            freq        = 880
            t    = np.linspace(0, duration, int(sample_rate * duration))
            wave = (np.sin(2 * math.pi * freq * t) * 32767).astype("int16")
            stereo = np.column_stack([wave, wave])
            sound  = pygame.sndarray.make_sound(stereo)
            sound.play()
            return
        except Exception:
            pass
    print("\a")   # terminal bell fallback


class BasicToolsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)

        # stopwatch state
        self._sw_running  = False
        self._sw_start    = 0.0
        self._sw_elapsed  = 0.0
        self._sw_laps     = []
        self._sw_ev       = None

        # alarm state
        self._alarm_ev    = None
        self._alarm_secs  = 0
        self._alarm_remain= 0

        # clock update
        self._clock_ev    = None

        # calc state
        self._calc_expr   = ""
        self._calc_result = ""

        root = BoxLayout(orientation="vertical", padding=5, spacing=5)

        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(42))
        self.tabs.add_widget(self._clock_tab())
        self.tabs.add_widget(self._stopwatch_tab())
        self.tabs.add_widget(self._alarm_tab())
        self.tabs.add_widget(self._calc_tab())
        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    # ════════════════════════════════════════════════════════════════════════
    # CLOCK TAB
    # ════════════════════════════════════════════════════════════════════════
    def _clock_tab(self):
        tab = TabbedPanelItem(text=" Clock")
        layout = BoxLayout(orientation="vertical", padding=16, spacing=10)

        self._time_lbl = Label(text="00:00:00", font_size=64, bold=True,
                               size_hint_y=None, height=dp(90))
        self._date_lbl = Label(text="", font_size=20,
                               size_hint_y=None, height=dp(36))
        self._week_lbl = Label(text="", font_size=14,
                               size_hint_y=None, height=dp(26),
                               color=(0.6, 0.8, 1, 1))

        # 12 / 24 hour toggle
        fmt_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=8)
        self._fmt_24 = ToggleButton(text="24h", state="down",
                                    size_hint_x=None, width=dp(70),
                                    font_size=13)
        self._fmt_12 = ToggleButton(text="12h", size_hint_x=None,
                                    width=dp(70), font_size=13)
        self._fmt_24.bind(on_release=lambda *a: self._set_fmt(24))
        self._fmt_12.bind(on_release=lambda *a: self._set_fmt(12))
        fmt_row.add_widget(self._fmt_24)
        fmt_row.add_widget(self._fmt_12)
        fmt_row.add_widget(Label())

        self._clock_fmt = 24

        for w in (self._time_lbl, self._date_lbl,
                  self._week_lbl, fmt_row):
            layout.add_widget(w)

        layout.add_widget(Label())   # spacer
        tab.add_widget(layout)
        return tab

    def _set_fmt(self, fmt):
        self._clock_fmt = fmt

    def _update_clock(self, dt=None):
        t   = time.localtime()
        day = ["Monday","Tuesday","Wednesday","Thursday",
               "Friday","Saturday","Sunday"][t.tm_wday]
        mon = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"][t.tm_mon-1]

        if self._clock_fmt == 12:
            h  = t.tm_hour % 12 or 12
            am = "AM" if t.tm_hour < 12 else "PM"
            self._time_lbl.text = f"{h:02d}:{t.tm_min:02d}:{t.tm_sec:02d} {am}"
        else:
            self._time_lbl.text = f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

        self._date_lbl.text = f"{day}, {t.tm_mday} {mon} {t.tm_year}"
        week = t.tm_yday // 7 + 1
        self._week_lbl.text = f"Week {week} of {t.tm_year}  •  Day {t.tm_yday}"

    # ════════════════════════════════════════════════════════════════════════
    # STOPWATCH TAB
    # ════════════════════════════════════════════════════════════════════════
    def _stopwatch_tab(self):
        tab = TabbedPanelItem(text=" Stopwatch")
        layout = BoxLayout(orientation="vertical", padding=10, spacing=8)

        self._sw_lbl = Label(text="00:00.000", font_size=52, bold=True,
                             size_hint_y=None, height=dp(80))
        layout.add_widget(self._sw_lbl)

        ctrl = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
        self._sw_start_btn = Button(text="> Start", font_size=16)
        self._sw_start_btn.bind(on_release=self._sw_toggle)
        lap_btn   = Button(text="Lap Lap",   font_size=16)
        lap_btn.bind(on_release=self._sw_lap)
        reset_btn = Button(text="↺ Reset",  font_size=16)
        reset_btn.bind(on_release=self._sw_reset)
        copy_btn  = Button(text="Copy Copy",  font_size=14,
                           size_hint_x=None, width=dp(80))
        copy_btn.bind(on_release=lambda *a: Clipboard.copy(self._sw_lbl.text))
        for b in (self._sw_start_btn, lap_btn, reset_btn, copy_btn):
            ctrl.add_widget(b)
        layout.add_widget(ctrl)

        layout.add_widget(Label(text="Laps:", size_hint_y=None,
                                height=dp(22), font_size=13))
        sv = ScrollView(size_hint=(1, 0.45))
        self._lap_grid = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self._lap_grid.bind(minimum_height=self._lap_grid.setter("height"))
        sv.add_widget(self._lap_grid)
        layout.add_widget(sv)

        tab.add_widget(layout)
        return tab

    def _sw_toggle(self, *a):
        if self._sw_running:
            self._sw_elapsed += time.monotonic() - self._sw_start
            self._sw_running = False
            if self._sw_ev:
                self._sw_ev.cancel()
                self._sw_ev = None
            self._sw_start_btn.text = "> Resume"
        else:
            self._sw_start   = time.monotonic()
            self._sw_running = True
            self._sw_ev = Clock.schedule_interval(self._sw_tick, 0.033)
            self._sw_start_btn.text = "|| Pause"

    def _sw_tick(self, dt):
        elapsed = self._sw_elapsed + (time.monotonic() - self._sw_start)
        self._sw_lbl.text = self._fmt_sw(elapsed)

    def _sw_lap(self, *a):
        if not self._sw_running and self._sw_elapsed == 0:
            return
        elapsed = self._sw_elapsed + (
            (time.monotonic() - self._sw_start) if self._sw_running else 0)
        n = len(self._sw_laps) + 1
        t = self._fmt_sw(elapsed)
        self._sw_laps.append(t)
        lbl = Label(text=f"Lap {n:3d}  {t}", size_hint_y=None,
                    height=dp(24), font_size=12, halign="left")
        lbl.bind(size=lbl.setter("text_size"))
        self._lap_grid.add_widget(lbl)

    def _sw_reset(self, *a):
        if self._sw_ev:
            self._sw_ev.cancel()
            self._sw_ev = None
        self._sw_running  = False
        self._sw_elapsed  = 0.0
        self._sw_laps     = []
        self._sw_lbl.text = "00:00.000"
        self._sw_start_btn.text = "> Start"
        self._lap_grid.clear_widgets()

    @staticmethod
    def _fmt_sw(s):
        mins = int(s) // 60
        secs = int(s) % 60
        ms   = int((s - int(s)) * 1000)
        return f"{mins:02d}:{secs:02d}.{ms:03d}"

    # ════════════════════════════════════════════════════════════════════════
    # ALARM TAB
    # ════════════════════════════════════════════════════════════════════════
    def _alarm_tab(self):
        tab = TabbedPanelItem(text=" Alarm")
        layout = BoxLayout(orientation="vertical", padding=12, spacing=8)

        layout.add_widget(Label(text="[b]Set alarm time[/b]", markup=True,
                                size_hint_y=None, height=dp(28), font_size=15))

        # H:M:S inputs
        time_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        self._al_h = TextInput(hint_text="H",  multiline=False,
                               input_filter="int", font_size=16)
        self._al_m = TextInput(hint_text="MM", multiline=False,
                               input_filter="int", font_size=16)
        self._al_s = TextInput(hint_text="SS", multiline=False,
                               input_filter="int", font_size=16)
        for lbl, ti in (("h:", self._al_h),("m:", self._al_m),("s:", self._al_s)):
            time_row.add_widget(Label(text=lbl, size_hint_x=None,
                                     width=dp(22), font_size=14))
            time_row.add_widget(ti)
        layout.add_widget(time_row)

        # quick presets
        pre_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=5)
        for lbl, h, m, s in [("5m",0,5,0),("10m",0,10,0),
                               ("30m",0,30,0),("1h",1,0,0)]:
            b = Button(text=lbl, font_size=13)
            b.bind(on_release=lambda inst, hh=h, mm=m, ss=s:
                   self._set_alarm_preset(hh, mm, ss))
            pre_row.add_widget(b)
        layout.add_widget(pre_row)

        # label input
        lbl_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=6)
        lbl_row.add_widget(Label(text="Label:", size_hint_x=None,
                                 width=dp(54), font_size=13))
        self._al_label = TextInput(hint_text="Wake up!",
                                   multiline=False, font_size=13)
        lbl_row.add_widget(self._al_label)
        layout.add_widget(lbl_row)

        ctrl = BoxLayout(size_hint_y=None, height=dp(48), spacing=8)
        self._al_start_btn = Button(text=" Start Alarm", font_size=15)
        self._al_start_btn.bind(on_release=self._start_alarm)
        self._al_stop_btn  = Button(text="[] Stop", font_size=15,
                                    disabled=True)
        self._al_stop_btn.bind(on_release=self._stop_alarm)
        ctrl.add_widget(self._al_start_btn)
        ctrl.add_widget(self._al_stop_btn)
        layout.add_widget(ctrl)

        self._al_display = Label(text="—", font_size=40, bold=True,
                                 size_hint_y=None, height=dp(70))
        self._al_status  = Label(text="", font_size=13,
                                 size_hint_y=None, height=dp(28),
                                 color=(0.4, 1, 0.4, 1))
        layout.add_widget(self._al_display)
        layout.add_widget(self._al_status)

        tab.add_widget(layout)
        return tab

    def _set_alarm_preset(self, h, m, s):
        self._al_h.text = str(h) if h else ""
        self._al_m.text = str(m) if m else ""
        self._al_s.text = str(s) if s else ""

    def _start_alarm(self, *a):
        try:
            h = int(self._al_h.text) if self._al_h.text.strip() else 0
            m = int(self._al_m.text) if self._al_m.text.strip() else 0
            s = int(self._al_s.text) if self._al_s.text.strip() else 0
        except ValueError:
            self._al_status.text = "Invalid time."
            return
        total = h*3600 + m*60 + s
        if total <= 0:
            self._al_status.text = "Enter a time > 0."
            return
        self._alarm_secs   = total
        self._alarm_remain = total
        self._al_start_btn.disabled = True
        self._al_stop_btn.disabled  = False
        self._al_status.text = f"Alarm set for {self._fmt_alarm(total)}"
        if self._alarm_ev:
            self._alarm_ev.cancel()
        self._alarm_ev = Clock.schedule_interval(self._alarm_tick, 1.0)

    def _stop_alarm(self, *a):
        if self._alarm_ev:
            self._alarm_ev.cancel()
            self._alarm_ev = None
        self._al_display.text       = "—"
        self._al_status.text        = "Alarm stopped."
        self._al_start_btn.disabled = False
        self._al_stop_btn.disabled  = True

    def _alarm_tick(self, dt):
        self._alarm_remain -= 1
        self._al_display.text = self._fmt_alarm(self._alarm_remain)
        if self._alarm_remain <= 0:
            if self._alarm_ev:
                self._alarm_ev.cancel()
                self._alarm_ev = None
            label = self._al_label.text.strip() or "Time's up!"
            self._al_status.text = f"🔔 {label}"
            self._al_display.text = "🔔"
            self._al_start_btn.disabled = False
            self._al_stop_btn.disabled  = True
            # beep 3 times
            for i in range(3):
                Clock.schedule_once(lambda dt: _beep(), i * 0.6)

    @staticmethod
    def _fmt_alarm(s):
        h = s // 3600; m = (s % 3600) // 60; sc = s % 60
        return f"{h:02d}:{m:02d}:{sc:02d}"

    # ════════════════════════════════════════════════════════════════════════
    # REAL CALCULATOR TAB
    # ════════════════════════════════════════════════════════════════════════
    def _calc_tab(self):
        tab = TabbedPanelItem(text=" Calc")
        layout = BoxLayout(orientation="vertical", padding=8, spacing=6)

        # expression display
        self._calc_expr_lbl = Label(
            text="", font_size=13, halign="right", valign="middle",
            size_hint_y=None, height=dp(24),
            color=(0.55, 0.55, 0.55, 1))
        self._calc_expr_lbl.bind(size=self._calc_expr_lbl.setter("text_size"))
        layout.add_widget(self._calc_expr_lbl)

        self._calc_disp = Label(
            text="0", font_size=34, bold=True,
            halign="right", valign="middle",
            size_hint_y=None, height=dp(54))
        self._calc_disp.bind(size=self._calc_disp.setter("text_size"))
        layout.add_widget(self._calc_disp)

        # history
        self._calc_hist = Label(text="", font_size=11,
                                size_hint_y=None, height=dp(18),
                                halign="right", color=(0.5,0.7,0.5,1))
        self._calc_hist.bind(size=self._calc_hist.setter("text_size"))
        layout.add_widget(self._calc_hist)

        # buttons
        grid = GridLayout(cols=5, spacing=4, size_hint_y=0.72)
        calc_btns = [
            ("C", self._calc_clear,   (0.75, 0.2,  0.2,  1)),
            ("Del", self._calc_back,    (0.5,  0.3,  0.1,  1)),
            ("%", lambda *a: self._calc_op("%"),  None),
            ("√", lambda *a: self._calc_sqrt(),   (0.2, 0.5, 0.7, 1)),
            ("x²",lambda *a: self._calc_sq(),     (0.2, 0.5, 0.7, 1)),

            ("7", lambda *a: self._calc_digit("7"), None),
            ("8", lambda *a: self._calc_digit("8"), None),
            ("9", lambda *a: self._calc_digit("9"), None),
            ("÷", lambda *a: self._calc_op("/"),   (0.25,0.55,0.8,1)),
            ("1/x",lambda *a: self._calc_inv(),    (0.2, 0.5, 0.7, 1)),

            ("4", lambda *a: self._calc_digit("4"), None),
            ("5", lambda *a: self._calc_digit("5"), None),
            ("6", lambda *a: self._calc_digit("6"), None),
            ("×", lambda *a: self._calc_op("*"),   (0.25,0.55,0.8,1)),
            ("π", lambda *a: self._calc_const(math.pi), (0.3,0.6,0.3,1)),

            ("1", lambda *a: self._calc_digit("1"), None),
            ("2", lambda *a: self._calc_digit("2"), None),
            ("3", lambda *a: self._calc_digit("3"), None),
            ("−", lambda *a: self._calc_op("-"),   (0.25,0.55,0.8,1)),
            ("e", lambda *a: self._calc_const(math.e),  (0.3,0.6,0.3,1)),

            ("0", lambda *a: self._calc_digit("0"), None),
            (".", lambda *a: self._calc_digit("."), None),
            ("+/-", self._calc_negate,  None),
            ("+", lambda *a: self._calc_op("+"),   (0.25,0.55,0.8,1)),
            ("=", self._calc_equals,  (0.2, 0.65, 0.25, 1)),
        ]
        for text, cb, color in calc_btns:
            kw = {"text": text, "font_size": 18}
            if color:
                kw["background_color"] = color
            b = Button(**kw)
            b.bind(on_release=cb)
            grid.add_widget(b)
        layout.add_widget(grid)

        copy_btn = Button(text="Copy Copy result", size_hint_y=None,
                          height=dp(36), font_size=13)
        copy_btn.bind(on_release=lambda *a: Clipboard.copy(self._calc_disp.text))
        layout.add_widget(copy_btn)

        tab.add_widget(layout)
        return tab

    def _calc_digit(self, d):
        cur = self._calc_disp.text
        # if we just finished an operation, start fresh number
        if self._calc_result or cur in ("0", "Error"):
            self._calc_disp.text = d
            self._calc_result = ""
        else:
            self._calc_disp.text = cur + d

    def _calc_op(self, op):
        # save left operand + operator; clear display for right operand
        left = self._calc_disp.text
        self._calc_expr = left + op
        self._calc_expr_lbl.text = left + " " + op
        self._calc_disp.text = "0"
        self._calc_result = ""

    def _calc_clear(self, *a):
        self._calc_expr      = ""
        self._calc_result    = ""
        self._calc_disp.text = "0"
        self._calc_expr_lbl.text = ""

    def _calc_back(self, *a):
        cur = self._calc_disp.text
        self._calc_disp.text = cur[:-1] if len(cur) > 1 else "0"
        self._calc_expr = self._calc_disp.text

    def _calc_negate(self, *a):
        try:
            v = float(self._calc_disp.text)
            self._calc_disp.text = str(-v)
            self._calc_expr = self._calc_disp.text
        except Exception:
            pass

    def _calc_sqrt(self, *a):
        try:
            v = float(self._calc_disp.text)
            r = math.sqrt(v)
            self._calc_expr_lbl.text = f"√({v})"
            self._calc_disp.text = self._fmt_num(r)
            self._calc_hist.text = f"√{v} = {self._fmt_num(r)}"
        except Exception:
            self._calc_disp.text = "Error"

    def _calc_sq(self, *a):
        try:
            v = float(self._calc_disp.text)
            r = v * v
            self._calc_expr_lbl.text = f"({v})²"
            self._calc_disp.text = self._fmt_num(r)
            self._calc_hist.text = f"{v}² = {self._fmt_num(r)}"
        except Exception:
            self._calc_disp.text = "Error"

    def _calc_inv(self, *a):
        try:
            v = float(self._calc_disp.text)
            r = 1.0 / v
            self._calc_expr_lbl.text = f"1/({v})"
            self._calc_disp.text = self._fmt_num(r)
        except Exception:
            self._calc_disp.text = "Error"

    def _calc_const(self, val):
        self._calc_disp.text = self._fmt_num(val)
        self._calc_expr = self._fmt_num(val)

    def _calc_equals(self, *a):
        right = self._calc_disp.text
        expr  = self._calc_expr + right
        try:
            import re
            safe   = re.sub(r"[^0-9+\-*/().eE%]", "", expr)
            result = eval(safe)
            self._calc_expr_lbl.text = expr + " ="
            self._calc_hist.text     = f"{expr} = {self._fmt_num(result)}"
            self._calc_disp.text     = self._fmt_num(result)
            self._calc_expr          = ""
            self._calc_result        = self._fmt_num(result)  # flag: result shown
        except Exception:
            self._calc_disp.text = "Error"
            self._calc_expr      = ""
            self._calc_result    = ""

    @staticmethod
    def _fmt_num(v):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return f"{v:.10g}"

    # ════════════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ════════════════════════════════════════════════════════════════════════
    def on_enter(self, *a):
        self._update_clock()
        self._clock_ev = Clock.schedule_interval(
            lambda dt: self._update_clock(), 1.0)

    def on_leave(self, *a):
        if self._clock_ev:
            self._clock_ev.cancel()
            self._clock_ev = None

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
