# screens/script_mode_screen.py
# Script / Teleprompter Mode
# - Split by Enter (blank line), Lines, Characters, Sentences, Paragraphs
# - Auto-advance: watches clipboard for paste (Ctrl+V), then copies next chunk

import re
import threading
import time

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.checkbox import CheckBox
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.clock import Clock


class ScriptModeScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._chunks    = []
        self._idx       = 0
        self._running   = False
        self._auto_ev   = None   # clock event for auto-advance
        self._auto_mode = False  # watching for paste

        root = BoxLayout(orientation="vertical", padding=8, spacing=5)

        root.add_widget(Label(
            text="Script / Teleprompter Mode",
            size_hint_y=None, height=dp(30), font_size=17, bold=True))
        root.add_widget(Label(
            text="Paste your full text, split it into chunks.\n"
                 "Each chunk auto-copies. Paste it wherever, then press Next.",
            size_hint_y=None, height=dp(36), font_size=11, halign="left"))

        # ── input ──────────────────────────────────────────────────────────
        self._input = TextInput(
            multiline=True, font_size=13, size_hint_y=0.26,
            hint_text="Paste full script/text here...",
            background_color=(0.10, 0.10, 0.13, 1),
            foreground_color=(0.92, 0.92, 0.88, 1),
        )
        root.add_widget(self._input)

        # ── split options ──────────────────────────────────────────────────
        opt = BoxLayout(size_hint_y=None, height=dp(36), spacing=6)
        opt.add_widget(Label(text="Split by:", size_hint_x=None,
                             width=dp(60), font_size=13))
        self._split_mode = Spinner(
            text="Enter (blank line)",
            values=("Enter (blank line)", "Lines", "Characters",
                    "Sentences", "Paragraphs"),
            size_hint_x=None, width=dp(170), font_size=12)
        opt.add_widget(self._split_mode)
        opt.add_widget(Label(text="Size:", size_hint_x=None,
                             width=dp(38), font_size=12))
        self._chunk_sz = TextInput(text="1", multiline=False,
                                   input_filter="int",
                                   size_hint_x=None, width=dp(50),
                                   font_size=13)
        opt.add_widget(self._chunk_sz)
        split_btn = Button(text="Split", size_hint_x=None, width=dp(70),
                           font_size=13)
        split_btn.bind(on_release=self._do_split)
        opt.add_widget(split_btn)
        root.add_widget(opt)

        # ── auto-advance option ────────────────────────────────────────────
        auto_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=8)
        self._auto_cb = CheckBox(size_hint_x=None, size=(dp(24), dp(24)))
        self._auto_cb.bind(active=self._toggle_auto)
        auto_row.add_widget(self._auto_cb)
        auto_row.add_widget(Label(
            text="Auto-advance on paste (Ctrl+V) — copies next chunk automatically",
            font_size=11, halign="left"))
        root.add_widget(auto_row)

        # ── chunk preview ──────────────────────────────────────────────────
        sv = ScrollView(size_hint=(1, 0.14))
        self._prev_grid = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self._prev_grid.bind(minimum_height=self._prev_grid.setter("height"))
        sv.add_widget(self._prev_grid)
        root.add_widget(sv)

        # ── status + current chunk ─────────────────────────────────────────
        self._status = Label(
            text="Press Split, then Start.",
            size_hint_y=None, height=dp(24), font_size=13, bold=True,
            color=(0.4, 0.9, 0.4, 1))
        root.add_widget(self._status)

        self._chunk_disp = TextInput(
            text="", readonly=True, multiline=True,
            font_size=15, size_hint_y=0.12,
            background_color=(0.06, 0.12, 0.06, 1),
            foreground_color=(0.3, 1, 0.4, 1),
        )
        root.add_widget(self._chunk_disp)

        self._prog = Label(text="", size_hint_y=None, height=dp(18),
                           font_size=11, color=(0.5, 0.7, 1, 1))
        root.add_widget(self._prog)

        # ── controls ───────────────────────────────────────────────────────
        ctrl = BoxLayout(size_hint_y=None, height=dp(48), spacing=5)
        self._start_btn = Button(text="Start", font_size=15,
                                 background_color=(0.2, 0.6, 0.2, 1))
        self._start_btn.bind(on_release=self._start)
        self._prev_btn = Button(text="< Back", font_size=13,
                                disabled=True, size_hint_x=None, width=dp(80))
        self._prev_btn.bind(on_release=self._prev)
        self._next_btn = Button(text="Next >", font_size=15, disabled=True)
        self._next_btn.bind(on_release=self._next)
        stop_btn = Button(text="Stop", font_size=13,
                          size_hint_x=None, width=dp(70),
                          background_color=(0.6, 0.15, 0.15, 1))
        stop_btn.bind(on_release=self._stop)
        for b in (self._start_btn, self._prev_btn, self._next_btn, stop_btn):
            ctrl.add_widget(b)
        root.add_widget(ctrl)

        back = Button(text="Back to menu", size_hint_y=None, height=dp(40))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

        # keyboard: bind Ctrl+V to auto-advance
        Window.bind(on_key_down=self._on_key)

    # ── split ──────────────────────────────────────────────────────────────
    def _do_split(self, *a):
        text = self._input.text
        if not text.strip():
            return
        try:
            size = max(1, int(self._chunk_sz.text))
        except ValueError:
            size = 1
        mode = self._split_mode.text

        if mode == "Enter (blank line)":
            # Each non-empty line is a unit; blank lines act as separators
            # Group 'size' consecutive non-empty lines = one chunk
            lines = [l.rstrip() for l in text.splitlines()]
            # collect non-empty lines (blank lines reset grouping)
            groups = []
            current_group = []
            for line in lines:
                if line.strip():
                    current_group.append(line)
                    if len(current_group) >= size:
                        groups.append("\n".join(current_group))
                        current_group = []
                else:
                    # blank line = flush current group as chunk
                    if current_group:
                        groups.append("\n".join(current_group))
                        current_group = []
            if current_group:
                groups.append("\n".join(current_group))
            self._chunks = groups

        elif mode == "Lines":
            lines = [l for l in text.splitlines() if l.strip()]
            self._chunks = ["\n".join(lines[i:i+size])
                           for i in range(0, len(lines), size)]

        elif mode == "Characters":
            self._chunks = [text[i:i+size]
                           for i in range(0, len(text), size)]

        elif mode == "Sentences":
            sentences = re.split(r"(?<=[.!?])\s+", text.strip())
            self._chunks = [" ".join(sentences[i:i+size])
                           for i in range(0, len(sentences), size)]

        elif mode == "Paragraphs":
            paras = [p.strip() for p in re.split(r"\n{2,}", text)
                     if p.strip()]
            self._chunks = ["\n\n".join(paras[i:i+size])
                           for i in range(0, len(paras), size)]

        # rebuild preview
        self._prev_grid.clear_widgets()
        for i, chunk in enumerate(self._chunks):
            preview = chunk[:65].replace("\n", " ")
            if len(chunk) > 65:
                preview += "..."
            lbl = Label(text=f"{i+1}. {preview}",
                        size_hint_y=None, height=dp(20),
                        font_size=10, halign="left")
            lbl.bind(size=lbl.setter("text_size"))
            self._prev_grid.add_widget(lbl)

        self._status.text = f"{len(self._chunks)} chunks ready -- press Start"

    # ── playback ───────────────────────────────────────────────────────────
    def _start(self, *a):
        if not self._chunks:
            self._do_split()
        if not self._chunks:
            self._status.text = "Split your text first."
            return
        self._idx = 0
        self._running = True
        self._start_btn.disabled = True
        self._next_btn.disabled  = False
        self._prev_btn.disabled  = False
        self._show()

    def _show(self):
        if self._idx >= len(self._chunks):
            self._status.text     = "All done!"
            self._chunk_disp.text = ""
            self._next_btn.disabled = True
            self._running = False
            self._start_btn.disabled = False
            if self._auto_ev:
                self._auto_ev.cancel()
                self._auto_ev = None
            return
        chunk = self._chunks[self._idx]
        self._chunk_disp.text = chunk
        Clipboard.copy(chunk)
        n = self._chunks.__len__()
        self._status.text = (f"Chunk {self._idx+1}/{n} -- copied! "
                              + ("Paste it (Ctrl+V auto-advances)"
                                 if self._auto_mode else "Paste it, then click Next"))
        filled = int((self._idx + 1) / n * 28)
        self._prog.text = ("=" * filled + "-" * (28 - filled) +
                           f"  {self._idx+1}/{n}")

    def _next(self, *a):
        self._idx += 1
        self._show()

    def _prev(self, *a):
        if self._idx > 0:
            self._idx -= 1
            self._show()

    def _stop(self, *a):
        self._running = False
        self._start_btn.disabled = False
        self._next_btn.disabled  = True
        self._prev_btn.disabled  = True
        self._status.text = "Stopped."
        if self._auto_ev:
            self._auto_ev.cancel()
            self._auto_ev = None

    # ── auto-advance ───────────────────────────────────────────────────────
    def _toggle_auto(self, cb, active):
        self._auto_mode = active

    def _on_key(self, window, key, scancode, codepoint, modifiers):
        """Detect Ctrl+V — if auto mode on and running, advance after short delay."""
        if not self.manager or self.manager.current != "script_mode":
            return
        is_paste = (key == 118 and "ctrl" in modifiers)   # V key + ctrl
        if is_paste and self._auto_mode and self._running:
            # small delay so paste completes first, then copy next chunk
            Clock.schedule_once(lambda dt: self._next(), 0.3)

    # ── lifecycle ──────────────────────────────────────────────────────────
    def on_leave(self, *a):
        if self._auto_ev:
            self._auto_ev.cancel()
            self._auto_ev = None

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
