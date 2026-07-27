# _overlay_app.py — Srboli Stats Overlay
# Separate always-on-top window.
# FPS: read from .srboli_overlay_data.json (written by main app every second)
# Ping: own thread, 1-packet ping with 1s timeout

import sys, os, time, json, threading, re, subprocess, collections

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_SHARED_FILE = os.path.join(_SCRIPT_DIR, ".srboli_overlay_data.json")

from kivy.config import Config
Config.set("graphics", "width",          "320")
Config.set("graphics", "height",         "230")
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
from kivy.clock import Clock

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

SHOW = {"CPU": True, "RAM": True, "Disk": False, "FPS": True, "Ping": True}

# ── ping thread ───────────────────────────────────────────────────────────────
_ping_ms  = [-1.0]
_ping_lock = threading.Lock()
_ping_run  = [True]

def _ping_once(host="8.8.8.8"):
    try:
        # Use -W 1 for 1-second timeout so it doesn't hang
        if sys.platform.startswith("win"):
            cmd = ["ping", "-n", "1", "-w", "1000", host]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", host]
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=3
        ).decode(errors="replace")
        m = re.search(r"time[=<](\d+\.?\d*)\s*ms", out)
        if m:
            return float(m.group(1))
    except subprocess.TimeoutExpired:
        return -1.0
    except Exception:
        pass
    return -1.0

def _ping_loop():
    # do first ping immediately
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

# start ping thread immediately
_pt = threading.Thread(target=_ping_loop, daemon=True)
_pt.start()


class OverlayApp(App):
    def build(self):
        self.title = "Srboli Stats"
        root = BoxLayout(orientation="vertical", padding=5, spacing=4)

        # toggle row
        tog = GridLayout(cols=10, size_hint_y=None, height=26, spacing=2)
        for k in ("CPU", "RAM", "Disk", "FPS", "Ping"):
            cb = CheckBox(active=SHOW[k], size_hint=(None, None),
                          size=(20, 20))
            cb.bind(active=lambda inst, v, key=k: SHOW.update({key: v}))
            tog.add_widget(cb)
            tog.add_widget(Label(text=k, font_size=10,
                                 size_hint_x=None, width=32))
        root.add_widget(tog)

        # stat labels
        self._lbls = {}
        for k in ("CPU", "RAM", "Disk", "FPS", "Ping"):
            lbl = Label(text=f"{k}: --", font_size=13,
                        halign="left", size_hint_y=None, height=28)
            lbl.bind(size=lbl.setter("text_size"))
            self._lbls[k] = lbl
            root.add_widget(lbl)

        self._status = Label(text="Overlay running", font_size=10,
                             size_hint_y=None, height=20,
                             color=(0.5, 0.7, 0.5, 1))
        root.add_widget(self._status)

        Clock.schedule_interval(self._tick, 1.0)
        return root

    def _tick(self, dt):
        # read FPS + ping from shared file
        shared = {}
        try:
            if os.path.exists(_SHARED_FILE):
                with open(_SHARED_FILE, encoding="utf-8") as f:
                    shared = json.load(f)
        except Exception:
            pass

        if not HAS_PSUTIL:
            for lbl in self._lbls.values():
                lbl.text = "psutil missing"
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

            if SHOW.get("FPS"):
                fps = shared.get("fps", None)
                age = time.time() - shared.get("ts", 0)
                if fps is not None and age < 10:
                    self._lbls["FPS"].text = f"FPS: {fps:.0f}"
                else:
                    self._lbls["FPS"].text = "FPS: (main app not running)"

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
