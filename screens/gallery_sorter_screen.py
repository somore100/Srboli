# screens/gallery_sorter_screen.py
# Gallery Sorter v4:
# - Video info panel (format, size, duration) next to thumbnail
# - In-app video player with time display and fading play button
# - Frame strip as toggle option (not auto-load, prevents lag)
# - Undo, subfolder sort buttons, multi-source

import os, sys, json, shutil, threading, subprocess, time, math

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.uix.checkbox import CheckBox
from kivy.uix.slider import Slider
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window

try:
    from kivy.uix.video import Video as KivyVideo
    HAS_KIVY_VIDEO = True
except Exception:
    HAS_KIVY_VIDEO = False

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

import app_data

IMAGE_EXTS = {".jpg",".jpeg",".png",".bmp",".gif",".webp",".tiff",".tif"}
VIDEO_EXTS = {".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

def _home(): return os.path.expanduser("~")
def _is_video(p): return os.path.splitext(p)[1].lower() in VIDEO_EXTS
def _is_image(p): return os.path.splitext(p)[1].lower() in IMAGE_EXTS
def _is_media(p): return os.path.splitext(p)[1].lower() in MEDIA_EXTS

def _open_ext(path):
    try:
        if sys.platform.startswith("win"):   os.startfile(path)
        elif sys.platform == "darwin":       subprocess.Popen(["open", path])
        else:                                subprocess.Popen(["xdg-open", path])
    except Exception: pass

def _fmt_size(b):
    if b < 1024:       return f"{b} B"
    elif b < 1048576:  return f"{b/1024:.1f} KB"
    elif b < 1073741824: return f"{b/1048576:.1f} MB"
    return f"{b/1073741824:.2f} GB"

def _fmt_dur(seconds):
    s = int(max(0, seconds))
    h = s // 3600; m = (s % 3600) // 60; sc = s % 60
    return f"{h}:{m:02d}:{sc:02d}" if h else f"{m}:{sc:02d}"


def _video_info(path):
    """Returns (duration_str, width_str, height_str)."""
    if not HAS_CV2:
        return "?", "?", "?"
    try:
        cap   = cv2.VideoCapture(path)
        fps   = cap.get(cv2.CAP_PROP_FPS) or 1
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        w     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        dur = total / fps if fps else 0
        return _fmt_dur(dur), str(w), str(h)
    except Exception:
        return "?", "?", "?"


def _make_thumb(path, offset_pct=0.05):
    """Generate thumbnail JPEG, return path or None."""
    cache = app_data.subdir("gallery_cache")
    name  = f"t_{abs(hash(path + str(offset_pct)))}.jpg"
    thumb = os.path.join(cache, name)
    if os.path.exists(thumb):
        return thumb
    try:
        if _is_image(path) and HAS_PIL:
            img = PILImage.open(path).convert("RGB")
            img.thumbnail((640, 480))
            img.save(thumb, "JPEG", quality=82)
            return thumb
        if _is_video(path) and HAS_CV2:
            cap   = cv2.VideoCapture(path)
            total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.set(cv2.CAP_PROP_POS_FRAMES,
                    max(0, int(total * offset_pct)))
            ok, frame = cap.read()
            cap.release()
            if ok:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil = PILImage.fromarray(rgb)
                pil.thumbnail((640, 480))
                pil.save(thumb, "JPEG", quality=82)
                return thumb
    except Exception as e:
        print("Thumb error:", e)
    return None


def _make_strip_thumbs(path, n=10):
    """Generate n thumbnail paths at even intervals through a video."""
    results = []
    if not (HAS_CV2 and HAS_PIL and _is_video(path)):
        return results
    cache = app_data.subdir("gallery_cache")
    try:
        cap   = cv2.VideoCapture(path)
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        for i in range(n):
            pct  = i / max(n - 1, 1)
            name = f"strip_{abs(hash(path))}_{i}.jpg"
            p    = os.path.join(cache, name)
            if not os.path.exists(p):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * pct))
                ok, frame = cap.read()
                if ok:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    PILImage.fromarray(rgb).save(p, "JPEG", quality=65)
                else:
                    p = ""
            results.append(p)
        cap.release()
    except Exception as e:
        print("Strip error:", e)
    return results


# -- In-app video player popup -----------------------------------------------
class VideoPlayerPopup(Popup):
    def __init__(self, path, **kw):
        self._path     = path
        self._dragging = False

        layout = BoxLayout(orientation="vertical", spacing=2, padding=4)
        super().__init__(title=os.path.basename(path),
                         content=layout, size_hint=(0.96, 0.94), **kw)

        if HAS_KIVY_VIDEO:
            self._vf = FloatLayout(size_hint_y=0.88)

            self._vid = KivyVideo(
                source=path, state="play",
                allow_stretch=True, keep_ratio=True,
                size_hint=(1, 1), pos_hint={"x": 0, "y": 0}
            )
            self._vf.add_widget(self._vid)

            # Control overlay at bottom
            self._ctrl_overlay = BoxLayout(
                orientation="vertical", spacing=2, padding=(4, 2),
                size_hint=(1, None), height=dp(68),
                pos_hint={"x": 0, "y": 0},
                opacity=1.0,
            )
            with self._ctrl_overlay.canvas.before:
                from kivy.graphics import Color as _C, Rectangle as _R
                _C(0, 0, 0, 0.45)
                self._cbg = _R(pos=self._ctrl_overlay.pos,
                               size=self._ctrl_overlay.size)
            self._ctrl_overlay.bind(
                pos=lambda inst, v: setattr(self._cbg, "pos", v),
                size=lambda inst, v: setattr(self._cbg, "size", v))

            # Time row: current | hover hint | total
            tr = BoxLayout(size_hint_y=None, height=dp(20), spacing=4)
            self._cur_lbl   = Label(text="0:00", font_size=12,
                                    size_hint_x=None, width=dp(46),
                                    color=(1,1,1,1))
            self._hover_lbl = Label(text="", font_size=11,
                                    color=(0.75, 0.9, 1, 1))
            self._dur_lbl   = Label(text="0:00", font_size=12,
                                    size_hint_x=None, width=dp(46),
                                    halign="right", color=(1,1,1,1))
            tr.add_widget(self._cur_lbl)
            tr.add_widget(self._hover_lbl)
            tr.add_widget(self._dur_lbl)
            self._ctrl_overlay.add_widget(tr)

            # Seek slider
            self._seek_sl = Slider(min=0, max=1, value=0,
                                   size_hint_y=None, height=dp(26),
                                   cursor_size=(dp(12), dp(12)))
            self._seek_sl.bind(on_touch_down=self._seek_down)
            self._seek_sl.bind(on_touch_move=self._seek_move)
            self._seek_sl.bind(on_touch_up=self._seek_up)
            self._ctrl_overlay.add_widget(self._seek_sl)
            self._vf.add_widget(self._ctrl_overlay)

            # Centre play/pause button
            self._play_btn = Button(
                text="||",
                size_hint=(None, None), size=(dp(58), dp(38)),
                pos_hint={"center_x": 0.5, "center_y": 0.6},
                opacity=1.0,
                background_color=(0, 0, 0, 0.55),
                color=(1,1,1,1), font_size=18,
            )
            self._play_btn.bind(on_release=self._toggle_play)
            self._vf.add_widget(self._play_btn)
            self._vf.bind(on_touch_down=lambda inst, t: self._show_controls())
            layout.add_widget(self._vf)

            # Bottom buttons
            bot = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
            for txt, cb in [("Play/Pause", self._toggle_play),
                             ("Stop", lambda *a: setattr(self._vid,"state","stop")),
                             ("Close", lambda *a: self.dismiss())]:
                b = Button(text=txt, font_size=12)
                b.bind(on_release=cb)
                bot.add_widget(b)
            layout.add_widget(bot)

            self._update_ev = Clock.schedule_interval(self._update_pos, 0.25)
            self._fade_ev   = None
            self._schedule_fade()
        else:
            layout.add_widget(Label(
                text="ffpyplayer not installed.\nRun: python3 -m pip install ffpyplayer",
                halign="center", font_size=14))
            fb = Button(text="Open in system player",
                        size_hint_y=None, height=dp(46))
            fb.bind(on_release=lambda *a: (_open_ext(path), self.dismiss()))
            layout.add_widget(fb)
            cl = Button(text="Close", size_hint_y=None, height=dp(40))
            cl.bind(on_release=lambda *a: self.dismiss())
            layout.add_widget(cl)

    def _toggle_play(self, *a):
        if not hasattr(self, "_vid"): return
        if self._vid.state == "play":
            self._vid.state = "pause"
            self._play_btn.text = ">"
        else:
            self._vid.state = "play"
            self._play_btn.text = "||"
        self._show_controls()

    def _seek_down(self, sl, touch):
        if sl.collide_point(*touch.pos):
            self._dragging = True
            self._update_hover(touch.x)
            self._show_controls()

    def _seek_move(self, sl, touch):
        if self._dragging:
            self._update_hover(touch.x)

    def _seek_up(self, sl, touch):
        if self._dragging:
            self._dragging = False
            if hasattr(self, "_vid"):
                self._vid.seek(sl.value)
            self._hover_lbl.text = ""
            self._show_controls()

    def _update_hover(self, tx):
        if not hasattr(self, "_vid"): return
        sl = self._seek_sl
        frac = max(0.0, min(1.0, (tx - sl.x) / max(sl.width, 1)))
        try:
            dur = self._vid.duration
            if dur and dur > 0:
                self._hover_lbl.text = f"[ {_fmt_dur(frac * dur)} ]"
        except Exception:
            pass

    def _update_pos(self, dt):
        if not hasattr(self, "_vid") or self._dragging: return
        try:
            pos = self._vid.position
            dur = self._vid.duration
            if dur and dur > 0:
                self._cur_lbl.text  = _fmt_dur(pos * dur)
                self._dur_lbl.text  = _fmt_dur(dur)
                self._seek_sl.value = pos
            else:
                self._cur_lbl.text = "0:00"
        except Exception:
            pass

    def _show_controls(self):
        from kivy.animation import Animation
        if hasattr(self, "_ctrl_overlay"):
            Animation.cancel_all(self._ctrl_overlay)
            Animation.cancel_all(self._play_btn)
            self._ctrl_overlay.opacity = 1.0
            self._play_btn.opacity     = 1.0
        if self._fade_ev: self._fade_ev.cancel()
        self._fade_ev = Clock.schedule_once(self._fade_controls, 4.0)

    def _schedule_fade(self):
        self._fade_ev = Clock.schedule_once(self._fade_controls, 4.0)

    def _fade_controls(self, dt):
        from kivy.animation import Animation
        if hasattr(self, "_ctrl_overlay"):
            Animation(opacity=0, duration=0.8).start(self._ctrl_overlay)
            Animation(opacity=0, duration=0.8).start(self._play_btn)

    def on_dismiss(self):
        if hasattr(self, "_update_ev"): self._update_ev.cancel()
        if hasattr(self, "_fade_ev") and self._fade_ev: self._fade_ev.cancel()
        if hasattr(self, "_vid"):
            self._vid.state = "stop"
            self._vid.unload()

# ── Frame strip popup ─────────────────────────────────────────────────────────
class FrameStripPopup(Popup):
    """Show N frames from video as image slides."""
    def __init__(self, path, n=10, **kw):
        layout = BoxLayout(orientation="vertical", padding=4, spacing=4)
        super().__init__(title=f"Frames: {os.path.basename(path)}",
                         content=layout, size_hint=(0.96, 0.94), **kw)

        self._loading = Label(text="Generating frames...", font_size=14)
        layout.add_widget(self._loading)

        self._img_row = BoxLayout(spacing=3)
        layout.add_widget(self._img_row)

        self._frame_idx = 0
        self._frame_paths = []

        # nav
        nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        prev_b = Button(text="< Prev")
        next_b = Button(text="Next >")
        self._frame_lbl = Label(text="0/0", size_hint_x=None, width=dp(60))
        close_b = Button(text="Close", size_hint_x=None, width=dp(80))
        prev_b.bind(on_release=self._prev)
        next_b.bind(on_release=self._next)
        close_b.bind(on_release=lambda *a: self.dismiss())
        for w in (prev_b, self._frame_lbl, next_b, close_b):
            nav.add_widget(w)
        layout.add_widget(nav)

        # load frames in bg
        self._n = n
        threading.Thread(target=self._load_frames, args=(path,),
                         daemon=True).start()

    def _load_frames(self, path):
        paths = _make_strip_thumbs(path, self._n)
        def _apply(dt):
            self._frame_paths = paths
            self._loading.text = f"{len(paths)} frames ready"
            self._show_frame(0)
        Clock.schedule_once(_apply, 0)

    def _show_frame(self, idx):
        if not self._frame_paths: return
        idx = max(0, min(idx, len(self._frame_paths) - 1))
        self._frame_idx = idx
        self._img_row.clear_widgets()
        p = self._frame_paths[idx]
        if p and os.path.exists(p):
            img = KivyImage(source=p, allow_stretch=True, keep_ratio=True)
            self._img_row.add_widget(img)
        else:
            self._img_row.add_widget(Label(text="Frame unavailable"))
        self._frame_lbl.text = f"{idx+1}/{len(self._frame_paths)}"

    def _prev(self, *a): self._show_frame(self._frame_idx - 1)
    def _next(self, *a): self._show_frame(self._frame_idx + 1)


# ── Main Screen ───────────────────────────────────────────────────────────────
class GallerySorterScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._sources    = []
        self._files      = []
        self._index      = 0
        self._dest_tree  = []
        self._queue      = []
        self._undo_stack = []
        self._instant    = True

        root = BoxLayout(orientation="vertical", spacing=3, padding=4)

        # ── top bar ───────────────────────────────────────────────────────
        top = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        add_src = Button(text="+ Source", size_hint_x=None, width=dp(95))
        add_src.bind(on_release=self._add_source)
        self._src_lbl = Label(text="No sources", font_size=11, halign="left")
        self._src_lbl.bind(size=self._src_lbl.setter("text_size"))
        save_c = Button(text="Save cfg", size_hint_x=None, width=dp(78))
        save_c.bind(on_release=self._save_config)
        load_c = Button(text="Load cfg", size_hint_x=None, width=dp(78))
        load_c.bind(on_release=self._load_config)
        undo_b = Button(text="Undo", size_hint_x=None, width=dp(60),
                        background_color=(0.5, 0.3, 0.1, 1))
        undo_b.bind(on_release=self._undo)
        top.add_widget(add_src); top.add_widget(self._src_lbl)
        top.add_widget(save_c);  top.add_widget(load_c)
        top.add_widget(undo_b)
        root.add_widget(top)

        # ── options ───────────────────────────────────────────────────────
        opts = BoxLayout(size_hint_y=None, height=dp(26), spacing=8)
        self._instant_cb = CheckBox(active=True, size_hint_x=None,
                                    size=(dp(20), dp(20)))
        self._instant_cb.bind(active=lambda cb, v: setattr(self, "_instant", v))
        opts.add_widget(self._instant_cb)
        opts.add_widget(Label(text="Instant move", size_hint_x=None,
                              width=dp(90), font_size=11))
        self._commit_btn = Button(text="Commit (0)", size_hint_x=None,
                                  width=dp(100), font_size=11, disabled=True)
        self._commit_btn.bind(on_release=self._commit)
        opts.add_widget(self._commit_btn)
        root.add_widget(opts)

        # ── main area ─────────────────────────────────────────────────────
        mid = BoxLayout(spacing=4, size_hint_y=0.52)

        # preview + info
        pbox = BoxLayout(orientation="vertical", size_hint_x=0.60, spacing=2)

        # float for image + play overlay
        self._pf = FloatLayout(size_hint_y=0.78)
        self._preview_img = KivyImage(
            allow_stretch=True, keep_ratio=True,
            size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self._pf.add_widget(self._preview_img)

        # play button overlay
        self._play_btn = Button(
            text="PLAY",
            size_hint=(None, None), size=(dp(68), dp(36)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            opacity=0,
            background_color=(0, 0, 0, 0.6),
            color=(1, 1, 1, 1), font_size=13,
        )
        self._play_btn.bind(on_release=self._open_player)
        self._pf.add_widget(self._play_btn)

        # frame strip button (on preview, video only)
        self._strip_btn = Button(
            text="Frames",
            size_hint=(None, None), size=(dp(68), dp(28)),
            pos_hint={"right": 1, "y": 0},
            opacity=0,
            background_color=(0, 0, 0, 0.55),
            color=(1, 1, 1, 1), font_size=11,
        )
        self._strip_btn.bind(on_release=self._open_strip)
        self._pf.add_widget(self._strip_btn)

        pbox.add_widget(self._pf)

        # info label (format, size, duration, resolution)
        self._info_lbl = Label(
            text="", size_hint_y=None, height=dp(36),
            font_size=11, halign="left", valign="top",
            color=(0.7, 0.85, 1, 1))
        self._info_lbl.bind(size=self._info_lbl.setter("text_size"))
        pbox.add_widget(self._info_lbl)

        self._file_lbl = Label(text="--", size_hint_y=None, height=dp(16),
                               font_size=10, shorten=True,
                               shorten_from="left")
        pbox.add_widget(self._file_lbl)

        ren = BoxLayout(size_hint_y=None, height=dp(28), spacing=3)
        self._ren_in = TextInput(hint_text="Rename (no ext)",
                                 multiline=False, font_size=11)
        ren_b = Button(text="Rename", size_hint_x=None, width=dp(70),
                       font_size=11)
        ren_b.bind(on_release=self._rename)
        ren.add_widget(self._ren_in); ren.add_widget(ren_b)
        pbox.add_widget(ren)
        mid.add_widget(pbox)

        # dest panel
        dpan = BoxLayout(orientation="vertical", size_hint_x=0.40, spacing=3)
        dpan.add_widget(Label(text="Destinations", size_hint_y=None,
                              height=dp(18), font_size=12, bold=True))
        da = BoxLayout(size_hint_y=None, height=dp(28), spacing=3)
        self._dest_in = TextInput(hint_text="Label", multiline=False,
                                  font_size=11, size_hint_x=0.38)
        pb = Button(text="Pick", size_hint_x=None, width=dp(58), font_size=10)
        cb2 = Button(text="Create", size_hint_x=None, width=dp(64), font_size=10)
        pb.bind(on_release=self._add_dest_pick)
        cb2.bind(on_release=self._add_dest_create)
        da.add_widget(self._dest_in); da.add_widget(pb); da.add_widget(cb2)
        dpan.add_widget(da)
        sv_d = ScrollView()
        self._dest_grid = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self._dest_grid.bind(minimum_height=self._dest_grid.setter("height"))
        sv_d.add_widget(self._dest_grid)
        dpan.add_widget(sv_d)
        mid.add_widget(dpan)
        root.add_widget(mid)

        # ── nav ───────────────────────────────────────────────────────────
        nav = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        self._prog = Label(text="0/0", size_hint_x=None, width=dp(52),
                           font_size=12)
        pv = Button(text="< Prev", size_hint_x=None, width=dp(72))
        pv.bind(on_release=lambda *a: self._step(-1))
        ps = Button(text="Pass >")
        ps.bind(on_release=lambda *a: self._step(1))
        dl = Button(text="Delete", size_hint_x=None, width=dp(76),
                    background_color=(0.7, 0.15, 0.15, 1))
        dl.bind(on_release=self._delete)
        nav.add_widget(self._prog); nav.add_widget(pv)
        nav.add_widget(ps);         nav.add_widget(dl)
        root.add_widget(nav)

        # ── sort buttons ──────────────────────────────────────────────────
        sv_s = ScrollView(size_hint_y=None, height=dp(48))
        self._sort_row = GridLayout(rows=1, cols=1, size_hint=(None, 1),
                                    spacing=3)
        self._sort_row.bind(minimum_width=self._sort_row.setter("width"))
        sv_s.add_widget(self._sort_row)
        root.add_widget(sv_s)

        # ── status + back ─────────────────────────────────────────────────
        bot = BoxLayout(size_hint_y=None, height=dp(28), spacing=5)
        self._status = Label(text="", font_size=10, halign="left")
        self._status.bind(size=self._status.setter("text_size"))
        bk = Button(text="Back", size_hint_x=None, width=dp(68))
        bk.bind(on_release=self._go_back)
        bot.add_widget(self._status); bot.add_widget(bk)
        root.add_widget(bot)

        self.add_widget(root)

    # ── lifecycle ─────────────────────────────────────────────────────────
    def on_enter(self, *a):
        Window.bind(on_key_down=self._key)
    def on_leave(self, *a):
        Window.unbind(on_key_down=self._key)
    def _key(self, win, key, *a):
        if not self.manager or self.manager.current != "gallery": return
        if key == 275:   self._step(1)
        elif key == 276: self._step(-1)
        elif key == 127: self._delete()
        elif key == 32:  self._open_player()

    # ── sources ───────────────────────────────────────────────────────────
    def _add_source(self, *a):
        chooser = FileChooserIconView(path=_home(), dirselect=True)
        btn = Button(text="Add this folder", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser); layout.add_widget(btn)
        popup = Popup(title="Add source folder", content=layout,
                      size_hint=(0.92, 0.92))
        def _sel(*a):
            f = (chooser.selection[0]
                 if chooser.selection and os.path.isdir(chooser.selection[0])
                 else chooser.path)
            if f not in self._sources:
                self._sources.append(f)
                self._reload_files()
            popup.dismiss()
        btn.bind(on_release=_sel); popup.open()

    def _reload_files(self):
        self._files = []
        for src in self._sources:
            if os.path.isdir(src):
                for fn in sorted(os.listdir(src)):
                    p = os.path.join(src, fn)
                    if os.path.isfile(p) and _is_media(p):
                        self._files.append(p)
        self._index = 0
        self._src_lbl.text = (f"{len(self._sources)} src, "
                              f"{len(self._files)} files")
        self._show_current()

    # ── destinations ──────────────────────────────────────────────────────
    def _add_dest_pick(self, *a):
        label = self._dest_in.text.strip()  # may be empty — fill from folder name
        chooser = FileChooserIconView(path=_home(), dirselect=True)
        btn = Button(text="Select", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser); layout.add_widget(btn)
        popup = Popup(title="Destination folder", content=layout,
                      size_hint=(0.92, 0.92))
        def _sel(*a):
            f = (chooser.selection[0]
                 if chooser.selection and os.path.isdir(chooser.selection[0])
                 else chooser.path)
            # Use typed label, or fall back to actual folder name
            lbl = label if label else os.path.basename(f.rstrip("/\\")) or f
            self._dest_tree.append({"label": lbl, "path": f,
                                    "subs": self._read_subs(f)})
            self._dest_in.text = ""
            self._refresh_dests()
            popup.dismiss()
        btn.bind(on_release=_sel); popup.open()

    def _add_dest_create(self, *a):
        label = self._dest_in.text.strip()
        if not label:
            self._popup("Error", "Enter a label first."); return
        base = self._sources[0] if self._sources else _home()
        f = os.path.join(base, label)
        try:
            os.makedirs(f, exist_ok=True)
            self._dest_tree.append({"label": label, "path": f,
                                    "subs": self._read_subs(f)})
            self._dest_in.text = ""
            self._refresh_dests()
        except Exception as e:
            self._popup("Error", str(e))

    def _read_subs(self, folder):
        subs = []
        try:
            for name in sorted(os.listdir(folder)):
                p = os.path.join(folder, name)
                if os.path.isdir(p):
                    subs.append({"label": name, "path": p})
        except Exception: pass
        return subs

    def _add_subfolder_ui(self, dest_idx):
        parent = self._dest_tree[dest_idx]
        nin = TextInput(hint_text="Subfolder name", multiline=False,
                        font_size=13, size_hint_y=None, height=dp(38))
        btn = Button(text="Create", size_hint_y=None, height=dp(42))
        layout = BoxLayout(orientation="vertical", padding=8, spacing=5)
        layout.add_widget(Label(text=f"In: {parent['label']}",
                                size_hint_y=None, height=dp(24)))
        layout.add_widget(nin); layout.add_widget(btn)
        popup = Popup(title="Add subfolder", content=layout,
                      size_hint=(0.62, 0.38))
        def _do(*a):
            name = nin.text.strip()
            if name:
                p = os.path.join(parent["path"], name)
                os.makedirs(p, exist_ok=True)
                parent["subs"].append({"label": name, "path": p})
                self._refresh_dests()
            popup.dismiss()
        btn.bind(on_release=_do); popup.open()

    def _refresh_dests(self):
        self._dest_grid.clear_widgets()
        for i, d in enumerate(self._dest_tree):
            row = BoxLayout(size_hint_y=None, height=dp(24), spacing=3)
            row.add_widget(Label(text=f"[b]{d['label']}[/b]", markup=True,
                                 font_size=11, halign="left"))
            asb = Button(text="+sub", size_hint_x=None, width=dp(40),
                         font_size=9)
            asb.bind(on_release=lambda inst, idx=i: self._add_subfolder_ui(idx))
            rm = Button(text="x", size_hint_x=None, width=dp(20), font_size=10)
            rm.bind(on_release=lambda inst, idx=i: (
                self._dest_tree.pop(idx), self._refresh_dests()))
            row.add_widget(asb); row.add_widget(rm)
            self._dest_grid.add_widget(row)
            for sub in d.get("subs", []):
                sr = BoxLayout(size_hint_y=None, height=dp(20), spacing=3)
                sr.add_widget(Label(text="   ", size_hint_x=None, width=dp(10)))
                sr.add_widget(Label(text=sub["label"], font_size=10,
                                    halign="left"))
                srm = Button(text="x", size_hint_x=None, width=dp(18),
                             font_size=9)
                srm.bind(on_release=lambda inst, dd=d, ss=sub: (
                    dd["subs"].remove(ss), self._refresh_dests()))
                sr.add_widget(srm)
                self._dest_grid.add_widget(sr)
        self._refresh_sort_buttons()

    def _refresh_sort_buttons(self):
        self._sort_row.clear_widgets()
        total = sum(1 + len(d.get("subs", [])) for d in self._dest_tree)
        self._sort_row.cols = max(1, total)
        for d in self._dest_tree:
            b = Button(text=d["label"], size_hint_x=None, width=dp(108),
                       height=dp(40), font_size=12,
                       background_color=(0.25, 0.45, 0.65, 1))
            b.bind(on_release=lambda inst, p=d["path"]: self._sort_to(p))
            self._sort_row.add_widget(b)
            for sub in d.get("subs", []):
                sb = Button(text=f"  {sub['label']}", size_hint_x=None,
                            width=dp(108), height=dp(40), font_size=11,
                            background_color=(0.18, 0.35, 0.52, 1))
                sb.bind(on_release=lambda inst, p=sub["path"]: self._sort_to(p))
                self._sort_row.add_widget(sb)

    # ── sorting ───────────────────────────────────────────────────────────
    def _sort_to(self, dest):
        if not self._files or self._index >= len(self._files): return
        src = self._files[self._index]
        if self._instant:
            result = self._do_move(src, dest)
            if result:
                self._undo_stack.append(("move", src, dest, result))
            self._files.pop(self._index)
            if self._index >= len(self._files):
                self._index = max(0, len(self._files) - 1)
            self._show_current()
            self._status.text = f"Moved to {os.path.basename(dest)}"
        else:
            self._queue.append((src, dest))
            self._commit_btn.text = f"Commit ({len(self._queue)})"
            self._commit_btn.disabled = False
            self._step(1)

    def _do_move(self, src, dst_folder):
        try:
            os.makedirs(dst_folder, exist_ok=True)
            dst = os.path.join(dst_folder, os.path.basename(src))
            if os.path.exists(dst):
                base, ext = os.path.splitext(os.path.basename(src))
                dst = os.path.join(dst_folder,
                                   f"{base}_{int(time.time())}{ext}")
            shutil.move(src, dst)
            return dst
        except Exception as e:
            self._status.text = f"Move error: {e}"
            return None

    def _undo(self, *a):
        if not self._undo_stack:
            self._status.text = "Nothing to undo."; return
        action, src, dst_folder, moved_to = self._undo_stack.pop()
        try:
            shutil.move(moved_to, os.path.dirname(src))
            self._files.insert(self._index, src)
            self._show_current()
            self._status.text = f"Undone: {os.path.basename(src)}"
        except Exception as e:
            self._status.text = f"Undo error: {e}"

    def _commit(self, *a):
        moved = 0
        for src, dst in self._queue:
            if os.path.exists(src):
                r = self._do_move(src, dst)
                if r:
                    self._undo_stack.append(("move", src, dst, r))
                    moved += 1
        self._queue.clear()
        self._commit_btn.text = "Commit (0)"
        self._commit_btn.disabled = True
        self._reload_files()
        self._status.text = f"Committed {moved} moves."

    def _rename(self, *a):
        if not self._files or self._index >= len(self._files): return
        new = self._ren_in.text.strip()
        if not new: return
        old = self._files[self._index]
        ext = os.path.splitext(old)[1]
        new_path = os.path.join(os.path.dirname(old), new + ext)
        try:
            os.rename(old, new_path)
            self._files[self._index] = new_path
            self._ren_in.text = ""
            self._show_current()
        except Exception as e:
            self._popup("Rename error", str(e))

    # ── video / player ────────────────────────────────────────────────────
    def _open_player(self, *a):
        if not self._files or self._index >= len(self._files): return
        path = self._files[self._index]
        if _is_video(path):
            VideoPlayerPopup(path).open()
        else:
            # Full-screen image
            layout = BoxLayout(orientation="vertical")
            img = KivyImage(source=path, allow_stretch=True, keep_ratio=True)
            layout.add_widget(img)
            cls = Button(text="Close", size_hint_y=None, height=dp(40))
            layout.add_widget(cls)
            popup = Popup(title=os.path.basename(path), content=layout,
                          size_hint=(0.96, 0.96))
            cls.bind(on_release=popup.dismiss)
            popup.open()

    def _open_strip(self, *a):
        if not self._files or self._index >= len(self._files): return
        path = self._files[self._index]
        if _is_video(path):
            FrameStripPopup(path, n=10).open()

    # ── preview ───────────────────────────────────────────────────────────
    def _show_current(self):
        if not self._files:
            self._preview_img.source  = ""
            self._file_lbl.text       = "No files"
            self._prog.text           = "0/0"
            self._info_lbl.text       = ""
            self._play_btn.opacity    = 0
            self._strip_btn.opacity   = 0
            return
        path = self._files[self._index]
        self._file_lbl.text = os.path.basename(path)
        self._prog.text     = f"{self._index+1}/{len(self._files)}"
        self._ren_in.text   = ""

        vid = _is_video(path)
        self._play_btn.opacity  = 1 if vid else 0
        self._strip_btn.opacity = 1 if (vid and HAS_CV2) else 0

        # file info in background
        def _get_info(p):
            try:
                size_str = _fmt_size(os.path.getsize(p))
                ext      = os.path.splitext(p)[1].upper().lstrip(".")
                if vid:
                    dur, w, h = _video_info(p)
                    info = f"{ext}  |  {size_str}  |  {w}x{h}  |  {dur}"
                else:
                    if HAS_PIL:
                        img = PILImage.open(p)
                        w, h = img.size
                        info = f"{ext}  |  {size_str}  |  {w}x{h}"
                    else:
                        info = f"{ext}  |  {size_str}"
            except Exception:
                info = os.path.splitext(p)[1].upper().lstrip(".")
            def _apply(dt):
                self._info_lbl.text = info
            Clock.schedule_once(_apply, 0)

        threading.Thread(target=_get_info, args=(path,), daemon=True).start()

        # thumbnail
        if vid and not HAS_CV2:
            self._preview_img.source = ""
            self._status.text = "Video: install opencv-python for thumbnails"
        else:
            def _load(p):
                thumb = _make_thumb(p)
                def _apply(dt):
                    if not self._files: return
                    if thumb and os.path.exists(thumb):
                        self._preview_img.source = ""
                        self._preview_img.source = thumb
                        self._preview_img.reload()
                    else:
                        self._preview_img.source = ""
                Clock.schedule_once(_apply, 0)
            threading.Thread(target=_load, args=(path,), daemon=True).start()

    # ── nav ───────────────────────────────────────────────────────────────
    def _step(self, delta):
        if not self._files: return
        self._index = (self._index + delta) % len(self._files)
        self._show_current()

    def _delete(self, *a):
        if not self._files or self._index >= len(self._files): return
        src = self._files[self._index]
        layout = BoxLayout(orientation="vertical", padding=8, spacing=5)
        layout.add_widget(Label(
            text=f"Delete permanently?\n{os.path.basename(src)}",
            halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=5)
        yes = Button(text="Yes, delete",
                     background_color=(0.8, 0.15, 0.15, 1))
        no  = Button(text="Cancel")
        row.add_widget(yes); row.add_widget(no)
        layout.add_widget(row)
        popup = Popup(title="Confirm", content=layout, size_hint=(0.6, 0.34))
        def _do(*a):
            popup.dismiss()
            try:
                os.remove(src)
                self._files.pop(self._index)
                if self._index >= len(self._files):
                    self._index = max(0, len(self._files) - 1)
                self._show_current()
            except Exception as e:
                self._status.text = f"Delete error: {e}"
        yes.bind(on_release=_do)
        no.bind(on_release=lambda *a: popup.dismiss())
        popup.open()

    # ── config ────────────────────────────────────────────────────────────
    def _save_config(self, *a):
        cfg_dir = app_data.subdir("gallery_configs")
        nin = TextInput(text="my_sort", multiline=False, font_size=13,
                        size_hint_y=None, height=dp(38))
        btn = Button(text="Save", size_hint_y=None, height=dp(42))
        layout = BoxLayout(orientation="vertical", padding=8, spacing=5)
        layout.add_widget(Label(text="Config name:",
                                size_hint_y=None, height=dp(24)))
        layout.add_widget(nin); layout.add_widget(btn)
        popup = Popup(title="Save config", content=layout,
                      size_hint=(0.58, 0.36))
        def _do(*a):
            name = nin.text.strip() or "config"
            path = os.path.join(cfg_dir, f"{name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"sources": self._sources,
                           "dest_tree": self._dest_tree}, f, indent=2)
            self._status.text = f"Saved: {name}"
            popup.dismiss()
        btn.bind(on_release=_do); popup.open()

    def _load_config(self, *a):
        cfg_dir = app_data.subdir("gallery_configs")
        cfgs = [f[:-5] for f in os.listdir(cfg_dir) if f.endswith(".json")]
        if not cfgs:
            self._popup("No configs", "No saved configs."); return
        layout = BoxLayout(orientation="vertical", padding=5, spacing=4)
        sv = ScrollView()
        grid = GridLayout(cols=1, spacing=3, size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))
        popup = Popup(title="Load config", content=layout,
                      size_hint=(0.62, 0.58))
        for name in cfgs:
            b = Button(text=name, size_hint_y=None, height=dp(36),
                       font_size=12)
            b.bind(on_release=lambda inst, n=name: (
                self._apply_config(n), popup.dismiss()))
            grid.add_widget(b)
        sv.add_widget(grid); layout.add_widget(sv)
        cancel = Button(text="Cancel", size_hint_y=None, height=dp(36))
        cancel.bind(on_release=lambda *a: popup.dismiss())
        layout.add_widget(cancel)
        popup.open()

    def _apply_config(self, name):
        cfg_dir = app_data.subdir("gallery_configs")
        try:
            with open(os.path.join(cfg_dir, f"{name}.json"),
                      encoding="utf-8") as f:
                data = json.load(f)
            self._sources   = data.get("sources",   [])
            self._dest_tree = data.get("dest_tree", [])
            self._refresh_dests()
            self._reload_files()
            self._status.text = f"Loaded: {name}"
        except Exception as e:
            self._popup("Error", str(e))

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=str(msg)),
              size_hint=(0.62, 0.32)).open()
