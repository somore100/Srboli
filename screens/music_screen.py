# screens/music_screen.py
# Music Player — custom playlists saved as JSON, folder-to-playlist import,
# volume, pause, seek, autonext. Linux + Windows compatible.

import os
import sys
import json
import subprocess

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.clock import Clock
from kivy.metrics import dp

try:
    import pygame
    pygame.mixer.init()
    HAS_PYGAME = True
except Exception:
    HAS_PYGAME = False

AUDIO_EXTS     = (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac")
PLAYLISTS_DIR  = os.path.join(os.path.expanduser("~"), ".srboli_playlists")
os.makedirs(PLAYLISTS_DIR, exist_ok=True)


def _home():
    return os.path.expanduser("~")


def _open_external(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def _save_playlist(name, tracks):
    path = os.path.join(PLAYLISTS_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"name": name, "tracks": tracks}, f, indent=2)


def _load_playlist(name):
    path = os.path.join(PLAYLISTS_DIR, f"{name}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _list_playlists():
    return [f[:-5] for f in os.listdir(PLAYLISTS_DIR) if f.endswith(".json")]


class MusicScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # playback state
        self.playlist      = []     # current track list
        self.current_index = None
        self.playing       = False
        self.paused        = False
        self.autonext      = True
        self._current_start_pos = 0.0
        self._durations    = {}
        self._update_ev    = None
        self._current_playlist_name = None

        root = BoxLayout(orientation="vertical", padding=6, spacing=5)

        # ── tabs ──────────────────────────────────────────────────────────
        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(40))
        self.tabs.add_widget(self._build_player_tab())
        self.tabs.add_widget(self._build_playlists_tab())
        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "dashboard"))
        root.add_widget(back)

        self.add_widget(root)

    # ═══════════════════════════════════════════════════════════════════════
    # PLAYER TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_player_tab(self):
        tab = TabbedPanelItem(text="> Player")
        layout = BoxLayout(orientation="vertical", spacing=5, padding=5)

        # ── now playing ──
        self.track_label = Label(
            text="— no track —", size_hint_y=None, height=dp(26),
            font_size=13, shorten=True, shorten_from="left")
        layout.add_widget(self.track_label)

        # ── playlist name badge ──
        self._pl_badge = Label(
            text="", size_hint_y=None, height=dp(20),
            font_size=11, color=(0.5, 0.8, 1, 1))
        layout.add_widget(self._pl_badge)

        # ── timeline ──
        self.timeline = Slider(min=0, max=1, value=0,
                               size_hint_y=None, height=dp(40))
        self.timeline.bind(on_touch_up=self._on_slider_release)
        layout.add_widget(self.timeline)
        self.time_label = Label(text="0:00 / 0:00", size_hint_y=None,
                                height=dp(22), font_size=12)
        layout.add_widget(self.time_label)

        # ── volume ──
        vol_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=6)
        vol_row.add_widget(Label(text="", size_hint_x=None,
                                 width=dp(28), font_size=16))
        self.vol_slider = Slider(min=0, max=1, value=0.8)
        self.vol_slider.bind(value=self._set_volume)
        vol_row.add_widget(self.vol_slider)
        vol_row.add_widget(Label(text="", size_hint_x=None,
                                 width=dp(28), font_size=16))
        layout.add_widget(vol_row)

        # ── track list ──
        sv = ScrollView(size_hint=(1, 0.40))
        self._track_grid = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self._track_grid.bind(minimum_height=self._track_grid.setter("height"))
        sv.add_widget(self._track_grid)
        layout.add_widget(sv)

        # ── load row ──
        load_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=5)
        add_files_btn  = Button(text="➕ Files",   font_size=12)
        add_folder_btn = Button(text=" Folder",  font_size=12)
        clear_btn      = Button(text="Del Clear",   font_size=12,
                                size_hint_x=None, width=dp(80))
        add_files_btn.bind(on_release=self._load_files)
        add_folder_btn.bind(on_release=self._load_folder)
        clear_btn.bind(on_release=self._clear_playlist)
        load_row.add_widget(add_files_btn)
        load_row.add_widget(add_folder_btn)
        load_row.add_widget(clear_btn)
        layout.add_widget(load_row)

        # ── controls ──
        ctrl = BoxLayout(size_hint_y=None, height=dp(48), spacing=4)
        btns = [
            ("<<", self._prev_track),
            ("> Play",  self._play_current),
            ("|| Pause", self._toggle_pause),
            ("[] Stop",  self._stop),
            (">>", self._next_track),
            ("-10s", lambda *a: self._seek_relative(-10)),
            ("+10s", lambda *a: self._seek_relative(10)),
        ]
        for txt, cb in btns:
            b = Button(text=txt, font_size=12)
            b.bind(on_release=cb)
            ctrl.add_widget(b)
        self.autonext_btn = Button(text="AutoNext: ON", font_size=11,
                                   size_hint_x=None, width=dp(110))
        self.autonext_btn.bind(on_release=self._toggle_autonext)
        ctrl.add_widget(self.autonext_btn)
        layout.add_widget(ctrl)

        tab.add_widget(layout)
        return tab

    # ═══════════════════════════════════════════════════════════════════════
    # PLAYLISTS TAB
    # ═══════════════════════════════════════════════════════════════════════
    def _build_playlists_tab(self):
        tab = TabbedPanelItem(text="Copy Playlists")
        layout = BoxLayout(orientation="vertical", spacing=6, padding=8)

        # save current as playlist
        save_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
        save_row.add_widget(Label(text="Save current as:",
                                  size_hint_x=None, width=dp(130), font_size=13))
        self._pl_name_input = TextInput(
            hint_text="Playlist name", multiline=False, font_size=13)
        save_btn = Button(text="Save Save", size_hint_x=None, width=dp(80),
                          font_size=13)
        save_btn.bind(on_release=self._save_current_playlist)
        save_row.add_widget(self._pl_name_input)
        save_row.add_widget(save_btn)
        layout.add_widget(save_row)

        # saved playlists list
        layout.add_widget(Label(text="Saved playlists:",
                                size_hint_y=None, height=dp(24), font_size=13))
        sv = ScrollView()
        self._pl_grid = GridLayout(cols=1, spacing=4, size_hint_y=None)
        self._pl_grid.bind(minimum_height=self._pl_grid.setter("height"))
        sv.add_widget(self._pl_grid)
        layout.add_widget(sv)

        refresh_btn = Button(text=" Refresh list", size_hint_y=None,
                             height=dp(38), font_size=13)
        refresh_btn.bind(on_release=lambda *a: self._refresh_playlists_ui())
        layout.add_widget(refresh_btn)

        tab.add_widget(layout)
        self._refresh_playlists_ui()
        return tab

    # ═══════════════════════════════════════════════════════════════════════
    # PLAYLIST MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════
    def _save_current_playlist(self, *a):
        name = self._pl_name_input.text.strip()
        if not name:
            self._popup("Error", "Enter a playlist name first.")
            return
        if not self.playlist:
            self._popup("Error", "No tracks loaded to save.")
            return
        # sanitise filename
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        try:
            _save_playlist(safe, self.playlist)
            self._current_playlist_name = safe
            self._pl_badge.text = f"Playlist: {safe}"
            self._pl_name_input.text = ""
            self._refresh_playlists_ui()
            self._popup("Saved", f"Playlist '{safe}' saved.")
        except Exception as e:
            self._popup("Error", str(e))

    def _refresh_playlists_ui(self):
        if not hasattr(self, "_pl_grid"):
            return
        self._pl_grid.clear_widgets()
        for pl_name in sorted(_list_playlists()):
            row = BoxLayout(size_hint_y=None, height=dp(38), spacing=5)
            lbl = Button(text=pl_name, font_size=13, halign="left")
            lbl.bind(on_release=lambda inst, n=pl_name: self._load_saved_playlist(n))
            del_btn = Button(text="x", size_hint_x=None, width=dp(36),
                             font_size=13)
            del_btn.bind(on_release=lambda inst, n=pl_name: self._delete_playlist(n))
            row.add_widget(lbl)
            row.add_widget(del_btn)
            self._pl_grid.add_widget(row)

    def _load_saved_playlist(self, name):
        try:
            data = _load_playlist(name)
            tracks = [t for t in data["tracks"] if os.path.exists(t)]
            if not tracks:
                self._popup("Empty", "No valid tracks found in this playlist.")
                return
            self.playlist = tracks
            self.current_index = 0
            self._current_playlist_name = name
            self._pl_badge.text = f"Playlist: {name}"
            self._refresh_track_ui()
            self.tabs.switch_to(self.tabs.tab_list[-1])  # go to player tab
            self._play_current()
        except Exception as e:
            self._popup("Error", str(e))

    def _delete_playlist(self, name):
        path = os.path.join(PLAYLISTS_DIR, f"{name}.json")
        try:
            os.remove(path)
            self._refresh_playlists_ui()
        except Exception as e:
            self._popup("Error", str(e))

    # ═══════════════════════════════════════════════════════════════════════
    # LOADING TRACKS
    # ═══════════════════════════════════════════════════════════════════════
    def _load_files(self, *a):
        chooser = FileChooserIconView(path=_home(), multiselect=True)
        add_btn = Button(text="Add selected", size_hint_y=None, height=dp(44))
        layout  = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(add_btn)
        popup = Popup(title="Select audio files", content=layout,
                      size_hint=(0.92, 0.92))

        def _add(inst):
            added = 0
            for p in chooser.selection:
                if os.path.isfile(p) and p.lower().endswith(AUDIO_EXTS):
                    if p not in self.playlist:
                        self.playlist.append(p)
                        added += 1
            if added:
                self._refresh_track_ui()
            popup.dismiss()

        add_btn.bind(on_release=_add)
        popup.open()

    def _load_folder(self, *a):
        chooser = FileChooserIconView(path=_home(), dirselect=True,
                                      multiselect=False)
        btn = Button(text="Load folder", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Select folder", content=layout,
                      size_hint=(0.92, 0.92))

        def _load(inst):
            folder = chooser.path
            if chooser.selection and os.path.isdir(chooser.selection[0]):
                folder = chooser.selection[0]
            added = 0
            for fn in sorted(os.listdir(folder)):
                if fn.lower().endswith(AUDIO_EXTS):
                    p = os.path.join(folder, fn)
                    if p not in self.playlist:
                        self.playlist.append(p)
                        added += 1
            if added:
                self._refresh_track_ui()
            popup.dismiss()

        btn.bind(on_release=_load)
        popup.open()

    def _clear_playlist(self, *a):
        self._stop()
        self.playlist = []
        self.current_index = None
        self._current_playlist_name = None
        self._pl_badge.text = ""
        self._refresh_track_ui()

    def _refresh_track_ui(self):
        self._track_grid.clear_widgets()
        for idx, p in enumerate(self.playlist):
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=3)
            name = os.path.basename(p)
            # highlight current
            color = (0.2, 0.6, 1, 1) if idx == self.current_index else (1,1,1,1)
            btn = Button(text=name, font_size=11, color=color, halign="left")
            btn.bind(on_release=lambda inst, i=idx: self._select_and_play(i))
            rm = Button(text="x", size_hint_x=None, width=dp(30), font_size=11)
            rm.bind(on_release=lambda inst, i=idx: self._remove_track(i))
            row.add_widget(btn)
            row.add_widget(rm)
            self._track_grid.add_widget(row)

    def _remove_track(self, idx):
        if 0 <= idx < len(self.playlist):
            if self.current_index == idx:
                self._stop()
                self.current_index = None
            elif self.current_index and self.current_index > idx:
                self.current_index -= 1
            del self.playlist[idx]
            self._refresh_track_ui()

    def _select_and_play(self, idx):
        self.current_index = idx
        self._play_current()

    # ═══════════════════════════════════════════════════════════════════════
    # PLAYBACK
    # ═══════════════════════════════════════════════════════════════════════
    def _play_current(self, *a):
        if not self.playlist:
            return
        if self.current_index is None:
            self.current_index = 0
        track = self.playlist[self.current_index]
        self.track_label.text = f"Loading: {os.path.basename(track)}"
        self.paused = False

        if HAS_PYGAME:
            # Load in background thread to avoid UI freeze
            def _load():
                try:
                    pygame.mixer.music.load(track)
                    dur = self._get_duration(track)
                    def _on_main(dt):
                        try:
                            pygame.mixer.music.play()
                            pygame.mixer.music.set_volume(self.vol_slider.value)
                            self._current_start_pos = 0.0
                            self.playing = True
                            self.track_label.text = os.path.basename(track)
                            self.timeline.max = dur if dur and dur > 0 else 1.0
                            self.timeline.value = 0.0
                            self._refresh_track_ui()
                            self._restart_update()
                        except Exception as e:
                            self.track_label.text = f"Error: {e}"
                    Clock.schedule_once(_on_main, 0)
                except Exception as e:
                    def _err(dt):
                        self.track_label.text = f"Load error: {e}"
                        _open_external(track)
                        self.playing = True
                    Clock.schedule_once(_err, 0)

            import threading as _th
            _th.Thread(target=_load, daemon=True).start()
            return

        # fallback — no pygame
        _open_external(track)
        self.playing = True

    def _toggle_pause(self, *a):
        if not HAS_PYGAME or not self.playing:
            return
        if self.paused:
            pygame.mixer.music.unpause()
            self.paused = False
            self._restart_update()
        else:
            pygame.mixer.music.pause()
            self.paused = True
            if self._update_ev:
                self._update_ev.cancel()

    def _stop(self, *a):
        if HAS_PYGAME:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        self.playing = False
        self.paused  = False
        if self._update_ev:
            self._update_ev.cancel()
            self._update_ev = None
        self.time_label.text = "Stopped"

    def _set_volume(self, slider, val):
        if HAS_PYGAME:
            try:
                pygame.mixer.music.set_volume(val)
            except Exception:
                pass

    def _restart_update(self):
        if self._update_ev:
            self._update_ev.cancel()
        self._update_ev = Clock.schedule_interval(self._tick, 0.5)

    def _tick(self, dt):
        if not HAS_PYGAME:
            return
        try:
            busy = pygame.mixer.music.get_busy()
        except Exception:
            busy = False

        if self.playing and not busy and not self.paused:
            if self.autonext and self.playlist:
                self.current_index = (self.current_index + 1) % len(self.playlist)
                self._play_current()
            else:
                self._stop()
            return

        try:
            pos_ms = pygame.mixer.music.get_pos()
            pos = (pos_ms / 1000.0) if pos_ms >= 0 else 0.0
            absolute = self._current_start_pos + pos
            self.timeline.value = min(absolute, self.timeline.max)
            self.time_label.text = (
                f"{self._fmt(absolute)} / {self._fmt(self.timeline.max)}")
        except Exception:
            pass

    def _on_slider_release(self, slider, touch):
        if slider.collide_point(*touch.pos):
            self._seek_to(slider.value)

    def _seek_relative(self, seconds):
        try:
            pos_ms = pygame.mixer.music.get_pos()
            pos = (pos_ms / 1000.0) if pos_ms >= 0 else 0.0
        except Exception:
            pos = 0.0
        self._seek_to(self._current_start_pos + pos + seconds)

    def _seek_to(self, position):
        if not self.playlist or self.current_index is None or not HAS_PYGAME:
            return
        position = max(0.0, min(position, self.timeline.max - 0.01))
        track = self.playlist[self.current_index]
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(track)
            pygame.mixer.music.play(start=position)
            pygame.mixer.music.set_volume(self.vol_slider.value)
            self._current_start_pos = position
            self.playing = True
            self._restart_update()
        except Exception:
            pass

    def _prev_track(self, *a):
        if not self.playlist:
            return
        self.current_index = ((self.current_index or 0) - 1) % len(self.playlist)
        self._play_current()

    def _next_track(self, *a):
        if not self.playlist:
            return
        self.current_index = ((self.current_index or 0) + 1) % len(self.playlist)
        self._play_current()

    def _toggle_autonext(self, *a):
        self.autonext = not self.autonext
        self.autonext_btn.text = ("AutoNext: ON" if self.autonext
                                  else "AutoNext: OFF")

    def _get_duration(self, path):
        if path in self._durations:
            return self._durations[path]
        try:
            s = pygame.mixer.Sound(path)
            dur = s.get_length()
            self._durations[path] = dur
            return dur
        except Exception:
            return None

    @staticmethod
    def _fmt(seconds):
        try:
            s = int(seconds or 0)
            return f"{s // 60}:{s % 60:02d}"
        except Exception:
            return "0:00"

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=msg),
              size_hint=(0.72, 0.38)).open()
