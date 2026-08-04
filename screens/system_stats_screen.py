# screens/system_stats_screen.py
# System Stats — CPU/RAM/Disk/GPU text + live FPS & Ping graphs
# Overlay: real separate window via subprocess (doesn't freeze main app)

import sys, os, re, time, json, subprocess, threading, collections

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.scrollview import ScrollView
from kivy.uix.checkbox import CheckBox
from kivy.graphics import Color, Line, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import GPUtil
    HAS_GPUTIL = True
except ImportError:
    HAS_GPUTIL = False

try:
    from ping3 import ping as ping3_ping
    HAS_PING3 = True
except ImportError:
    HAS_PING3 = False

HISTORY = 60
PING_HOST_DEFAULT = "8.8.8.8"


class GraphWidget(BoxLayout):
    def __init__(self, label="", unit="", max_val=100.0,
                 color=(0.3, 0.8, 0.4), **kw):
        super().__init__(orientation="vertical", **kw)
        self.max_val = max_val
        self.unit    = unit
        self.color   = color
        self._history = collections.deque([0.0] * HISTORY, maxlen=HISTORY)

        hdr = BoxLayout(size_hint_y=None, height=dp(22))
        self._title_lbl = Label(text=label, font_size=12, halign="left",
                                size_hint_x=0.6)
        self._val_lbl   = Label(text="--",  font_size=12, halign="right",
                                size_hint_x=0.4)
        hdr.add_widget(self._title_lbl)
        hdr.add_widget(self._val_lbl)
        self.add_widget(hdr)

        self._ga = BoxLayout()
        self._ga.bind(pos=self._redraw, size=self._redraw)
        self.add_widget(self._ga)

    def push(self, value, label_override=None):
        self._history.append(float(value))
        self._val_lbl.text = (label_override if label_override is not None
                              else f"{value:.1f} {self.unit}")
        self._redraw()

    def _redraw(self, *a):
        ga = self._ga
        ga.canvas.clear()
        w, h = ga.width, ga.height
        if w < 2 or h < 2:
            return
        vals = list(self._history)
        step = w / max(len(vals) - 1, 1)
        with ga.canvas:
            Color(0.12, 0.12, 0.14, 1)
            Rectangle(pos=ga.pos, size=(w, h))
            Color(0.25, 0.25, 0.28, 1)
            for pct in (0.25, 0.50, 0.75):
                y = ga.y + h * pct
                Line(points=[ga.x, y, ga.x + w, y], width=0.8)
            Color(*self.color, 1)
            pts = []
            for i, v in enumerate(vals):
                pts += [ga.x + i*step,
                        ga.y + (min(v, self.max_val)/self.max_val)*h]
            if len(pts) >= 4:
                Line(points=pts, width=1.4)


def _do_ping(host) -> float:
    if HAS_PING3:
        try:
            r = ping3_ping(host, timeout=2, unit="ms")
            if r is not None and r is not False:
                return float(r)
        except Exception:
            pass
    try:
        cmd = (["ping", "-n", "1", "-w", "2000", host]
               if sys.platform.startswith("win")
               else ["ping", "-c", "1", "-W", "2", host])
        out = subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, timeout=4
        ).decode(errors="replace")
        m = re.search(r"time[=<](\d+\.?\d*)\s*ms", out)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return -1.0


def _gpu_info_lines():
    lines = []
    if HAS_GPUTIL:
        try:
            for g in GPUtil.getGPUs():
                lines += [f"[b]{g.name}[/b]",
                           f"  Load: {g.load*100:.1f}%",
                           f"  VRAM: {g.memoryUsed:.0f}/{g.memoryTotal:.0f} MB",
                           f"  Temp: {g.temperature} C"]
            return lines
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            timeout=3, stderr=subprocess.DEVNULL
        ).decode(errors="replace").strip()
        for row in out.splitlines():
            p = [x.strip() for x in row.split(",")]
            if len(p) >= 5:
                lines += [f"[b]{p[0]}[/b]",
                           f"  Load: {p[1]}%",
                           f"  VRAM: {p[2]}/{p[3]} MB",
                           f"  Temp: {p[4]} C"]
        if lines:
            return lines
    except Exception:
        pass
    if sys.platform.startswith("linux"):
        try:
            drm = "/sys/class/drm"
            for card in sorted(os.listdir(drm)):
                gp = os.path.join(drm, card, "device", "gpu_busy_percent")
                if os.path.exists(gp):
                    util = open(gp).read().strip()
                    lines += [f"[b]{card}[/b]", f"  Load: {util}%"]
            if lines:
                return lines
        except Exception:
            pass
    lines.append("GPU info not available")
    return lines


class SystemStatsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._ping_host           = PING_HOST_DEFAULT
        self._ping_thread_running = False
        self._ping_lock           = threading.Lock()
        self._last_ping           = [-1.0]
        self._fps_ref             = [0.0]
        self._frame_times         = collections.deque(maxlen=30)
        self._update_ev           = None
        self._overlay_proc        = None   # subprocess for overlay window
        self._overlay_log_path    = None   # set at launch time

        root = BoxLayout(orientation="vertical", padding=6, spacing=6)
        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(40))
        self.tabs.add_widget(self._build_system_tab())
        self.tabs.add_widget(self._build_graphs_tab())
        self.tabs.add_widget(self._build_overlay_tab())
        root.add_widget(self.tabs)

        back = Button(text="Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=self._go_back)
        root.add_widget(back)
        self.add_widget(root)

    # ── System tab ────────────────────────────────────────────────────────
    def _build_system_tab(self):
        tab = TabbedPanelItem(text="System")
        sv = ScrollView()
        self._sys_grid = GridLayout(cols=1, spacing=4,
                                    size_hint_y=None, padding=8)
        self._sys_grid.bind(minimum_height=self._sys_grid.setter("height"))
        sv.add_widget(self._sys_grid)
        self._sys_labels = {}
        for key, title in [("cpu","CPU"),("ram","RAM"),
                            ("disk","Disk"),("gpu","GPU"),("net","Network")]:
            self._sys_grid.add_widget(
                Label(text=f"[b]-- {title} --[/b]", markup=True,
                      size_hint_y=None, height=dp(26), font_size=14))
            lbl = Label(text="...", size_hint_y=None, height=dp(80),
                        markup=True, halign="left", valign="top", font_size=13)
            lbl.bind(size=lbl.setter("text_size"))
            self._sys_labels[key] = lbl
            self._sys_grid.add_widget(lbl)
        tab.add_widget(sv)
        return tab

    # ── Graphs tab ────────────────────────────────────────────────────────
    def _build_graphs_tab(self):
        tab = TabbedPanelItem(text="Live Graphs")
        layout = BoxLayout(orientation="vertical", padding=8, spacing=8)
        layout.add_widget(Label(text="[b]Kivy FPS[/b]", markup=True,
                                size_hint_y=None, height=dp(22), font_size=14))
        self._fps_graph = GraphWidget(label="FPS", unit="fps",
                                      max_val=120.0, color=(0.25, 0.70, 1.0),
                                      size_hint_y=0.35)
        layout.add_widget(self._fps_graph)

        pr = BoxLayout(size_hint_y=None, height=dp(36), spacing=8)
        pr.add_widget(Label(text="[b]Ping[/b] host:", markup=True,
                            size_hint_x=None, width=dp(100), font_size=13))
        self._ping_input = TextInput(text=PING_HOST_DEFAULT,
                                     multiline=False, font_size=13,
                                     size_hint_x=0.5)
        apply_btn = Button(text="Apply", size_hint_x=None, width=dp(70))
        apply_btn.bind(on_release=self._apply_ping)
        pr.add_widget(self._ping_input)
        pr.add_widget(apply_btn)
        layout.add_widget(pr)

        self._ping_graph = GraphWidget(label="Ping", unit="ms",
                                       max_val=300.0, color=(1.0, 0.65, 0.10),
                                       size_hint_y=0.35)
        layout.add_widget(self._ping_graph)
        tab.add_widget(layout)
        return tab

    # ── Overlay tab ───────────────────────────────────────────────────────
    def _build_overlay_tab(self):
        tab = TabbedPanelItem(text="Overlay")
        layout = BoxLayout(orientation="vertical", padding=10, spacing=8)

        layout.add_widget(Label(
            text="[b]Mini Stats Overlay[/b]", markup=True,
            size_hint_y=None, height=dp(30), font_size=16))
        layout.add_widget(Label(
            text=("Opens a small always-on-top window that stays visible\n"
                  "even when Srboli is minimised.\n"
                  "Close it by closing that window directly."),
            size_hint_y=None, height=dp(56), font_size=12, halign="left"))

        self._overlay_btn = Button(
            text="Open Overlay Window", size_hint_y=None, height=dp(52),
            font_size=15, background_color=(0.2, 0.55, 0.2, 1))
        self._overlay_btn.bind(on_release=self._toggle_overlay)
        layout.add_widget(self._overlay_btn)

        self._overlay_status = Label(
            text="Overlay: not running", font_size=12,
            size_hint_y=None, height=dp(26), color=(0.6, 0.8, 1, 1))
        layout.add_widget(self._overlay_status)

        layout.add_widget(Label(
            text="Note: the overlay is a separate process.\n"
                 "You can move, resize, and minimise it independently.",
            font_size=11, size_hint_y=None, height=dp(40),
            halign="left", color=(0.6, 0.6, 0.6, 1)))

        tab.add_widget(layout)
        return tab

    def _toggle_overlay(self, *a):
        if self._overlay_proc and self._overlay_proc.poll() is None:
            self._overlay_proc.terminate()
            self._overlay_proc = None
            self._overlay_btn.text    = "Open Overlay Window"
            self._overlay_status.text = "Overlay: closed"
            return

        script_path = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "_overlay_app.py"))

        if not os.path.exists(script_path):
            # also check root folder
            script_path2 = os.path.abspath(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "_overlay_app.py"))
            if os.path.exists(script_path2):
                script_path = script_path2
            else:
                self._overlay_status.text = (
                    f"Error: _overlay_app.py not found.\n"
                    f"Checked:\n{script_path}\n{script_path2}")
                return

        # Use a log file so we can read errors if it crashes
        log_path = os.path.join(os.path.dirname(script_path),
                                ".overlay_log.txt")
        self._overlay_log_path = log_path
        try:
            env = os.environ.copy()
            # Ensure display is set on Linux
            if not env.get("DISPLAY"):
                env["DISPLAY"] = ":0"

            with open(log_path, "w") as log_f:
                self._overlay_proc = subprocess.Popen(
                    [sys.executable, script_path],
                    stdout=log_f, stderr=log_f,
                    env=env,
                    start_new_session=True)  # fully detach from parent

            self._overlay_btn.text    = "Close Overlay Window"
            self._overlay_status.text = f"Overlay launched (PID {self._overlay_proc.pid})"

            # Check after 2s if it's still running
            Clock.schedule_once(self._check_overlay_startup, 2.0)
        except Exception as e:
            self._overlay_status.text = f"Launch error: {e}"

        Clock.schedule_interval(self._check_overlay, 3.0)

    def _check_overlay_startup(self, dt):
        """Check 2s after launch if overlay crashed and show log."""
        if self._overlay_proc and self._overlay_proc.poll() is not None:
            # read from the same folder the log was actually written to
            # (next to whichever _overlay_app.py copy we launched — this
            # used to be hardcoded to the root folder, which silently
            # missed the log whenever _overlay_app.py was found in screens/)
            log_path = self._overlay_log_path
            try:
                with open(os.path.abspath(log_path), encoding="utf-8",
                          errors="replace") as f:
                    err = f.read()[-400:]  # last 400 chars
            except Exception:
                err = "No log available"
            self._overlay_status.text = f"Overlay crashed. Log: {err[:120]}"
            self._overlay_proc = None
            self._overlay_btn.text = "Open Overlay Window"

    def _check_overlay(self, dt):
        if self._overlay_proc and self._overlay_proc.poll() is not None:
            self._overlay_proc = None
            self._overlay_btn.text    = "Open Overlay Window"
            self._overlay_status.text = "Overlay: closed"
            return False  # unschedule

    # ── lifecycle ─────────────────────────────────────────────────────────
    def on_enter(self, *a):
        self._update_ev = Clock.schedule_interval(self._tick, 1.0)
        self._start_ping_thread()
        Clock.schedule_interval(self._fps_tick, 1/30)

    def on_leave(self, *a):
        if self._update_ev:
            self._update_ev.cancel()
            self._update_ev = None
        self._ping_thread_running = False
        Clock.unschedule(self._fps_tick)

    def _fps_tick(self, dt):
        self._frame_times.append(time.monotonic())

    def _tick(self, dt):
        self._update_system()
        times = list(self._frame_times)
        if len(times) >= 2:
            elapsed = times[-1] - times[0]
            fps = (len(times)-1)/elapsed if elapsed > 0 else 0.0
        else:
            fps = 0.0
        self._fps_ref[0] = fps
        self._fps_graph.push(fps)
        with self._ping_lock:
            ms = self._last_ping[0]
        if ms < 0:
            self._ping_graph.push(0, label_override="timeout")
        else:
            self._ping_graph.push(min(ms, 300), label_override=f"{ms:.1f} ms")

        # Write shared data for overlay subprocess
        _shared = os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", ".srboli_overlay_data.json"))
        try:
            import json as _json
            with open(_shared, "w", encoding="utf-8") as f:
                _json.dump({"fps": round(fps, 1),
                            "ping": round(ms, 1),
                            "host": self._ping_host,
                            "ts": time.time()}, f)
        except Exception:
            pass

    def _start_ping_thread(self):
        if self._ping_thread_running:
            return
        self._ping_thread_running = True
        def _loop():
            while self._ping_thread_running:
                ms = _do_ping(self._ping_host)
                with self._ping_lock:
                    self._last_ping[0] = ms
                time.sleep(2.0)
        threading.Thread(target=_loop, daemon=True).start()

    def _apply_ping(self, *a):
        h = self._ping_input.text.strip()
        if h:
            self._ping_host = h
            self._ping_thread_running = False
            time.sleep(0.1)
            self._start_ping_thread()

    def _update_system(self):
        if not HAS_PSUTIL:
            for lbl in self._sys_labels.values():
                lbl.text = ("psutil not installed\n"
                           "Run: python3 -m pip install psutil")
            return
        try:
            freq = psutil.cpu_freq()
            freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"
            per = psutil.cpu_percent(percpu=True)
            cores = "  ".join(f"C{i}:{p:.0f}%" for i,p in enumerate(per))
            self._sys_labels["cpu"].text = (
                f"Usage: {psutil.cpu_percent():.1f}%\n"
                f"Freq:  {freq_str}\n"
                f"Cores ({psutil.cpu_count()}): {cores}")
            self._sys_labels["cpu"].height = dp(90)
        except Exception as e:
            self._sys_labels["cpu"].text = f"Error: {e}"
        try:
            vm = psutil.virtual_memory()
            sw = psutil.swap_memory()
            self._sys_labels["ram"].text = (
                f"Used:  {vm.used/1e9:.2f}/{vm.total/1e9:.2f} GB ({vm.percent:.1f}%)\n"
                f"Free:  {vm.available/1e9:.2f} GB\n"
                f"Swap:  {sw.used/1e9:.2f}/{sw.total/1e9:.2f} GB")
        except Exception as e:
            self._sys_labels["ram"].text = f"Error: {e}"
        try:
            lines = []
            for part in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    lines.append(f"{part.mountpoint}: "
                                 f"{u.used/1e9:.1f}/{u.total/1e9:.1f} GB "
                                 f"({u.percent:.0f}%)")
                except PermissionError:
                    pass
            self._sys_labels["disk"].text = "\n".join(lines) or "--"
            self._sys_labels["disk"].height = dp(max(60, len(lines)*22))
        except Exception as e:
            self._sys_labels["disk"].text = f"Error: {e}"
        try:
            gpu_lines = _gpu_info_lines()
            self._sys_labels["gpu"].text = "\n".join(gpu_lines)
            self._sys_labels["gpu"].height = dp(max(60, len(gpu_lines)*22))
        except Exception as e:
            self._sys_labels["gpu"].text = f"Error: {e}"
        try:
            net = psutil.net_io_counters()
            with self._ping_lock:
                ms = self._last_ping[0]
            ps = f"{ms:.1f} ms" if ms >= 0 else "timeout"
            self._sys_labels["net"].text = (
                f"Sent:  {net.bytes_sent/1e6:.1f} MB\n"
                f"Recv:  {net.bytes_recv/1e6:.1f} MB\n"
                f"Ping ({self._ping_host}): {ps}")
        except Exception as e:
            self._sys_labels["net"].text = f"Error: {e}"

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
