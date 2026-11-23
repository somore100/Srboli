# screens/clipboard_history_screen.py - Clipboard History: what you copied lately.
# Tap an entry to copy it again. Pin keeps it; search filters. While Srboli is
# open it checks the clipboard once a second (not when paused). Kept in memory
# only unless "Keep after closing" is on. Logic: core/clipboard_history_core.py.
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core import clipboard_history_core as core
from core import theme
from screens.scaffold import ToolScreen

POLL = 1.0
OFF = (0.25, 0.25, 0.25, 1)


class ClipboardHistoryScreen(ToolScreen):
    title = "Clipboard History"

    def __init__(self, **kw):
        super().__init__(**kw)
        st = core.load_state()
        self.hist = core.History()
        self.hist.items = st["items"] if st["keep"] else []
        self.keep = st["keep"]
        self.recording = True
        self._last = None
        self._ev = None

        bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.rec_btn = Button(font_size=sp(12))
        self.rec_btn.bind(on_release=lambda *a: self.set_recording(not self.recording))
        self.keep_btn = Button(font_size=sp(12))
        self.keep_btn.bind(on_release=lambda *a: self.set_keep(not self.keep))
        clr = Button(text="Clear (keeps pinned)", font_size=sp(12))
        clr.bind(on_release=lambda *a: self.clear())
        for b in (self.rec_btn, self.keep_btn, clr):
            bar.add_widget(b)
        self.body.add_widget(bar)

        self.search = TextInput(hint_text="Search", multiline=False, size_hint_y=None,
                                height=dp(38), font_size=sp(14))
        self.search.bind(text=lambda *a: self.refresh())
        self.body.add_widget(self.search)

        sv = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        sv.add_widget(self.grid)
        self.body.add_widget(sv)
        self.status = Label(text="", font_size=sp(11), size_hint_y=None, height=dp(22),
                            color=theme.SUCCESS)
        self.body.add_widget(self.status)
        self._sync_buttons()
        self._start()
        self.refresh()

    # ----- watching -----
    def _start(self):
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._poll, POLL)

    def _poll(self, dt):
        if not self.recording:
            return
        try:
            text = Clipboard.paste()
        except Exception:
            return
        if text == self._last:
            return
        self._last = text
        if self.hist.add(text):
            self._persist()
            self.refresh()

    def set_recording(self, on):
        self.recording = on
        self._sync_buttons()

    def set_keep(self, on):
        self.keep = on
        self._persist()
        self._sync_buttons()

    def clear(self):
        self.hist.clear(keep_pinned=True)
        self._persist()
        self.refresh()

    def _persist(self):
        core.save_state(self.keep, self.hist.items)

    def _sync_buttons(self):
        self.rec_btn.text = "Recording: on" if self.recording else "Recording: paused"
        self.rec_btn.background_color = theme.ACCENT if self.recording else OFF
        self.keep_btn.text = "Keep after closing: " + ("on" if self.keep else "off")
        self.keep_btn.background_color = theme.ACCENT if self.keep else OFF

    # ----- list -----
    def on_pre_enter(self, *a):
        self.refresh()

    def refresh(self):
        self.grid.clear_widgets()
        q = self.search.text
        rows = [(i, it) for i, it in self.hist.pinned_first()
                if not q or q.lower() in it["text"].lower()]
        if not rows:
            lbl = Label(text="Nothing yet. Copy some text anywhere and it shows up here."
                        if not q else "No match.", font_size=sp(13), color=theme.MUTED,
                        size_hint_y=None, height=dp(80))
            self.grid.add_widget(lbl)
            return
        for i, it in rows:
            self.grid.add_widget(self._row(i, it))

    def _row(self, index, it):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
        use = Button(text=core.preview(it["text"]), font_size=sp(12), halign="left",
                     valign="middle", shorten=True, shorten_from="right")
        use.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(12), v[1])))
        use.bind(on_release=lambda *a, t=it["text"]: self.copy(t))
        row.add_widget(use)
        pin = Button(text="Pinned" if it["pinned"] else "Pin", size_hint_x=None,
                     width=dp(64), font_size=sp(11),
                     background_color=theme.ACCENT if it["pinned"] else OFF)
        pin.bind(on_release=lambda *a, i=index: self.pin(i))
        row.add_widget(pin)
        rm = Button(text="X", size_hint_x=None, width=dp(40), font_size=sp(12))
        rm.bind(on_release=lambda *a, i=index: self.remove(i))
        row.add_widget(rm)
        return row

    def copy(self, text):
        try:
            Clipboard.copy(text)
            self._last = text
            self.status.text = "Copied again."
        except Exception as e:
            self.status.text = f"Could not copy: {e}"

    def pin(self, i):
        self.hist.toggle_pin(i)
        self._persist()
        self.refresh()

    def remove(self, i):
        self.hist.remove(i)
        self._persist()
        self.refresh()
