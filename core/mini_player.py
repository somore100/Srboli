# core/mini_player.py - a small player that slides up from the bottom, like a
# phone's built-in quick player: title, time, seek bar, play/pause, loop,
# volume, and "Open in Srboli" for the full tools.
# fmt_time / clamp are pure; MiniPlayer needs Kivy (SoundLoader).
import os


def fmt_time(sec):
    m, s = divmod(int(max(0, sec or 0)), 60)
    return f"{m:02d}:{s:02d}"


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


class MiniPlayer:
    def __init__(self, path, name, on_open_in_app, on_close=None, loader=None):
        from kivy.clock import Clock
        from kivy.core.audio import SoundLoader
        from kivy.graphics import Color, RoundedRectangle
        from kivy.metrics import dp, sp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.modalview import ModalView
        from kivy.uix.slider import Slider
        from core import theme

        self.path, self._on_open, self._on_close = path, on_open_in_app, on_close
        self._seeking = False
        self._loop = False
        self._Clock = Clock
        self.sound = (loader or SoundLoader.load)(path)

        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(16))
        with box.canvas.before:
            Color(*theme.SURFACE)
            self._bg = RoundedRectangle(pos=box.pos, size=box.size, radius=[dp(24)])
        box.bind(pos=lambda w, v: setattr(self._bg, "pos", v),
                 size=lambda w, v: setattr(self._bg, "size", v))

        self.title = Label(text=name or os.path.basename(path), font_size=sp(16),
                           bold=True, halign="left", valign="middle",
                           shorten=True, shorten_from="right",
                           size_hint_y=None, height=dp(28))
        self.title.bind(size=lambda w, v: setattr(w, "text_size", v))
        box.add_widget(self.title)
        self.time = Label(text="00:00 / 00:00", font_size=sp(13),
                          color=theme.MUTED, halign="left", valign="middle",
                          size_hint_y=None, height=dp(20))
        self.time.bind(size=lambda w, v: setattr(w, "text_size", v))
        box.add_widget(self.time)

        self.seek = Slider(min=0, max=1, value=0, size_hint_y=None, height=dp(36))
        self.seek.bind(on_touch_down=self._seek_down, on_touch_up=self._seek_up)
        box.add_widget(self.seek)

        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.play_btn = Button(text="Pause", font_size=sp(14))
        self.play_btn.bind(on_release=lambda *a: self.toggle())
        self.loop_btn = Button(text="Loop: off", font_size=sp(14))
        self.loop_btn.bind(on_release=lambda *a: self.toggle_loop())
        row.add_widget(self.play_btn)
        row.add_widget(self.loop_btn)
        box.add_widget(row)

        vrow = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        vrow.add_widget(Label(text="Volume", font_size=sp(12), color=theme.MUTED,
                              size_hint_x=None, width=dp(60)))
        self.vol = Slider(min=0, max=1, value=1)
        self.vol.bind(value=lambda w, v: self.set_volume(v))
        vrow.add_widget(self.vol)
        box.add_widget(vrow)

        row2 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        close = Button(text="Close", font_size=sp(14))
        close.bind(on_release=lambda *a: self.close())
        openb = Button(text="Open in Srboli", font_size=sp(14),
                       background_color=theme.ACCENT)
        openb.bind(on_release=lambda *a: self.open_in_app())
        row2.add_widget(close)
        row2.add_widget(openb)
        box.add_widget(row2)

        self.view = ModalView(size_hint=(0.96, None), height=dp(300),
                              pos_hint={"center_x": 0.5, "y": 0.02},
                              background="", background_color=(0, 0, 0, 0),
                              overlay_color=(0, 0, 0, 0.35), auto_dismiss=False)
        self.view.add_widget(box)
        self.view.bind(on_dismiss=lambda *a: self._stop())
        self._tick_ev = None

    # -- control ------------------------------------------------------------
    def show(self):
        self.view.open()
        if self.sound:
            self.sound.play()
            self.seek.max = max(1.0, float(self.sound.length or 1))
        else:
            self.time.text = "Can't play this file here"
        self._tick_ev = self._Clock.schedule_interval(self._tick, 0.25)

    def toggle(self):
        s = self.sound
        if not s:
            return
        if s.state == "play":
            self._paused_at = s.get_pos()
            s.stop()
            self.play_btn.text = "Play"
        else:
            s.play()
            s.seek(getattr(self, "_paused_at", 0) or 0)
            self.play_btn.text = "Pause"

    def toggle_loop(self):
        self._loop = not self._loop
        if self.sound:
            self.sound.loop = self._loop
        self.loop_btn.text = "Loop: on" if self._loop else "Loop: off"

    def set_volume(self, v):
        if self.sound:
            self.sound.volume = clamp(v)

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
            self.play_btn.text = "Play"         # reached the end
            self._paused_at = 0

    def _stop(self):
        if self._tick_ev:
            self._tick_ev.cancel()
            self._tick_ev = None
        if self.sound:
            self.sound.stop()
            self.sound.unload()
            self.sound = None

    def close(self):
        self.view.dismiss()
        if self._on_close:
            self._on_close()

    def open_in_app(self):
        self.view.dismiss()
        self._on_open()
