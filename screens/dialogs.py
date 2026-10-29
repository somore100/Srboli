# screens/dialogs.py - small popups shared by several screens.

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup


def confirm_popup(title, message, on_yes, yes_text="Delete"):
    """Small yes / cancel dialog; on_yes() runs only after the yes button."""
    box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
    box.add_widget(Label(text=message))
    row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
    yes, no = Button(text=yes_text), Button(text="Cancel")
    row.add_widget(yes)
    row.add_widget(no)
    box.add_widget(row)
    pop = Popup(title=title, content=box, size_hint=(0.8, 0.34))
    yes.bind(on_release=lambda *a: (pop.dismiss(), on_yes()))
    no.bind(on_release=lambda *a: pop.dismiss())
    pop.open()


def message_popup(title, message, size_hint=(0.8, 0.4)):
    """A message with the text wrapped to the popup width."""
    lbl = Label(text=str(message), halign="left", valign="middle")
    lbl.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(8), None)))
    Popup(title=title, content=lbl, size_hint=size_hint).open()
