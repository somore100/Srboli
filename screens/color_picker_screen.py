# screens/color_picker_screen.py - Colour Picker: pick a colour from anywhere on the
# screen (computer, X11/Windows/macOS) or from a picture (everywhere), tune it with
# sliders or a hex code, copy it as HEX / RGB / HSL and keep a palette.
# Logic: core/color_core.py.
import os

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image as KImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform as _platform

from core import color_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)


class Swatch(Widget):
    def __init__(self, rgb=(255, 255, 255), **kw):
        super().__init__(**kw)
        self.rgb = rgb
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def set_rgb(self, rgb):
        self.rgb = rgb
        self._draw()

    def _draw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(*(v / 255 for v in self.rgb), 1)
            Rectangle(pos=self.pos, size=self.size)


class PickerImage(KImage):
    """The captured screen / picture; reports the pixel under a touch."""

    def __init__(self, pil, on_pick, **kw):
        super().__init__(**kw)
        self.pil = pil
        self.on_pick = on_pick
        tex = Texture.create(size=pil.size, colorfmt="rgb")
        tex.blit_buffer(pil.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
        tex.flip_vertical()
        self.texture = tex
        self.fit_mode = "contain"

    def _pixel_at(self, touch):
        nw, nh = self.norm_image_size
        if not nw or not nh:
            return None
        ox = self.x + (self.width - nw) / 2
        oy = self.y + (self.height - nh) / 2
        fx, fy = (touch.x - ox) / nw, (touch.y - oy) / nh
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        return core.pixel(self.pil, fx * self.pil.width, (1 - fy) * self.pil.height)

    def _handle(self, touch):
        if self.collide_point(*touch.pos):
            rgb = self._pixel_at(touch)
            if rgb:
                self.on_pick(rgb)
                return True
        return False

    def on_touch_down(self, touch):
        if self._handle(touch):
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._handle(touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)


class ColorPickerScreen(ToolScreen):
    title = "Colour Picker"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.rgb = (70, 130, 220)
        self.palette = core.load_palette()
        self._busy = False

        self.swatch = Swatch(self.rgb, size_hint_y=None, height=dp(90))
        self.swatch_label = Label(text="", font_size=sp(22), bold=True)
        top = BoxLayout(size_hint_y=None, height=dp(90))
        top.add_widget(self._overlay(self.swatch, self.swatch_label))
        self.body.add_widget(top)

        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.screen_btn = Button(text="Pick from screen", font_size=sp(12))
        self.screen_btn.bind(on_release=lambda *a: self.pick_from_screen())
        pic = Button(text="Pick from picture", font_size=sp(12))
        pic.bind(on_release=lambda *a: self.pick_from_file())
        save = Button(text="Save to palette", font_size=sp(12))
        save.bind(on_release=lambda *a: self.save_color())
        for b in (self.screen_btn, pic, save):
            row.add_widget(b)
        self.body.add_widget(row)
        if _platform == "android":
            self.screen_btn.disabled = True
            self.screen_btn.text = "Screen: computer only"

        self.hex_in = TextInput(multiline=False, size_hint_y=None, height=dp(40),
                                font_size=sp(15), hint_text="#RRGGBB, rgb(1,2,3) ...")
        self.hex_in.bind(on_text_validate=lambda *a: self._from_text())
        self.hex_in.bind(focus=lambda w, f: None if f else self._from_text())
        self.body.add_widget(self.hex_in)

        self.sliders = []
        for name in "RGB":
            r = BoxLayout(size_hint_y=None, height=dp(34))
            r.add_widget(Label(text=name, size_hint_x=None, width=dp(24)))
            s = Slider(min=0, max=255, step=1)
            s.bind(value=lambda *a: self._from_sliders())
            r.add_widget(s)
            self.sliders.append(s)
            self.body.add_widget(r)

        self.fmt_labels = {}
        for key in ("HEX", "RGB", "HSL"):
            r = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
            lbl = Label(text="", font_size=sp(14), halign="left", valign="middle")
            lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
            cp = Button(text=f"Copy {key}", size_hint_x=None, width=dp(100), font_size=sp(12))
            cp.bind(on_release=lambda *a, k=key: self.copy(k))
            r.add_widget(lbl)
            r.add_widget(cp)
            self.fmt_labels[key] = lbl
            self.body.add_widget(r)

        self.contrast_label = Label(text="", font_size=sp(11), color=theme.MUTED,
                                    size_hint_y=None, height=dp(22))
        self.body.add_widget(self.contrast_label)
        self.status = Label(text="", font_size=sp(11), color=theme.MUTED, size_hint_y=None,
                            height=dp(34), halign="center", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.status)

        head = BoxLayout(size_hint_y=None, height=dp(28))
        head.add_widget(Label(text="Palette (tap to use)", font_size=sp(12),
                              halign="left", color=theme.MUTED))
        clr = Button(text="Clear", size_hint_x=None, width=dp(70), font_size=sp(11))
        clr.bind(on_release=lambda *a: self.clear_palette())
        head.add_widget(clr)
        self.body.add_widget(head)
        self.grid = GridLayout(cols=8, spacing=dp(4), size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.body.add_widget(self.grid)
        self.body.add_widget(Widget())
        self.set_rgb(self.rgb)
        self._draw_palette()

    @staticmethod
    def _overlay(bottom, top):
        from kivy.uix.floatlayout import FloatLayout
        fl = FloatLayout()
        bottom.size_hint = (1, 1)
        fl.add_widget(bottom)
        top.size_hint = (1, 1)
        fl.add_widget(top)
        return fl

    # ----- colour state -----
    def set_rgb(self, rgb, source=None):
        self.rgb = tuple(int(v) for v in rgb)
        self._busy = True
        try:
            self.swatch.set_rgb(self.rgb)
            fg = core.readable_on(self.rgb)
            self.swatch_label.color = (*(v / 255 for v in fg), 1)
            self.swatch_label.text = core.to_hex(self.rgb)
            if source != "text":
                self.hex_in.text = core.to_hex(self.rgb)
            if source != "sliders":
                for s, v in zip(self.sliders, self.rgb):
                    s.value = v
            f = core.formats(self.rgb)
            for k, lbl in self.fmt_labels.items():
                lbl.text = f"{k}   {f[k]}"
            w = core.contrast(self.rgb, (255, 255, 255))
            k = core.contrast(self.rgb, (0, 0, 0))
            self.contrast_label.text = f"Contrast: {w:.1f}:1 with white, {k:.1f}:1 with black"
        finally:
            self._busy = False

    def _from_sliders(self):
        if not self._busy:
            self.set_rgb([s.value for s in self.sliders], "sliders")

    def _from_text(self):
        if self._busy:
            return
        c = core.parse_color(self.hex_in.text)
        if c:
            self.set_rgb(c, "text")
        elif self.hex_in.text.strip():
            self.status.text = "Not a colour. Try #RRGGBB or rgb(1, 2, 3)."

    def copy(self, key):
        text = core.formats(self.rgb)[key]
        try:
            Clipboard.copy(text)
            self.status.text = f"Copied {text}"
        except Exception as e:
            self.status.text = f"Could not copy: {e}"

    # ----- palette -----
    def save_color(self):
        self.palette = core.add_to_palette(self.palette, self.rgb)
        core.save_palette(self.palette)
        self._draw_palette()
        self.status.text = "Saved to the palette."

    def clear_palette(self):
        self.palette = []
        core.save_palette(self.palette)
        self._draw_palette()

    def _draw_palette(self):
        self.grid.clear_widgets()
        for h in self.palette:
            rgb = core.parse_color(h)
            b = Button(text="", size_hint_y=None, height=dp(34), background_normal="",
                       background_color=(*(v / 255 for v in rgb), 1))
            b.bind(on_release=lambda *a, c=rgb: self.set_rgb(c))
            self.grid.add_widget(b)

    # ----- picking -----
    def pick_from_screen(self):
        self.status.text = "Hiding Srboli for a moment to capture the screen..."
        try:
            Window.minimize()
        except Exception:
            pass
        Clock.schedule_once(self._grab, 0.8)

    def _grab(self, dt):
        img, err = core.grab_screen()
        try:
            Window.restore()
            Window.raise_window()
        except Exception:
            pass
        if img is None:
            self.status.text = err
            return
        self.pick_from_image(img)

    def pick_from_file(self):
        start = os.path.expanduser("~")
        try:
            from core.android_storage import shared_storage_root
            start = shared_storage_root() or start
        except Exception:
            pass
        pics = os.path.join(start, "Pictures")
        chooser = FileChooserIconView(path=pics if os.path.isdir(pics) else start,
                                      filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"])
        use = Button(text="Open this picture", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Choose a picture", content=lay, size_hint=(0.92, 0.92))

        def _use(*a):
            if chooser.selection:
                pop.dismiss()
                self.open_path(chooser.selection[0])

        use.bind(on_release=_use)
        pop.open()

    def open_path(self, path):
        img, err = core.open_picture(path)
        if img is None:
            self.status.text = err
            return
        self.pick_from_image(img)

    def pick_from_image(self, pil):
        """Full-window picker: drag over the picture, then 'Use this colour'."""
        chosen = {"rgb": self.rgb}
        preview = Swatch(self.rgb, size_hint_x=None, width=dp(60))
        label = Label(text=core.to_hex(self.rgb), font_size=sp(16))
        use = Button(text="Use this colour", size_hint_x=None, width=dp(150))
        cancel = Button(text="Cancel", size_hint_x=None, width=dp(90))

        def moved(rgb):
            chosen["rgb"] = rgb
            preview.set_rgb(rgb)
            label.text = core.to_hex(rgb)

        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        for w in (preview, label, use, cancel):
            bar.add_widget(w)
        lay = BoxLayout(orientation="vertical", spacing=dp(4))
        lay.add_widget(bar)
        lay.add_widget(PickerImage(pil, moved))
        pop = Popup(title="Touch or drag over the picture", content=lay, size_hint=(0.98, 0.98))
        use.bind(on_release=lambda *a: (pop.dismiss(), self.set_rgb(chosen["rgb"])))
        cancel.bind(on_release=lambda *a: pop.dismiss())
        pop.open()
