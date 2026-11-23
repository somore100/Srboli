# core/mini_player.py - a small player that sits at the bottom of the screen,
# like a phone's built-in quick player: title, time, seek bar, play/pause,
# loop, volume (shared with the Music Player), "next track automatically"
# (when the file has other sounds beside it), a minimise arrow, and
# "Open in Srboli" for the full tools. It is not modal: minimised, the rest of
# the app stays usable.
# fmt_time / clamp / clean_title / siblings / next_sibling are pure.
import os

AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".oga"}
_FULLWIDTH = {"【": "[", "】": "]", "（": "(", "）": ")", "「": "[", "」": "]",
              "『": "[", "』": "]", "《": "<", "》": ">", "｜": "|", "～": "~",
              "：": ":", "　": " "}


def fmt_time(sec):
    m, s = divmod(int(max(0, sec or 0)), 60)
    return f"{m:02d}:{s:02d}"


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def clean_title(name):
    """The default font has no glyph for fullwidth brackets and similar; they
    showed as empty boxes. Swap them for plain ASCII."""
    return "".join(_FULLWIDTH.get(c, c) for c in (name or ""))


def siblings(path):
    """Sounds in the same folder as `path`, sorted by name ([] if alone)."""
    try:
        folder = os.path.dirname(path)
        names = sorted(n for n in os.listdir(folder)
                       if os.path.splitext(n)[1].lower() in AUDIO_EXT)
    except OSError:
        return []
    out = [os.path.join(folder, n) for n in names]
    return out if len(out) > 1 and path in out else []


def next_sibling(path, loop=False):
    """The track after `path` in its folder (None at the end unless `loop`)."""
    sib = siblings(path)
    if not sib:
        return None
    i = sib.index(path) + 1
    if i < len(sib):
        return sib[i]
    return sib[0] if loop else None


class MiniPlayer:
    def __init__(self, path, name, on_open_in_app, on_close=None, loader=None):
        from kivy.clock import Clock
        from kivy.core.audio import SoundLoader
        from kivy.core.window import Window
        from kivy.graphics import Color, RoundedRectangle
        from kivy.metrics import dp, sp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.checkbox import CheckBox
        from kivy.uix.label import Label
        from kivy.uix.slider import Slider
        from core import music_prefs, theme

        self.path, self._on_open, self._on_close = path, on_open_in_app, on_close
        self._name = name
        self._seeking = False
        self._loop = False
        self._autonext = False
        self._paused_at = 0
        self._Clock, self._Window, self._dp = Clock, Window, dp
        self._loader = loader or SoundLoader.load
        self._sibs = siblings(path)
        self.sound = None
        self._tick_ev = None
        self._open = False
        self.collapsed = False

        self.panel = BoxLayout(orientation="vertical", spacing=dp(8),
                               padding=dp(16), size_hint=(0.96, None),
                               pos_hint={"center_x": 0.5, "y": 0.02})
        with self.panel.canvas.before:
            Color(*theme.SURFACE)
            self._bg = RoundedRectangle(pos=self.panel.pos, size=self.panel.size,
                                        radius=[dp(24)])
        self.panel.bind(pos=lambda w, v: setattr(self._bg, "pos", v),
                        size=lambda w, v: setattr(self._bg, "size", v))

        head = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.title = Label(text="", font_size=sp(16), bold=True, halign="left",
                           valign="middle", shorten=True, shorten_from="right")
        self.title.bind(size=lambda w, v: setattr(w, "text_size", v))
        head.add_widget(self.title)
        self.mini_play = Button(text="Pause", size_hint_x=None, width=dp(70),
                                font_size=sp(12))
        self.mini_play.bind(on_release=lambda *a: self.toggle())
        self.mini_play.opacity, self.mini_play.disabled = 0, True
        head.add_widget(self.mini_play)
        self.fold_btn = Button(text="v", size_hint_x=None, width=dp(44),
                               font_size=sp(16))
        self.fold_btn.bind(on_release=lambda *a: self.set_collapsed(not self.collapsed))
        head.add_widget(self.fold_btn)
        self.panel.add_widget(head)

        self.body = BoxLayout(orientation="vertical", spacing=dp(8))
        self.time = Label(text="00:00 / 00:00", font_size=sp(13),
                          color=theme.MUTED, halign="left", valign="middle",
                          size_hint_y=None, height=dp(20))
        self.time.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.time)

        self.seek = Slider(min=0, max=1, value=0, size_hint_y=None, height=dp(36))
        self.seek.bind(on_touch_down=self._seek_down, on_touch_up=self._seek_up)
        self.body.add_widget(self.seek)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.play_btn = Button(text="Pause", font_size=sp(14))
        self.play_btn.bind(on_release=lambda *a: self.toggle())
        self.loop_btn = Button(text="Loop: off", font_size=sp(14))
        self.loop_btn.bind(on_release=lambda *a: self.toggle_loop())
        row.add_widget(self.play_btn)
        row.add_widget(self.loop_btn)
        self.body.add_widget(row)

        vrow = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        vrow.add_widget(Label(text="Volume", font_size=sp(12), color=theme.MUTED,
                              size_hint_x=None, width=dp(60)))
        self.vol = Slider(min=0, max=1, value=music_prefs.load_volume())
        self.vol.bind(value=lambda w, v: self.set_volume(v))
        vrow.add_widget(self.vol)
        self.vol_lbl = Label(text="", font_size=sp(12), size_hint_x=None,
                             width=dp(44))
        vrow.add_widget(self.vol_lbl)
        self.body.add_widget(vrow)

        self.auto_cb = None
        if self._sibs:
            arow = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
            self.auto_cb = CheckBox(active=False, size_hint=(None, None),
                                    size=(dp(24), dp(24)))
            self.auto_cb.bind(active=lambda w, v: setattr(self, "_autonext", v))
            arow.add_widget(self.auto_cb)
            n = len(self._sibs)
            arow.add_widget(Label(text=f"Play the next track automatically "
                                       f"({n} in this folder)", font_size=sp(12),
                                  halign="left", valign="middle"))
            self.body.add_widget(arow)

        row2 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        close = Button(text="Close", font_size=sp(14))
        close.bind(on_release=lambda *a: self.close())
        openb = Button(text="Open in Srboli", font_size=sp(14),
                       background_color=theme.ACCENT)
        openb.bind(on_release=lambda *a: self.open_in_app())
        row2.add_widget(close)
        row2.add_widget(openb)
        self.body.add_widget(row2)
        self.panel.add_widget(self.body)

        self._set_vol_label(self.vol.value)
        self._load(path, name)
        self._relayout()

    # -- layout -------------------------------------------------------------
    def _relayout(self):
        dp = self._dp
        if self.collapsed:
            self.panel.height = dp(34) + dp(32)
        else:
            rows = 20 + 36 + 48 + 36 + 48 + (34 if self.auto_cb else 0)
            self.panel.height = dp(34) + dp(16 * 2) + dp(rows) + dp(8 * (6 if self.auto_cb else 5))

    def set_collapsed(self, on):
        self.collapsed = bool(on)
        self.body.opacity = 0 if on else 1
        self.body.disabled = bool(on)
        if on:
            self.body.size_hint_y, self.body.height = None, 0
        else:
            self.body.size_hint_y = 1
        self.mini_play.opacity = 1 if on else 0
        self.mini_play.disabled = not on
        self.fold_btn.text = "^" if on else "v"
        self._relayout()

    # -- control ------------------------------------------------------------
    def _load(self, path, name):
        self.path = path
        self.title.text = clean_title(name or os.path.basename(path))
        self.sound = self._loader(path)
        if self.sound:
            self.sound.volume = self.vol.value
            self.sound.loop = self._loop
        self._paused_at = 0

    def show(self):
        self._Window.add_widget(self.panel)
        self._open = True
        self._start()
        self._tick_ev = self._Clock.schedule_interval(self._tick, 0.25)

    def _start(self):
        if self.sound:
            self.sound.play()
            self.seek.max = max(1.0, float(self.sound.length or 1))
            self.play_btn.text = self.mini_play.text = "Pause"
        else:
            self.time.text = "Can't play this file here"

    def toggle(self):
        s = self.sound
        if not s:
            return
        if s.state == "play":
            self._paused_at = s.get_pos()
            s.stop()
            self.play_btn.text = self.mini_play.text = "Play"
        else:
            s.play()
            s.seek(self._paused_at or 0)
            self.play_btn.text = self.mini_play.text = "Pause"

    def toggle_loop(self):
        self._loop = not self._loop
        if self.sound:
            self.sound.loop = self._loop
        self.loop_btn.text = "Loop: on" if self._loop else "Loop: off"

    def _set_vol_label(self, v):
        self.vol_lbl.text = f"{int(round(clamp(v) * 100))}%"

    def set_volume(self, v):
        v = clamp(v)
        from core import music_prefs
        music_prefs.save_volume(v)
        self._set_vol_label(v)
        if self.sound:
            self.sound.volume = v

    def _seek_down(self, w, touch):
        if w.collide_point(*touch.pos):
            self._seeking = True

    def _seek_up(self, w, touch):
        if self._seeking and self.sound:
            self.sound.seek(self.seek.value)
        self._seeking = False

    def _tick(self, dt):
        s = self.sound
        if not s:
            return
        length = float(s.length or 0)
        if length and abs(self.seek.max - length) > 0.5:
            self.seek.max = max(1.0, length)
        pos = s.get_pos()
        if not self._seeking:
            self.seek.value = clamp(pos, 0, self.seek.max)
        self.time.text = f"{fmt_time(pos)} / {fmt_time(length)}"
        if s.state != "play" and self.play_btn.text == "Pause" and not self._loop:
            nxt = next_sibling(self.path) if self._autonext else None
            if nxt:
                self.play_next(nxt)
            else:
                self.play_btn.text = self.mini_play.text = "Play"   # the end
                self._paused_at = 0

    def play_next(self, path):
        if self.sound:
            self.sound.stop()
            self.sound.unload()
        self._load(path, os.path.basename(path))
        self._start()

    def _stop(self):
        if self._tick_ev:
            self._tick_ev.cancel()
            self._tick_ev = None
        if self.sound:
            self.sound.stop()
            self.sound.unload()
            self.sound = None
        if self._open:
            self._open = False
            self._Window.remove_widget(self.panel)

    def close(self):
        self._stop()
        if self._on_close:
            self._on_close()

    def open_in_app(self):
        self._stop()
        self._on_open()
