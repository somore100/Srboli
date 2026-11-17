# screens/ai_ui.py - small pieces every AI button shares.
#   ai_button_state(btn, tool)   show the button only while the AI is allowed
#   ask(title, hint, on_submit)  a popup with a text box
#   work(fn, done)               run fn off the UI thread; done(result, error)

import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput

from core import ai_core


def is_on(tool):
    return ai_core.enabled(tool)


def sync_button(btn, tool, full_height):
    """Hidden (no space, no touches) unless the master switch, the provider
    and this tool's tick box are all on. Call from on_enter, so a change made
    in Settings shows up the next time the screen opens."""
    on = ai_core.enabled(tool)
    btn.opacity = 1 if on else 0
    btn.disabled = not on
    btn.height = full_height if on else 0
    return on


def _msg(title, text, height=0.4):
    lbl = Label(text=text, font_size=sp(13), halign="left", valign="middle")
    lbl.bind(width=lambda w, v: setattr(w, "text_size", (v - dp(16), None)))
    Popup(title=title, content=lbl, size_hint=(0.85, height)).open()


def show_error(text):
    _msg("AI problem", text)


def ask(title, hint, on_submit, button="Ask", initial=""):
    lay = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
    box = TextInput(text=initial, hint_text=hint, multiline=True,
                    font_size=sp(14))
    lay.add_widget(box)
    note = Label(text="What you type here is sent to the AI provider you "
                      "chose in Settings.", font_size=sp(10),
                 size_hint_y=None, height=dp(18), color=(0.6, 0.6, 0.6, 1))
    lay.add_widget(note)
    row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
    go = Button(text=button)
    cancel = Button(text="Cancel")
    row.add_widget(go)
    row.add_widget(cancel)
    lay.add_widget(row)
    pop = Popup(title=title, content=lay, size_hint=(0.92, 0.6))

    def _go(*_):
        text = box.text.strip()
        if not text:
            return
        pop.dismiss()
        on_submit(text)

    go.bind(on_release=_go)
    cancel.bind(on_release=lambda *a: pop.dismiss())
    pop.open()
    Clock.schedule_once(lambda dt: setattr(box, "focus", True), 0.2)
    return pop


def work(fn, done, title="Asking the AI..."):
    """Run fn() in a thread behind a small 'working' popup (with Cancel, which
    just stops waiting for the answer). done(result, error_text) runs on the
    UI thread."""
    state = {"cancelled": False}
    lbl = Label(text="This can take a while with a local model.",
                font_size=sp(12))
    lay = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
    lay.add_widget(lbl)
    cancel = Button(text="Cancel", size_hint_y=None, height=dp(40))
    lay.add_widget(cancel)
    pop = Popup(title=title, content=lay, size_hint=(0.7, 0.3),
                auto_dismiss=False)

    def _cancel(*_):
        state["cancelled"] = True
        pop.dismiss()

    cancel.bind(on_release=_cancel)
    pop.open()

    def run():
        result = err = None
        try:
            result = fn()
        except ai_core.AIError as e:
            err = str(e)
        except Exception as e:                      # never crash the app
            err = f"Something went wrong: {e}"

        def finish(dt):
            if state["cancelled"]:
                return
            pop.dismiss()
            done(result, err)

        Clock.schedule_once(finish)

    threading.Thread(target=run, daemon=True).start()
