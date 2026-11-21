# screens/when_done_screen.py - Power Off When Done.
# Watch something that goes quiet when a task ends (a program, uploads, CPU, disk) and
# then shut down / sleep / just notify, after a 60 second countdown you can cancel.
# Desktop only (a phone app can't power the phone off). Logic: core/when_done_core.py.

import threading
import time

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import platform as _platform

from core import theme
from core import when_done_core as core
from screens.scaffold import ToolScreen

ON = (0.2, 0.45, 0.75, 1)
OFF = (0.25, 0.25, 0.25, 1)
GREEN = (0.2, 0.55, 0.2, 1)
RED = (0.7, 0.25, 0.25, 1)
COUNTDOWN = 60
TICK = 2.0
LABELS = {"process": "A program ends", "network": "Uploads / downloads stop",
          "cpu": "CPU gets quiet", "disk": "Disk copying stops"}
HELP = {
    "process": "Pick the program (for example rclone, ffmpeg, an installer). Done when it has exited.",
    "network": "Done when network traffic stays under the limit for the quiet time - "
               "e.g. the Google Drive upload finished.",
    "cpu": "Done when CPU use stays under the limit for the quiet time - rendering, encoding, compiling.",
    "disk": "Done when disk reads+writes stay under the limit for the quiet time - copying files.",
}


class WhenDoneScreen(ToolScreen):
    title = "Power Off When Done"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.kind = "network"
        self.monitor = None
        self.sampler = None
        self._ev = None
        self._count_ev = None
        self._pop = None
        self._ps_error = ""
        root = self.body

        self.help = Label(text="", font_size=sp(12), color=theme.MUTED, size_hint_y=None,
                          height=dp(52), halign="left", valign="middle")
        self.help.bind(size=lambda w, v: setattr(w, "text_size", v))
        tabs = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.kind_btns = {}
        for k in core.KINDS:
            b = Button(text=LABELS[k], font_size=sp(11), background_normal="",
                       background_color=OFF)
            b.bind(on_release=lambda i, kk=k: self.set_kind(kk))
            self.kind_btns[k] = b
            tabs.add_widget(b)
        root.add_widget(tabs)
        root.add_widget(self.help)

        r = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.proc = Spinner(text="(pick a program)", values=[], font_size=sp(12))
        self.refresh_btn = Button(text="Refresh list", size_hint_x=None, width=dp(100),
                                  font_size=sp(12))
        self.refresh_btn.bind(on_release=lambda *a: self.refresh_processes())
        self.limit = TextInput(multiline=False, font_size=sp(12), input_filter="float",
                               hint_text="limit")
        self.limit_lbl = Label(text="", font_size=sp(12), size_hint_x=None, width=dp(50))
        self.quiet = TextInput(multiline=False, font_size=sp(12), input_filter="float",
                               text="3", hint_text="minutes")
        self.quiet_lbl = Label(text="min quiet", font_size=sp(12), size_hint_x=None, width=dp(70))
        self.row = r
        root.add_widget(r)

        r2 = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        r2.add_widget(Label(text="Then:", size_hint_x=None, width=dp(50), font_size=sp(13)))
        self.action = Spinner(text="Shut down", values=list(core.ACTIONS), font_size=sp(13))
        r2.add_widget(self.action)
        root.add_widget(r2)

        self.big = Label(text="", font_size=sp(15), halign="center", valign="middle")
        self.big.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.big)

        self.start_btn = Button(text="Start watching", size_hint_y=None, height=dp(50),
                                background_color=GREEN, font_size=sp(14))
        self.start_btn.bind(on_release=lambda *a: self.toggle())
        root.add_widget(self.start_btn)
        self.note = Label(text=("Nothing happens until the task is really quiet, then a "
                                f"{COUNTDOWN}-second countdown lets you cancel."),
                          font_size=sp(11), color=theme.MUTED, size_hint_y=None, height=dp(34),
                          halign="left", valign="middle")
        self.note.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.note)

        self.set_kind("network")
        if _platform == "android":
            self.big.text = ("A phone app can't switch the phone off.\nUse this on a "
                             "computer (Linux, Windows, macOS).")
            self.start_btn.disabled = True

    # ── choices ─────────────────────────────────────────────────────────
    def set_kind(self, kind):
        self.kind = kind
        for k, b in self.kind_btns.items():
            b.background_color = ON if k == kind else OFF
        self.help.text = HELP[kind]
        self.row.clear_widgets()
        if kind == "process":
            self.row.add_widget(self.proc)
            self.row.add_widget(self.refresh_btn)
            self.refresh_processes()
        else:
            self.limit.text = f"{core.DEFAULTS[kind]:.0f}"
            self.limit_lbl.text = core.UNITS[kind]
            self.row.add_widget(Label(text="quiet below", font_size=sp(12), size_hint_x=None,
                                      width=dp(80)))
            self.row.add_widget(self.limit)
            self.row.add_widget(self.limit_lbl)
            self.row.add_widget(self.quiet)
            self.row.add_widget(self.quiet_lbl)

    def refresh_processes(self):
        try:
            self.proc.values = core.list_processes()
            self._ps_error = ""
        except Exception as e:
            self._ps_error = f"Can't list programs ({e}). Is psutil installed?"
            self.big.text = self._ps_error

    # ── watching ────────────────────────────────────────────────────────
    def toggle(self):
        if self._ev:
            self.stop("Stopped watching.")
        else:
            self.start()

    def start(self):
        try:
            self.sampler = core.Sampler()
        except Exception as e:
            self.big.text = f"Needs psutil ({e})."
            return
        try:
            if self.kind == "process":
                if self.proc.text not in self.proc.values:
                    self.big.text = "Pick a program first."
                    return
                self.monitor = core.Monitor("process", need_active=False)
                self.watched = self.proc.text
            else:
                limit = float(self.limit.text or core.DEFAULTS[self.kind])
                quiet = float(self.quiet.text or 3) * 60
                self.monitor = core.Monitor(self.kind, limit, quiet)
                self.watched = None
        except ValueError:
            self.big.text = "Limit and minutes must be numbers."
            return
        self.sampler.reading(self.kind, name=self.watched)   # first reading primes the rates
        self.start_btn.text = "Stop watching"
        self.start_btn.background_color = RED
        self._ev = Clock.schedule_interval(lambda dt: self.tick(), TICK)
        self.big.text = "Watching..."

    def tick(self, now=None):
        try:
            reading = self.sampler.reading(self.kind, now=now, name=self.watched)
            self.big.text = self.monitor.update(time.monotonic() if now is None else now, reading)
        except Exception as e:
            self.stop(f"Stopped: could not read the system ({e}).")
            return
        if self.monitor.done:
            self._finish()

    def stop(self, msg=""):
        if self._ev:
            self._ev.cancel()
            self._ev = None
        self.start_btn.text = "Start watching"
        self.start_btn.background_color = GREEN
        if msg:
            self.big.text = msg

    # ── finishing ───────────────────────────────────────────────────────
    def _finish(self):
        self.stop()
        action = self.action.text
        threading.Thread(target=self._notify, daemon=True).start()
        if not core.power_command(action):
            self.big.text = "The task is done."
            return
        self._countdown(action)

    def _notify(self):
        try:
            import core.notify as notify
            notify.send_notification("Srboli", "The task is done.")
        except Exception:
            pass

    def _countdown(self, action):
        self._left = COUNTDOWN
        lbl = Label(text="", font_size=sp(16), halign="center")
        cancel = Button(text="Cancel", size_hint_y=None, height=dp(50), background_color=RED)
        lay = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        lay.add_widget(lbl)
        lay.add_widget(cancel)
        self._pop = Popup(title="The task is done", content=lay, size_hint=(0.8, 0.4),
                          auto_dismiss=False)

        def show():
            lbl.text = f"{action} in {self._left} seconds."
            self.big.text = lbl.text

        def tick(dt):
            self._left -= 1
            if self._left <= 0:
                self._cancel_countdown()
                self.big.text = f"{action}..."
                try:
                    core.run_action(action)
                except Exception as e:
                    self.big.text = f"Could not {action.lower()}: {e}"
                return
            show()

        def do_cancel(*a):
            self._cancel_countdown()
            self.big.text = f"Cancelled: the PC stays on."

        cancel.bind(on_release=do_cancel)
        self._tick_fn, self._cancel_fn = tick, do_cancel
        show()
        self._count_ev = Clock.schedule_interval(tick, 1)
        self._pop.open()

    def _cancel_countdown(self):
        if self._count_ev:
            self._count_ev.cancel()
            self._count_ev = None
        if self._pop:
            self._pop.dismiss()
            self._pop = None

    def on_leave(self, *a):
        pass        # keeps watching in the background: that is the point
