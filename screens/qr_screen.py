# screens/qr_screen.py - QR Code: make one from text, a link or Wi-Fi login, save it
# as a picture, or read one from a picture (computer builds, needs OpenCV).
# Logic: core/qr_core.py (own encoder, no extra library).
import os
import time

from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivy.core.clipboard import Clipboard

import app_data
from core import qr_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)
BORDER = 4


class QRView(Widget):
    """Draws the matrix, black on white, as sharp squares."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.matrix = None
        self.bind(pos=self.redraw, size=self.redraw)

    def set_matrix(self, matrix):
        self.matrix = matrix
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        with self.canvas:
            Color(1, 1, 1, 1)
            side = min(self.width, self.height)
            x = self.x + (self.width - side) / 2
            y = self.y + (self.height - side) / 2
            Rectangle(pos=(x, y), size=(side, side))
            if not self.matrix:
                return
            n = len(self.matrix) + 2 * BORDER
            tex = Texture.create(size=(n, n), colorfmt="luminance")
            tex.mag_filter = "nearest"
            tex.min_filter = "nearest"
            tex.blit_buffer(bytes(self._topdown(n)), colorfmt="luminance",
                            bufferfmt="ubyte")
            tex.flip_vertical()                 # rows were written top-down
            Color(1, 1, 1, 1)
            Rectangle(texture=tex, pos=(x, y), size=(side, side))

    def _topdown(self, n):
        size = len(self.matrix)
        out = bytearray()
        for r in range(n):
            for c in range(n):
                rr, cc = r - BORDER, c - BORDER
                dark = 0 <= rr < size and 0 <= cc < size and self.matrix[rr][cc]
                out.append(0 if dark else 255)
        return out


class QRScreen(ToolScreen):
    title = "QR Code"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mode = "text"
        self.level = "M"
        self.matrix = None
        self.text = ""

        tabs = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        self.tab_btns = {}
        for key, label in (("text", "Text / link"), ("wifi", "Wi-Fi")):
            b = Button(text=label, font_size=sp(12))
            b.bind(on_release=lambda *a, k=key: self.set_mode(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        self.level_btn = Button(text="", font_size=sp(12), size_hint_x=None, width=dp(130))
        self.level_btn.bind(on_release=lambda *a: self.toggle_level())
        tabs.add_widget(self.level_btn)
        self.body.add_widget(tabs)

        self.input = TextInput(hint_text="Text or link to turn into a QR code",
                               size_hint_y=None, height=dp(90), font_size=sp(14))
        self.input.bind(text=lambda *a: self.update())
        self.body.add_widget(self.input)

        self.wifi = BoxLayout(orientation="vertical", size_hint_y=None, height=0,
                              spacing=dp(4), opacity=0)
        self.ssid = TextInput(hint_text="Network name", multiline=False,
                              size_hint_y=None, height=dp(38), font_size=sp(14))
        self.pw = TextInput(hint_text="Password (empty = open network)", multiline=False,
                            size_hint_y=None, height=dp(38), font_size=sp(14))
        for w in (self.ssid, self.pw):
            w.bind(text=lambda *a: self.update())
            self.wifi.add_widget(w)
        self.body.add_widget(self.wifi)

        self.view = QRView()
        self.body.add_widget(self.view)
        self.status = Label(text="", font_size=sp(12), color=theme.MUTED, size_hint_y=None,
                            height=dp(34), halign="center", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.status)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.save_btn = Button(text="Save PNG", font_size=sp(13))
        self.save_btn.bind(on_release=lambda *a: self.save())
        self.read_btn = Button(text="Read from picture", font_size=sp(13))
        self.read_btn.bind(on_release=lambda *a: self.pick_image())
        row.add_widget(self.save_btn)
        row.add_widget(self.read_btn)
        self.body.add_widget(row)
        self.set_mode("text")

    # ----- making -----
    def set_mode(self, mode):
        self.mode = mode
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == mode else OFF
        wifi = mode == "wifi"
        self.input.height = 0 if wifi else dp(90)
        self.input.opacity = 0 if wifi else 1
        self.input.disabled = wifi
        self.wifi.height = dp(80) if wifi else 0
        self.wifi.opacity = 1 if wifi else 0
        self._sync_level()
        self.update()

    def toggle_level(self):
        self.level = "L" if self.level == "M" else "M"
        self._sync_level()
        self.update()

    def _sync_level(self):
        self.level_btn.text = ("Strong repair (M)" if self.level == "M"
                               else "More text (L)")

    def current_text(self):
        if self.mode == "wifi":
            if not self.ssid.text.strip():
                return ""
            return core.wifi_text(self.ssid.text, self.pw.text)
        return self.input.text

    def update(self):
        self.text = self.current_text()
        self.matrix = None
        if not self.text.strip():
            self.status.text = "Type something to make a code."
            self.view.set_matrix(None)
            return
        try:
            self.matrix = core.make(self.text, self.level)
            n = len(self.text.encode("utf-8"))
            self.status.text = (f"{n} bytes. Scan it with a phone camera. "
                                f"Room for {core.capacity(self.level)}.")
            self.status.color = theme.MUTED
        except core.QRTooLong as e:
            self.status.text = str(e)
            self.status.color = theme.DANGER
        self.view.set_matrix(self.matrix)

    def save(self):
        if not self.matrix:
            self.status.text = "Nothing to save yet."
            return
        try:
            path = os.path.join(app_data.subdir("qr"),
                                time.strftime("qr-%Y%m%d-%H%M%S.png"))
            core.to_png(self.matrix, path)
            self.status.text = f"Saved: {path}"
            self.status.color = theme.SUCCESS
        except Exception as e:
            self.status.text = f"Could not save: {e}"
            self.status.color = theme.DANGER

    # ----- reading -----
    def pick_image(self):
        if not core.can_scan():
            self.status.text = core.scan_image("")[1]
            self.status.color = theme.DANGER
            return
        start = os.path.expanduser("~")
        pics = os.path.join(start, "Pictures")
        chooser = FileChooserIconView(path=pics if os.path.isdir(pics) else start,
                                      filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.webp"])
        use = Button(text="Read this picture", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Choose a picture with a QR code", content=lay,
                    size_hint=(0.92, 0.92))

        def _use(*a):
            if chooser.selection:
                pop.dismiss()
                self.read_path(chooser.selection[0])

        use.bind(on_release=_use)
        pop.open()

    def read_path(self, path):
        text, err = core.scan_image(path)
        if text is None:
            self.status.text = err
            self.status.color = theme.DANGER
            return
        self.mode_text(text)

    def mode_text(self, text):
        """Show a scanned text: in the box, ready to copy."""
        self.set_mode("text")
        self.input.text = text
        try:
            Clipboard.copy(text)
            self.status.text = "Read it. The text is in the box and copied."
        except Exception:
            self.status.text = "Read it. The text is in the box."
        self.status.color = theme.SUCCESS
