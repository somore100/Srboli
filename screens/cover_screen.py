# screens/cover_screen.py — control panel for the Cover feature (privacy
# boxes, blackout, hide-from-recording, global hotkeys). Desktop only.
#
# The boxes themselves live in a separate tkinter process (`Srboli --cover`,
# see core/cover_app.py) because Kivy allows one Window per process. This
# screen only edits cover.json and sends commands to that process; every
# socket call runs on a worker thread so the UI never blocks on it.

import threading

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.metrics import dp

import core.cover_core as cc
from core.daemon_ipc import send_command as daemon_send

STATUS_POLL_S = 2.0


def _bg_input(**kw):
    kw.setdefault("multiline", False)
    kw.setdefault("write_tab", False)
    kw.setdefault("background_color", (0.12, 0.12, 0.14, 1))
    kw.setdefault("foreground_color", (0.9, 0.9, 0.9, 1))
    kw.setdefault("font_size", 13)
    return TextInput(**kw)


def _in_thread(fn, *a):
    threading.Thread(target=fn, args=a, daemon=True).start()


class BoxCard(BoxLayout):
    """Editor for one box. read() returns the edited dict."""

    def __init__(self, box, on_remove, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(150), padding=6, spacing=4, **kw)
        self.box_id = box["id"]
        from kivy.graphics import Color, Rectangle
        with self.canvas.before:
            Color(0.14, 0.14, 0.17, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *a: setattr(self._bg, "pos", self.pos),
                  size=lambda *a: setattr(self._bg, "size", self.size))

        r1 = BoxLayout(size_hint_y=None, height=dp(34), spacing=4)
        self.name_in = _bg_input(text=box["name"], hint_text="name")
        r1.add_widget(self.name_in)
        self.style_sp = Spinner(text=box["style"], values=list(cc.STYLES),
                             size_hint_x=0.5, font_size=13)
        self.style_sp.bind(text=self._style_changed)
        r1.add_widget(self.style_sp)
        rm = Button(text="Remove", size_hint_x=0.5, font_size=13,
                    background_color=(0.55, 0.2, 0.2, 1))
        rm.bind(on_release=lambda *a: on_remove(self.box_id))
        r1.add_widget(rm)
        self.add_widget(r1)

        r2 = BoxLayout(size_hint_y=None, height=dp(34), spacing=4)
        self.fields = {}
        for key in ("x", "y", "w", "h"):
            r2.add_widget(Label(text=key, size_hint_x=0.25, font_size=13))
            ti = _bg_input(text=str(box[key]), input_filter="int",
                           halign="center")
            self.fields[key] = ti
            r2.add_widget(ti)
        self.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(34), spacing=4)
        r3.add_widget(Label(text="colour", size_hint_x=0.6, font_size=13))
        self.color_in = _bg_input(text=box["color"], hint_text="#rrggbb")
        r3.add_widget(self.color_in)
        r3.add_widget(Label(text="opacity", size_hint_x=0.6, font_size=13))
        self.opacity_in = _bg_input(text=str(box["opacity"]),
                                 input_filter="float")
        r3.add_widget(self.opacity_in)
        self.add_widget(r3)

        r4 = BoxLayout(size_hint_y=None, height=dp(34), spacing=4)
        self.hide_cap = CheckBox(active=box["hide_from_capture"],
                                 size_hint_x=None, width=dp(32),
                                 disabled=not cc.capture_exclusion_supported())
        r4.add_widget(self.hide_cap)
        r4.add_widget(Label(
            text="hide from recording" if cc.capture_exclusion_supported()
            else "hide from recording (Windows only)",
            font_size=12, halign="left", color=(0.8, 0.8, 0.8, 1)))
        self.hotkey = _bg_input(text=box["hotkey"],
                                hint_text="box hotkey, e.g. ctrl+alt+1")
        r4.add_widget(self.hotkey)
        self.add_widget(r4)

    def _style_changed(self, inst, text):
        # A frame is an outline, so black-on-anything is useless: switch the
        # default colour to white when the user picks it (and back).
        if text == "frame" and self.color_in.text.strip().lower() == "#000000":
            self.color_in.text = "#ffffff"
        elif text == "solid" and self.color_in.text.strip().lower() == "#ffffff":
            self.color_in.text = "#000000"

    def read(self):
        d = {"id": self.box_id, "name": self.name_in.text.strip(),
             "style": self.style_sp.text, "color": self.color_in.text.strip(),
             "opacity": self.opacity_in.text.strip() or "1",
             "hide_from_capture": bool(self.hide_cap.active),
             "hotkey": self.hotkey.text.strip()}
        for k, ti in self.fields.items():
            d[k] = ti.text.strip() or "0"
        return d


class CoverScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._poll = None
        self._cfg = cc.load_config()
        self.cards = []

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        root.add_widget(Label(text="[b]Cover — privacy boxes & blackout[/b]",
                              markup=True, size_hint_y=None, height=dp(34),
                              font_size=18))

        if not cc.is_desktop():
            root.add_widget(Label(
                text="Desktop only.\nThe cover boxes are desktop windows "
                     "(Windows / Linux X11); there's nothing to run on "
                     "Android.", halign="center"))
            self._add_back(root)
            self.add_widget(root)
            return

        self.status = Label(text="…", size_hint_y=None, height=dp(48),
                            font_size=12, halign="left", valign="middle",
                            color=(0.8, 0.85, 0.9, 1))
        self.status.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        root.add_widget(self.status)

        sv = ScrollView()
        self.body = GridLayout(cols=1, spacing=8, size_hint_y=None)
        self.body.bind(minimum_height=self.body.setter("height"))
        sv.add_widget(self.body)
        root.add_widget(sv)
        self._add_back(root)
        self.add_widget(root)
        self._build_body()

    def _add_back(self, root):
        back = Button(text="Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(self.manager, "current",
                                                "dashboard"))
        root.add_widget(back)

    # ── layout ────────────────────────────────────────────────────────
    def _section(self, text):
        self.body.add_widget(Label(
            text=f"[b]{text}[/b]", markup=True, size_hint_y=None,
            height=dp(28), font_size=14, halign="left",
            color=(0.55, 0.8, 1, 1)))
        self.body.children[0].bind(
            size=lambda i, s: setattr(i, "text_size", (s[0], None)))

    def _note(self, text, h=40):
        lb = Label(text=text, size_hint_y=None, height=dp(h), font_size=12,
                   halign="left", valign="top", color=(0.7, 0.7, 0.7, 1))
        lb.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.body.add_widget(lb)

    def _btn_row(self, items):
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
        for text, fn in items:
            b = Button(text=text, font_size=13)
            b.bind(on_release=lambda inst, f=fn: f())
            row.add_widget(b)
        self.body.add_widget(row)

    def _check_row(self, text, active, attr):
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
        cb = CheckBox(active=active, size_hint_x=None, width=dp(32))
        setattr(self, attr, cb)
        row.add_widget(cb)
        row.add_widget(Label(text=text, font_size=13, halign="left",
                             color=(0.9, 0.9, 0.9, 1)))
        row.children[0].bind(
            size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.body.add_widget(row)

    def _build_body(self):
        self.body.clear_widgets()
        cfg = self._cfg

        self._section("Control")
        self._btn_row([("Start", self._start), ("Stop", self._stop),
                       ("Show/Hide", lambda: self._cmd("toggle")),
                       ("Blackout", lambda: self._cmd("blackout"))])
        self._btn_row([("Draw a box", lambda: self._cmd("add_box")),
                       ("Lock session", lambda: self._cmd("lock"))])
        self._note("Boxes: drag to move, drag the bottom-right corner of a "
                   "solid box to resize, right-click a box to hide it. "
                   "Blackout: double-click to dismiss.", 44)

        self._section("Options")
        self._check_row("Run with the background service (starts at login "
                        "if the service does)", cfg["service_enabled"],
                        "_svc_cb")
        self._check_row("Start with boxes hidden", cfg["start_hidden"],
                        "_hidden_cb")
        self._check_row("Also lock the session when blackout turns on",
                        cfg["lock_after_blackout"], "_lock_cb")
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
        row.add_widget(Label(text="Blackout colour / opacity", font_size=13,
                             size_hint_x=1.4))
        self._bo_color = _bg_input(text=cfg["blackout"]["color"])
        self._bo_opacity = _bg_input(text=str(cfg["blackout"]["opacity"]),
                                     input_filter="float")
        row.add_widget(self._bo_color)
        row.add_widget(self._bo_opacity)
        self.body.add_widget(row)

        self._section("Hotkeys")
        self._hk = {}
        for act in cc.HOTKEY_ACTIONS:
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
            row.add_widget(Label(text=cc.HOTKEY_LABELS[act], font_size=13,
                                 size_hint_x=1.3))
            ti = _bg_input(text=cfg["hotkeys"].get(act, ""),
                           hint_text="e.g. ctrl+alt+h")
            self._hk[act] = ti
            row.add_widget(ti)
            self.body.add_widget(row)
        if cc.global_hotkeys_supported():
            if not cc.pynput_available():
                self._note("Global hotkeys need:  pip install pynput", 24)
            else:
                self._note("Needs at least one modifier (ctrl / alt / shift "
                           "/ win). Per-box hotkeys are set on each box.", 30)
        else:
            cmds = "\n".join(
                f"{a}:  " + " ".join(cc.cover_cmd_launch_cmd(a))
                for a in ("toggle", "blackout", "add_box"))
            self._note(
                f"This session is {cc.session_type()}: apps cannot register "
                "global hotkeys here. Bind a system shortcut (e.g. GNOME "
                "Settings > Keyboard > Custom Shortcuts) to these commands:\n"
                + cmds, 110)

        self._section("Boxes")
        self.cards = []
        for b in cfg["boxes"]:
            card = BoxCard(b, self._remove_box)
            self.cards.append(card)
            self.body.add_widget(card)
        if not cfg["boxes"]:
            self._note("No boxes yet — add one here, or use 'Draw a box' "
                       "while Cover is running.", 26)
        self._btn_row([("Add box", self._add_box),
                       ("Save & apply", self._save)])
        self.msg = Label(text="", size_hint_y=None, height=dp(40),
                         font_size=12, halign="left", valign="top")
        self.msg.bind(size=lambda i, s: setattr(i, "text_size", (s[0], None)))
        self.body.add_widget(self.msg)

        if not cc.tk_available():
            self._msg("tkinter is missing - Cover cannot run. Fedora: sudo "
                      "dnf install python3-tkinter  |  Debian/Ubuntu: sudo "
                      "apt install python3-tk", err=True)

    # ── collecting / saving ───────────────────────────────────────────
    def _collect(self):
        cfg = {
            "service_enabled": self._svc_cb.active,
            "start_hidden": self._hidden_cb.active,
            "lock_after_blackout": self._lock_cb.active,
            "blackout": {"color": self._bo_color.text.strip(),
                         "opacity": self._bo_opacity.text.strip() or "1"},
            "hotkeys": {}, "boxes": [c.read() for c in self.cards],
        }
        errors = []
        for act, ti in self._hk.items():
            try:
                cfg["hotkeys"][act] = cc.normalize_hotkey(ti.text)
            except ValueError as e:
                errors.append(f"{cc.HOTKEY_LABELS[act]}: {e}")
        for b in cfg["boxes"]:
            try:
                cc.normalize_hotkey(b["hotkey"])
            except ValueError as e:
                errors.append(f"{b['name']}: {e}")
        return cfg, errors

    def _msg(self, text, err=False):
        if hasattr(self, "msg"):
            self.msg.text = text
            self.msg.color = (1, 0.5, 0.5, 1) if err else (0.6, 0.9, 0.6, 1)

    def _save(self, quiet=False):
        cfg, errors = self._collect()
        if errors:
            self._msg("Not saved:\n" + "\n".join(errors), err=True)
            return False
        saved = cc.save_config(cfg)
        self._cfg = saved

        def push():
            cc.send_cover_command("reload")          # no-op if not running
            daemon_send("reload", timeout=1.0)       # starts it if enabled
        _in_thread(push)
        if not quiet:
            self._msg("Saved.")
        return True

    def _add_box(self):
        cfg, errors = self._collect()
        if errors:
            self._msg("Fix first:\n" + "\n".join(errors), err=True)
            return
        cfg["boxes"].append({"id": cc.new_box_id(
            {"boxes": cfg["boxes"]})[0]})
        n = len(cfg["boxes"])
        cfg["boxes"][-1] = dict(cc.default_box(n), id=cfg["boxes"][-1]["id"])
        self._cfg = cc.normalize_config(cfg)
        self._build_body()
        self._msg("Box added - press Save & apply to show it.")

    def _remove_box(self, bid):
        cfg, errors = self._collect()
        cfg["boxes"] = [b for b in cfg["boxes"] if b["id"] != bid]
        self._cfg = cc.normalize_config(cfg)
        self._build_body()
        self._msg("Removed - press Save & apply.")

    # ── commands ──────────────────────────────────────────────────────
    def _start(self):
        if not cc.tk_available():
            self._msg("tkinter missing (see below).", err=True)
            return
        if not self._save(quiet=True):
            return
        _in_thread(cc.start_cover)
        self._msg("Starting…")

    def _stop(self):
        _in_thread(cc.send_cover_command, "quit")
        self._msg("Stopped." + (
            " (Background service is on and will start it again at its "
            "next restart.)" if self._cfg.get("service_enabled") else ""))

    def _cmd(self, cmd):
        def run():
            r = cc.send_cover_command(cmd)
            if r is None and cmd in ("toggle", "blackout", "add_box") \
                    and cc.tk_available() and cc.start_cover():
                import time
                for _ in range(30):
                    time.sleep(0.1)
                    if cc.is_running():
                        break
                if cmd != "toggle":
                    cc.send_cover_command(cmd)
            elif cmd == "lock" and r is None:
                cc.lock_session()
        _in_thread(run)

    # ── status polling ────────────────────────────────────────────────
    def _poll_status(self, *a):
        def work():
            r = cc.send_cover_command("status", timeout=0.6)
            Clock.schedule_once(lambda dt: self._set_status(r), 0)
        _in_thread(work)

    def _set_status(self, r):
        sess = cc.session_type()
        cap = ("hide-from-recording: available" if
               cc.capture_exclusion_supported() else
               "hide-from-recording: Windows only")
        if r and r.startswith("ok"):
            head = "[RUNNING]  " + r[3:]
        else:
            head = "[not running]"
        self.status.text = f"{head}\nsession: {sess}  |  {cap}"

    def on_enter(self, *a):
        if not cc.is_desktop():
            return
        self._cfg = cc.load_config()
        self._build_body()
        self._poll_status()
        self._poll = Clock.schedule_interval(self._poll_status,
                                             STATUS_POLL_S)

    def on_leave(self, *a):
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
