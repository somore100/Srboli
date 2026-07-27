# screens/image_text.py
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.core.clipboard import Clipboard
from kivy.uix.popup import Popup
from kivy.metrics import dp
import base64
from PIL import Image
import io
import os
from tkinter import filedialog as tkfiledialog
import tkinter as tk

class ImageTextScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        root = BoxLayout(orientation="vertical", padding=10, spacing=10)
        
        # Tabbed Panel
        self.tab_panel = TabbedPanel(do_default_tab=False, tab_height=dp(48))
        
        # Tab 1: Image → Text
        self.img_to_text_tab = TabbedPanelItem(text="📷 Image → Text")
        self.setup_image_to_text_tab()
        self.tab_panel.add_widget(self.img_to_text_tab)
        
        # Tab 2: Text → Image
        self.text_to_img_tab = TabbedPanelItem(text="📝 Text → Image")
        self.setup_text_to_image_tab()
        self.tab_panel.add_widget(self.text_to_img_tab)
        
        root.add_widget(self.tab_panel)
        
        # Back button
        back_btn = Button(
            text="← Back",
            size_hint_y=None,
            height=dp(48),
            background_color=(0.2, 0.4, 0.7, 1),
            color=(1, 1, 1, 1)
        )
        back_btn.bind(on_release=self.go_back)
        root.add_widget(back_btn)
        
        self.add_widget(root)
        
        self.reconstructed_image = None
        self.reconstructed_path = None
    
    def setup_image_to_text_tab(self):
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        
        # Title
        title = Label(
            text="[b]Convert Image to Text String[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(40),
            font_size=18,
            color=(0.8, 0.9, 1, 1)
        )
        layout.add_widget(title)
        
        # Image preview
        self.img_preview = KivyImage(size_hint_y=0.3)
        layout.add_widget(self.img_preview)
        
        # Select button
        select_btn = Button(
            text="📁 Select Image",
            size_hint_y=None,
            height=dp(50),
            font_size=16,
            background_color=(0.3, 0.6, 0.3, 1)
        )
        select_btn.bind(on_release=self.select_image)
        layout.add_widget(select_btn)
        
        # Text output
        output_label = Label(
            text="[b]Base64 String Output:[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(30),
            font_size=14
        )
        layout.add_widget(output_label)
        
        self.img_text_output = TextInput(
            multiline=True,
            readonly=True,
            size_hint_y=0.35,
            background_color=(0.15, 0.15, 0.15, 1),
            foreground_color=(1, 1, 1, 1)
        )
        layout.add_widget(self.img_text_output)
        
        # Copy button
        copy_btn = Button(
            text="📋 Copy to Clipboard",
            size_hint_y=None,
            height=dp(48),
            font_size=14,
            background_color=(0.2, 0.5, 0.8, 1)
        )
        copy_btn.bind(on_release=self.copy_to_clipboard)
        layout.add_widget(copy_btn)
        
        self.img_to_text_tab.add_widget(layout)
    
    def setup_text_to_image_tab(self):
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        
        # Title
        title = Label(
            text="[b]Convert Text String to Image[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(40),
            font_size=18,
            color=(0.8, 0.9, 1, 1)
        )
        layout.add_widget(title)
        
        # Text input
        input_label = Label(
            text="[b]Paste Base64 String Here:[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(30),
            font_size=14
        )
        layout.add_widget(input_label)
        
        self.text_input_box = TextInput(
            multiline=True,
            size_hint_y=0.25,
            background_color=(0.15, 0.15, 0.15, 1),
            foreground_color=(1, 1, 1, 1)
        )
        layout.add_widget(self.text_input_box)
        
        # Convert button
        convert_btn = Button(
            text="🔄 Convert to Image",
            size_hint_y=None,
            height=dp(50),
            font_size=16,
            background_color=(0.8, 0.5, 0.2, 1)
        )
        convert_btn.bind(on_release=self.convert_to_image)
        layout.add_widget(convert_btn)
        
        # Image preview
        self.text_preview = KivyImage(size_hint_y=0.3)
        layout.add_widget(self.text_preview)
        
        # Save button
        self.save_btn = Button(
            text="💾 Save Image",
            size_hint_y=None,
            height=dp(48),
            font_size=14,
            background_color=(0.6, 0.2, 0.6, 1),
            disabled=True
        )
        self.save_btn.bind(on_release=self.save_image)
        layout.add_widget(self.save_btn)
        
        self.text_to_img_tab.add_widget(layout)
    
    def select_image(self, instance):
        try:
            root = tk.Tk()
            root.withdraw()
            path = tkfiledialog.askopenfilename(
                title="Select Image",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif")]
            )
            root.destroy()
            if path:
                self.load_and_convert_image(path)
        except Exception as e:
            self.show_popup("Error", f"Failed to select image: {e}")
    
    def load_and_convert_image(self, path):
        try:
            # Display image
            self.img_preview.source = path
            self.img_preview.reload()
            
            # Convert to base64
            with open(path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            
            self.img_text_output.text = encoded
        except Exception as e:
            self.show_popup("Error", f"Failed to convert image: {e}")
    
    def copy_to_clipboard(self, instance):
        text = self.img_text_output.text
        if text:
            Clipboard.copy(text)
        else:
            self.show_popup("Warning", "No text to copy!")
    
    def convert_to_image(self, instance):
        data = self.text_input_box.text.strip()
        if not data:
            self.show_popup("Error", "No text provided!")
            return
        
        try:
            image_bytes = base64.b64decode(data)
            self.reconstructed_image = Image.open(io.BytesIO(image_bytes))
            
            # Save temporarily to display
            temp_path = "temp_reconstructed.png"
            self.reconstructed_image.save(temp_path)
            self.reconstructed_path = temp_path
            
            # Display image
            self.text_preview.source = temp_path
            self.text_preview.reload()
            
            self.save_btn.disabled = False
        except Exception as e:
            self.show_popup("Error", f"Invalid image string: {e}")
    
    def save_image(self, instance):
        if self.reconstructed_image:
            try:
                root = tk.Tk()
                root.withdraw()
                path = tkfiledialog.asksaveasfilename(
                    title="Save Image",
                    defaultextension=".png",
                    filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")]
                )
                root.destroy()
                if path:
                    self.reconstructed_image.save(path)
                    self.show_popup("Success", f"Image saved!")
            except Exception as e:
                self.show_popup("Error", f"Failed to save image: {e}")
    
    def show_popup(self, title, message):
        popup = Popup(
            title=title,
            content=Label(text=message),
            size_hint=(0.8, 0.4)
        )
        popup.open()
    
    def go_back(self, instance):
        if self.manager:
            self.manager.current = "dashboard"
            
            # Clean up temp file
            if self.reconstructed_path and os.path.exists(self.reconstructed_path):
                try:
                    os.remove(self.reconstructed_path)
                except:
                    pass