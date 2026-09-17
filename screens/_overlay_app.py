# _overlay_app.py — Srboli Stats Overlay
# Separate always-on-top window, its own process.
# FPS: self-computed from this window's own render loop (its own frame
#   timestamps) — NOT read from the main app anymore. This is the
#   overlay's own render rate, a rough reference only — see the caveat
#   in System Stats > Overlay in the main app.
# GPU: reuses sys_info.gpu_summary_line(), the same detection logic the
#   main app's System Stats screen uses (no more duplicated GPU code).
# Ping: own thread, 1-packet ping with 1s timeout.

import sys, os, time, threading, collections

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from kivy.config import Config
Config.set("graphics", "width",          "320")
Config.set("graphics", "height",         "260")
Config.set("graphics", "always_on_top",  "1")
Config.set("graphics", "borderless",     "0")
Config.set("graphics", "resizable",      "1")
Config.set("input",    "mouse",          "mouse,disable_multitouch")
Config.set("kivy",     "exit_on_escape", "1")

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.checkbox import CheckBox
from kivy.uix.button import Button
from kivy.clock import Clock

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import sys_info
    HAS_SYS_INFO = True
except ImportError:
    HAS_SYS_INFO = False

STAT_KEYS = ("CPU", "RAM", "Disk", "GPU", "FPS", "Ping")
SHOW = {"CPU": True, "RAM": True, "Disk": False, "GPU": False,
        "FPS": True, "Ping": True}
ROW_HEIGHT = 26


# ── ping thread ──────────────────────────────────────────────────────────
_ping_ms   = [-1.0]
_ping_lock = threading.Lock()
_ping_run  = [True]


def _ping_once(host="8.8.8.8"):
    if HAS_SYS_INFO:
        return sys_info.do_ping(host)
    return -1.0


def _ping_loop():
    ms = _ping_once()
    with _ping_lock:
        _ping_ms[0] = ms
    while _ping_run[0]:
        time.sleep(3.0)
        if not _ping_run[0]:
            break
        ms = _ping_once()
        with _ping_lock:
            _ping_ms[0] = ms


_pt = threading.Thread(target=_ping_loop, daemon=True)
_pt.start()


class OverlayApp(App):
    def build(self):
        self.title = "Srboli Stats"
        self._collapsed = False
        self._frame_times = collections.deque(maxlen=30)

        root = BoxLayout(orientation="vertical", padding=5, spacing=4)

        # ── collapse button for the checkbox strip (saves vertical space
        # while this is left open on top of whatever's being tested) ─────
        top_row = BoxLayout(size_hint_y=None, height=24, spacing=4)
        self._collapse_btn = Button(text="\u25b2 hide options",
                                    size_hint_x=None, width=110, font_size=10)
        self._collapse_btn.bind(on_release=self._toggle_collapse)
        top_row.add_widget(self._collapse_btn)
        root.add_widget(top_row)

        self._tog = GridLayout(cols=12, size_hint_y=None, height=26, spacing=2)
        self._checkboxes = {}
        for k in STAT_KEYS:
            cb = CheckBox(active=SHOW[k], size_hint=(None, None), size=(20, 20))
            cb.bind(active=lambda inst, v, key=k: self._set_show(key, v))
            self._checkboxes[k] = cb
            self._tog.add_widget(cb)
            self._tog.add_widget(Label(text=k, font_size=10,
                                       size_hint_x=None, width=32))
        root.add_widget(self._tog)

        # ── stat rows — built once; toggled by height+opacity so an
        # unchecked stat is actually gone (no space taken, no stale
        # frozen text left behind, unlike before) ──────────────────────
        self._lbls = {}
        self._rows_box = BoxLayout(orientation="vertical", size_hint_y=None)
        self._rows_box.bind(minimum_height=self._rows_box.setter("height"))
        for k in STAT_KEYS:
            lbl = Label(text=f"{k}: --", font_size=13, halign="left",
                       size_hint_y=None,
                       height=ROW_HEIGHT if SHOW[k] else 0,
                       opacity=1 if SHOW[k] else 0)
            lbl.bind(size=lbl.setter("text_size"))
            self._lbls[k] = lbl
            self._rows_box.add_widget(lbl)
        root.add_widget(self._rows_box)

        self._status = Label(text="Overlay running", font_size=10,
                             size_hint_y=None, height=20,
                             color=(0.5, 0.7, 0.5, 1))
        root.add_widget(self._status)

        Clock.schedule_interval(self._tick, 1.0)
        Clock.schedule_interval(self._fps_sample, 0)  # every rendered frame
        return root

    # ── collapse/expand the checkbox strip ──────────────────────────────
    def _toggle_collapse(self, *a):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._tog.height   = 0
            self._tog.opacity  = 0
            self._tog.disabled = True
            self._collapse_btn.text = "\u25bc show options"
        else:
            self._tog.height   = 26
            self._tog.opacity  = 1
            self._tog.disabled = False
            self._collapse_btn.text = "\u25b2 hide options"

    # ── actually hide a row when unchecked (previously it just stopped
    # updating and sat there with stale text, still taking up space) ────
    def _set_show(self, key, value):
        SHOW[key] = value
        lbl = self._lbls[key]
        if value:
            lbl.height  = ROW_HEIGHT
            lbl.opacity = 1
        else:
            lbl.height  = 0
            lbl.opacity = 0
            lbl.text    = f"{key}: --"

    def _fps_sample(self, dt):
        self._frame_times.append(time.monotonic())

    def _own_fps(self):
        times = list(self._frame_times)
        if len(times) < 2:
            return 0.0
        elapsed = times[-1] - times[0]
        return (len(times) - 1) / elapsed if elapsed > 0 else 0.0

    def _tick(self, dt):
        if not HAS_PSUTIL:
            for k, lbl in self._lbls.items():
                if SHOW[k]:
                    lbl.text = "psutil missing - run: python3 -m pip install psutil"
            return

        try:
            if SHOW.get("CPU"):
                cpu = psutil.cpu_percent()
                self._lbls["CPU"].text = f"CPU: {cpu:.0f}%"

            if SHOW.get("RAM"):
                vm = psutil.virtual_memory()
                self._lbls["RAM"].text = (
                    f"RAM: {vm.percent:.0f}%  "
                    f"{vm.used/1e9:.1f}/{vm.total/1e9:.1f} GB")

            if SHOW.get("Disk"):
                parts = psutil.disk_partitions(all=False)
                if parts:
                    u = psutil.disk_usage(parts[0].mountpoint)
                    self._lbls["Disk"].text = (
                        f"Disk: {u.percent:.0f}%  "
                        f"{u.used/1e9:.1f}/{u.total/1e9:.1f} GB")

            if SHOW.get("GPU"):
                if HAS_SYS_INFO:
                    self._lbls["GPU"].text = f"GPU: {sys_info.gpu_summary_line()}"
                else:
                    self._lbls["GPU"].text = "GPU: unavailable"

            if SHOW.get("FPS"):
                fps = self._own_fps()
                self._lbls["FPS"].text = f"FPS: {fps:.0f} (overlay, approx)"

            if SHOW.get("Ping"):
                with _ping_lock:
                    ms = _ping_ms[0]
                if ms < 0:
                    self._lbls["Ping"].text = "Ping: measuring..."
                else:
                    self._lbls["Ping"].text = f"Ping: {ms:.0f} ms"

            self._status.text = f"Updated {time.strftime('%H:%M:%S')}"

        except Exception as e:
            self._status.text = f"Error: {e}"

    def on_stop(self):
        _ping_run[0] = False


OverlayApp().run()
