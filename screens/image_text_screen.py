# screens/image_text_screen.py
# Replaced tkinter file dialogs with Kivy-native FileChooserIconView
# Works on Linux (Wayland/X11) and Windows.

import os
import base64
import io

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _home():
    return os.path.expanduser("~")


class ImageTextScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._reconstructed_image = None
        self._temp_path = None

        root = BoxLayout(orientation="vertical", padding=8, spacing=8)

        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(46))
        self.tabs.add_widget(self._build_img_to_text_tab())
        self.tabs.add_widget(self._build_text_to_img_tab())
        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(46))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    # ── Tab 1: Image > Base64 ────────────────────────────────────────────────
    def _build_img_to_text_tab(self):
        tab = TabbedPanelItem(text="  Image > Text")
        layout = BoxLayout(orientation="vertical", padding=8, spacing=8)

        layout.add_widget(Label(
            text="[b]Convert image to Base64 string[/b]", markup=True,
            size_hint_y=None, height=dp(32), font_size=16,
        ))

        self.img_preview = KivyImage(size_hint_y=0.30, allow_stretch=True,
                                     keep_ratio=True)
        layout.add_widget(self.img_preview)

        select_btn = Button(text="  Select Image", size_hint_y=None,
                            height=dp(48), font_size=15)
        select_btn.bind(on_release=self._pick_image)
        layout.add_widget(select_btn)

        layout.add_widget(Label(text="Base64 output:", size_hint_y=None,
                                height=dp(24), font_size=13))

        self.img_text_output = TextInput(
            multiline=True, readonly=True, size_hint_y=0.32,
            background_color=(0.12, 0.12, 0.12, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        layout.add_widget(self.img_text_output)

        copy_btn = Button(text="Copy  Copy to Clipboard", size_hint_y=None,
                          height=dp(44))
        copy_btn.bind(on_release=self._copy_to_clipboard)
        layout.add_widget(copy_btn)

        tab.add_widget(layout)
        return tab

    # ── Tab 2: Base64 > Image ────────────────────────────────────────────────
    def _build_text_to_img_tab(self):
        tab = TabbedPanelItem(text="  Text > Image")
        layout = BoxLayout(orientation="vertical", padding=8, spacing=8)

        layout.add_widget(Label(
            text="[b]Convert Base64 string to image[/b]", markup=True,
            size_hint_y=None, height=dp(32), font_size=16,
        ))

        layout.add_widget(Label(text="Paste Base64 string here:",
                                size_hint_y=None, height=dp(24), font_size=13))

        self.text_input_box = TextInput(
            multiline=True, size_hint_y=0.25,
            background_color=(0.12, 0.12, 0.12, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        layout.add_widget(self.text_input_box)

        convert_btn = Button(text="  Convert to Image", size_hint_y=None,
                             height=dp(48), font_size=15)
        convert_btn.bind(on_release=self._convert_to_image)
        layout.add_widget(convert_btn)

        self.text_preview = KivyImage(size_hint_y=0.28, allow_stretch=True,
                                      keep_ratio=True)
        layout.add_widget(self.text_preview)

        self.save_btn = Button(text="Save  Save Image", size_hint_y=None,
                               height=dp(44), disabled=True)
        self.save_btn.bind(on_release=self._pick_save_location)
        layout.add_widget(self.save_btn)

        tab.add_widget(layout)
        return tab

    # ── file chooser helpers ─────────────────────────────────────────────────
    def _pick_image(self, *a):
        chooser = FileChooserIconView(
            path=_home(),
            filters=["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp"],
            multiselect=False,
        )
        btn = Button(text="Open", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Select Image", content=layout, size_hint=(0.92, 0.92))

        def _open(inst):
            if chooser.selection:
                self._load_image(chooser.selection[0])
            popup.dismiss()

        btn.bind(on_release=_open)
        popup.open()

    def _load_image(self, path):
        if not os.path.exists(path):
            self._popup("Error", "File not found.")
            return
        try:
            self.img_preview.source = path
            self.img_preview.reload()
            with open(path, "rb") as f:
                self.img_text_output.text = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            self._popup("Error", str(e))

    def _copy_to_clipboard(self, *a):
        txt = self.img_text_output.text
        if txt:
            Clipboard.copy(txt)
        else:
            self._popup("Nothing to copy", "Convert an image first.")

    def _convert_to_image(self, *a):
        if not HAS_PIL:
            self._popup("Missing dependency", "Install Pillow:\npip install Pillow")
            return
        data = self.text_input_box.text.strip()
        if not data:
            self._popup("Error", "Paste a Base64 string first.")
            return
        try:
            img_bytes = base64.b64decode(data)
            img = PILImage.open(io.BytesIO(img_bytes))
            self._reconstructed_image = img

            # save to a temp file so Kivy can display it
            tmp = os.path.join(os.path.expanduser("~"), ".srboli_temp_preview.png")
            img.save(tmp)
            self._temp_path = tmp

            self.text_preview.source = tmp
            self.text_preview.reload()
            self.save_btn.disabled = False
        except Exception as e:
            self._popup("Error", f"Invalid image string:\n{e}")

    def _pick_save_location(self, *a):
        if self._reconstructed_image is None:
            return
        chooser = FileChooserIconView(path=_home(), multiselect=False)
        filename_input = TextInput(
            text="image.png", multiline=False,
            size_hint_y=None, height=dp(36),
        )
        save_btn = Button(text="Save here", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(Label(text="Choose folder, set filename below:",
                                size_hint_y=None, height=dp(28)))
        layout.add_widget(chooser)
        layout.add_widget(filename_input)
        layout.add_widget(save_btn)
        popup = Popup(title="Save Image", content=layout, size_hint=(0.92, 0.92))

        def _save(inst):
            folder = chooser.path
            name = filename_input.text.strip() or "image.png"
            full_path = os.path.join(folder, name)
            try:
                self._reconstructed_image.save(full_path)
                self._popup("Saved", f"Image saved to:\n{full_path}")
            except Exception as e:
                self._popup("Error", str(e))
            popup.dismiss()

        save_btn.bind(on_release=_save)
        popup.open()

    # ── utilities ────────────────────────────────────────────────────────────
    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=msg),
              size_hint=(0.75, 0.40)).open()

    def _go_back(self, *a):
        # clean up temp preview file
        if self._temp_path and os.path.exists(self._temp_path):
            try:
                os.remove(self._temp_path)
            except Exception:
                pass
        if self.manager:
            self.manager.current = "dashboard"
