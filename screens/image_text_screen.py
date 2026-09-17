# screens/image_text_screen.py
#
# Was: File -> Base64, all synchronous on the UI thread (file read +
# base64 encode), then the ENTIRE base64 string dumped straight into a
# Kivy TextInput. TextInput does expensive line-wrap/glyph-measurement
# work that doesn't scale — for anything above a few hundred KB (e.g. a
# video file) that would freeze the whole app, sometimes the whole
# system, and it got worse on Copy since Kivy's clipboard backend on
# Linux shells out to xclip/xsel with the whole string, also
# synchronously on the UI thread.
#
# Fixed:
#   - File read + base64 encode/decode always run on a background thread.
#     UI updates are marshalled back via Clock.schedule_once.
#   - Past MAX_DISPLAY_CHARS, the TextInput is never given the full
#     string — it shows a short preview instead, and "Save to .txt" /
#     "Copy to Clipboard" work from the in-memory result directly
#     (never round-tripping through the widget).
#   - Copy-to-clipboard also runs on a background thread for the same
#     reason (large strings can make even the clipboard call itself
#     noticeably slow).
#   - Generalized from images-only to any file: the picker no longer
#     restricts to image extensions, and Base64 -> File writes the exact
#     decoded bytes to whatever filename you choose — image preview is
#     attempted opportunistically, not required.

import os
import base64
import io
import threading

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
from kivy.clock import Clock
from kivy.metrics import dp

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Above this many characters, stop putting the string in a TextInput
# altogether — 300k chars is roughly 225KB of raw file data once
# base64-inflated (~4/3 ratio). Below this, a TextInput is fine.
MAX_DISPLAY_CHARS = 300_000


def _home():
    return os.path.expanduser("~")


class ImageTextScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._reconstructed_bytes = None
        self._temp_preview_path = None
        self._last_b64 = ""          # full result, kept out of the widget
        self._loaded_b64 = ""        # base64 loaded from a .txt file (tab 2)
        self._busy = False

        root = BoxLayout(orientation="vertical", padding=8, spacing=8)

        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(46))
        self.tabs.add_widget(self._build_file_to_b64_tab())
        self.tabs.add_widget(self._build_b64_to_file_tab())
        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(46))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    # ── Tab 1: File -> Base64 ────────────────────────────────────────────
    def _build_file_to_b64_tab(self):
        tab = TabbedPanelItem(text="  File > Base64")
        layout = BoxLayout(orientation="vertical", padding=8, spacing=8)

        layout.add_widget(Label(
            text="[b]Convert a file to a Base64 string[/b] (any file type)",
            markup=True, size_hint_y=None, height=dp(32), font_size=15,
        ))

        self.img_preview = KivyImage(size_hint_y=0.28, fit_mode="contain")
        layout.add_widget(self.img_preview)

        select_btn = Button(text="Select File", size_hint_y=None,
                            height=dp(48), font_size=15)
        select_btn.bind(on_release=self._pick_file)
        layout.add_widget(select_btn)

        self._encode_status = Label(text="No file selected.", size_hint_y=None,
                                    height=dp(22), font_size=12,
                                    color=(0.6, 0.6, 0.6, 1))
        layout.add_widget(self._encode_status)

        layout.add_widget(Label(text="Base64 output:", size_hint_y=None,
                                height=dp(20), font_size=12))

        self.img_text_output = TextInput(
            multiline=True, readonly=True, size_hint_y=0.30,
            background_color=(0.12, 0.12, 0.12, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        layout.add_widget(self.img_text_output)

        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        self._copy_btn = Button(text="Copy to Clipboard")
        self._copy_btn.bind(on_release=self._copy_to_clipboard)
        self._save_txt_btn = Button(text="Save output to .txt")
        self._save_txt_btn.bind(on_release=self._save_output_to_txt)
        btn_row.add_widget(self._copy_btn)
        btn_row.add_widget(self._save_txt_btn)
        layout.add_widget(btn_row)

        tab.add_widget(layout)
        return tab

    # ── Tab 2: Base64 -> File ────────────────────────────────────────────
    def _build_b64_to_file_tab(self):
        tab = TabbedPanelItem(text="  Base64 > File")
        layout = BoxLayout(orientation="vertical", padding=8, spacing=8)

        layout.add_widget(Label(
            text="[b]Convert a Base64 string back to a file[/b]", markup=True,
            size_hint_y=None, height=dp(32), font_size=15,
        ))

        layout.add_widget(Label(text="Paste Base64 string here (small/medium "
                                     "strings only — see note below):",
                                size_hint_y=None, height=dp(20), font_size=12))

        self.text_input_box = TextInput(
            multiline=True, size_hint_y=0.25,
            background_color=(0.12, 0.12, 0.12, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        self.text_input_box.bind(text=self._on_input_box_edited)
        layout.add_widget(self.text_input_box)

        load_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
        self._load_file_btn = Button(text="Load Base64 from .txt file...")
        self._load_file_btn.bind(on_release=self._pick_b64_file)
        load_row.add_widget(self._load_file_btn)
        layout.add_widget(load_row)

        note_lbl = Label(
            text="Pasting a very large string directly into the box above "
                 "can be slow (that's a text-box rendering limit, not this "
                 "app hanging) - for anything past a few hundred KB, use "
                 "\"Load from .txt file\" instead.",
            font_size=10, size_hint_y=None, height=dp(38),
            halign="left", valign="top", color=(0.55, 0.55, 0.55, 1))
        note_lbl.bind(size=note_lbl.setter("text_size"))
        layout.add_widget(note_lbl)

        self._decode_btn = Button(text="Convert to File", size_hint_y=None,
                                  height=dp(48), font_size=15)
        self._decode_btn.bind(on_release=self._convert_to_file)
        layout.add_widget(self._decode_btn)

        self._decode_status = Label(text="", size_hint_y=None, height=dp(22),
                                    font_size=12, color=(0.6, 0.6, 0.6, 1))
        layout.add_widget(self._decode_status)

        self.text_preview = KivyImage(size_hint_y=0.26, fit_mode="contain")
        layout.add_widget(self.text_preview)

        save_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=6)
        save_row.add_widget(Label(text="Save as:", size_hint_x=None,
                                  width=dp(70), font_size=12))
        self._filename_input = TextInput(text="output.bin", multiline=False,
                                         font_size=12)
        save_row.add_widget(self._filename_input)
        layout.add_widget(save_row)

        self.save_btn = Button(text="Save File", size_hint_y=None,
                               height=dp(44), disabled=True)
        self.save_btn.bind(on_release=self._pick_save_location)
        layout.add_widget(self.save_btn)

        tab.add_widget(layout)
        return tab

    # ── busy-state helper ────────────────────────────────────────────────
    def _set_busy(self, busy, status_lbl=None, msg=""):
        self._busy = busy
        for b in (self._copy_btn, self._save_txt_btn, self._decode_btn):
            b.disabled = busy
        if status_lbl and msg:
            status_lbl.text = msg

    # ── Tab 1: pick + encode ─────────────────────────────────────────────
    def _pick_file(self, *a):
        if self._busy:
            return
        chooser = FileChooserIconView(path=_home(), multiselect=False)
        btn = Button(text="Open", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Select File (any type)", content=layout,
                      size_hint=(0.92, 0.92))

        def _open(inst):
            if chooser.selection:
                self._load_file(chooser.selection[0])
            popup.dismiss()

        btn.bind(on_release=_open)
        popup.open()

    def _load_file(self, path):
        if not os.path.exists(path):
            self._popup("Error", "File not found.")
            return

        size = os.path.getsize(path)
        self.img_text_output.text = ""
        self._last_b64 = ""
        self._set_busy(True, self._encode_status,
                      f"Reading and encoding ({size/1e6:.1f} MB)... "
                      f"this can take a moment for large files.")

        # Opportunistic image preview: cheap (just points the Image widget
        # at the file), doesn't require decoding anything ourselves, and
        # silently no-ops if it's not actually an image.
        self.img_preview.source = path
        try:
            self.img_preview.reload()
        except Exception:
            pass

        def worker():
            try:
                with open(path, "rb") as f:
                    raw = f.read()
                b64 = base64.b64encode(raw).decode("ascii")
                Clock.schedule_once(lambda dt: self._on_encode_done(b64, None))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_encode_done(None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_encode_done(self, b64, error):
        self._set_busy(False)
        if error is not None:
            self._encode_status.text = "Encoding failed."
            self._popup("Error", str(error))
            return

        self._last_b64 = b64
        n = len(b64)
        if n <= MAX_DISPLAY_CHARS:
            self.img_text_output.text = b64
        else:
            preview = b64[:500]
            self.img_text_output.text = (
                f"{preview}\n\n"
                f"...[truncated - {n:,} characters total, "
                f"{n/1e6:.1f} MB as text]\n"
                f"Use \"Copy to Clipboard\" or \"Save output to .txt\" "
                f"below to get the full string - this box only shows a "
                f"preview so the app doesn't have to render the whole "
                f"thing.")
        self._encode_status.text = f"Done - {n:,} characters ({n/1e6:.1f} MB)"

    # ── Tab 1: copy / save (always from memory, never from the widget) ──
    def _copy_to_clipboard(self, *a):
        if not self._last_b64:
            self._popup("Nothing to copy", "Convert a file first.")
            return
        if self._busy:
            return
        text = self._last_b64
        self._set_busy(True, self._encode_status, "Copying to clipboard...")

        def worker():
            try:
                Clipboard.copy(text)
                Clock.schedule_once(lambda dt: self._on_copy_done(None))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_copy_done(e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_copy_done(self, error):
        self._set_busy(False)
        if error is not None:
            self._encode_status.text = "Copy failed."
            self._popup("Error", str(error))
        else:
            self._encode_status.text = (
                f"Copied {len(self._last_b64):,} characters to clipboard.")

    def _save_output_to_txt(self, *a):
        if not self._last_b64:
            self._popup("Nothing to save", "Convert a file first.")
            return
        chooser = FileChooserIconView(path=_home(), multiselect=False)
        filename_input = TextInput(text="output.txt", multiline=False,
                                   size_hint_y=None, height=dp(36))
        save_btn = Button(text="Save here", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(Label(text="Choose folder, set filename below:",
                                size_hint_y=None, height=dp(28)))
        layout.add_widget(chooser)
        layout.add_widget(filename_input)
        layout.add_widget(save_btn)
        popup = Popup(title="Save Base64 Output", content=layout,
                      size_hint=(0.92, 0.92))

        def _save(inst):
            folder = chooser.path
            name = filename_input.text.strip() or "output.txt"
            full_path = os.path.join(folder, name)
            text = self._last_b64
            self._set_busy(True, self._encode_status, "Saving...")

            def worker():
                try:
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(text)
                    Clock.schedule_once(
                        lambda dt: self._on_save_txt_done(full_path, None))
                except Exception as e:
                    Clock.schedule_once(
                        lambda dt: self._on_save_txt_done(full_path, e))

            threading.Thread(target=worker, daemon=True).start()
            popup.dismiss()

        save_btn.bind(on_release=_save)
        popup.open()

    def _on_save_txt_done(self, path, error):
        self._set_busy(False)
        if error is not None:
            self._encode_status.text = "Save failed."
            self._popup("Error", str(error))
        else:
            self._encode_status.text = f"Saved to {path}"
            self._popup("Saved", f"Output saved to:\n{path}")

    # ── Tab 2: decode ────────────────────────────────────────────────────
    def _on_input_box_edited(self, inst, value):
        # if the user starts typing/pasting manually, a previously loaded
        # file buffer is no longer what they mean to convert
        if self._loaded_b64:
            self._loaded_b64 = ""
            self._decode_status.text = ""

    def _pick_b64_file(self, *a):
        if self._busy:
            return
        chooser = FileChooserIconView(path=_home(), multiselect=False,
                                      filters=["*.txt", "*"])
        btn = Button(text="Open", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Load Base64 from file", content=layout,
                      size_hint=(0.92, 0.92))

        def _open(inst):
            if chooser.selection:
                self._load_b64_file(chooser.selection[0])
            popup.dismiss()

        btn.bind(on_release=_open)
        popup.open()

    def _load_b64_file(self, path):
        self._set_busy(True, self._decode_status, "Reading file...")

        def worker():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                Clock.schedule_once(lambda dt: self._on_b64_file_loaded(text, None))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_b64_file_loaded(None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_b64_file_loaded(self, text, error):
        self._set_busy(False)
        if error is not None:
            self._decode_status.text = "Load failed."
            self._popup("Error", str(error))
            return
        self._loaded_b64 = text
        # Deliberately NOT put into text_input_box — that's the whole
        # point (avoids the widget-reflow slowdown for large strings).
        self.text_input_box.unbind(text=self._on_input_box_edited)
        self.text_input_box.text = ""
        self.text_input_box.bind(text=self._on_input_box_edited)
        n = len(text)
        self._decode_status.text = (
            f"Loaded {n:,} characters from file "
            f"(not shown in the box above, to avoid lag). "
            f"Click \"Convert to File\" to decode it.")

    def _convert_to_file(self, *a):
        if self._busy:
            return
        data = self._loaded_b64 or self.text_input_box.text.strip()
        if not data:
            self._popup("Error", "Paste a Base64 string first, or load one "
                                 "from a .txt file.")
            return

        self.save_btn.disabled = True
        self._set_busy(True, self._decode_status, "Decoding...")

        def worker():
            try:
                raw = base64.b64decode(data)
                Clock.schedule_once(lambda dt: self._on_decode_done(raw, None))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_decode_done(None, e))

        threading.Thread(target=worker, daemon=True).start()

    def _on_decode_done(self, raw, error):
        self._set_busy(False)
        if error is not None:
            self._decode_status.text = "Decode failed."
            self._popup("Error", f"Invalid Base64 string:\n{error}")
            return

        self._reconstructed_bytes = raw
        self.save_btn.disabled = False
        n = len(raw)
        self._decode_status.text = f"Decoded {n:,} bytes ({n/1e6:.1f} MB)."

        # Only attempt an image preview if it happens to parse as one —
        # this tab now handles arbitrary decoded bytes, not just images.
        if HAS_PIL:
            try:
                img = PILImage.open(io.BytesIO(raw))
                img.load()  # force decode now, while we're already off-thread-free path
                tmp = os.path.join(_home(), ".srboli_temp_preview.png")
                img.save(tmp)
                self._temp_preview_path = tmp
                self.text_preview.source = tmp
                self.text_preview.reload()
                ext = (img.format or "png").lower()
                self._filename_input.text = f"output.{ext}"
                self._decode_status.text += "  (image preview available)"
                return
            except Exception:
                pass
        # not an image (or PIL unavailable) — clear any stale preview
        self.text_preview.source = ""
        self._filename_input.text = "output.bin"

    def _pick_save_location(self, *a):
        if self._reconstructed_bytes is None:
            return
        chooser = FileChooserIconView(path=_home(), multiselect=False)
        filename_input = TextInput(
            text=self._filename_input.text or "output.bin", multiline=False,
            size_hint_y=None, height=dp(36),
        )
        save_btn = Button(text="Save here", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(Label(text="Choose folder, set filename below:",
                                size_hint_y=None, height=dp(28)))
        layout.add_widget(chooser)
        layout.add_widget(filename_input)
        layout.add_widget(save_btn)
        popup = Popup(title="Save File", content=layout, size_hint=(0.92, 0.92))

        def _save(inst):
            folder = chooser.path
            name = filename_input.text.strip() or "output.bin"
            full_path = os.path.join(folder, name)
            raw = self._reconstructed_bytes
            self._set_busy(True, self._decode_status, "Saving...")

            def worker():
                try:
                    with open(full_path, "wb") as f:
                        f.write(raw)
                    Clock.schedule_once(
                        lambda dt: self._on_save_file_done(full_path, None))
                except Exception as e:
                    Clock.schedule_once(
                        lambda dt: self._on_save_file_done(full_path, e))

            threading.Thread(target=worker, daemon=True).start()
            popup.dismiss()

        save_btn.bind(on_release=_save)
        popup.open()

    def _on_save_file_done(self, path, error):
        self._set_busy(False)
        if error is not None:
            self._decode_status.text = "Save failed."
            self._popup("Error", str(error))
        else:
            self._decode_status.text = f"Saved to {path}"
            self._popup("Saved", f"File saved to:\n{path}")

    # ── utilities ────────────────────────────────────────────────────────
    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=msg),
              size_hint=(0.75, 0.40)).open()

    def _go_back(self, *a):
        if self._temp_preview_path and os.path.exists(self._temp_preview_path):
            try:
                os.remove(self._temp_preview_path)
            except Exception:
                pass
        if self.manager:
            self.manager.current = "dashboard"
