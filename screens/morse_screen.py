# screens/converted/morse_screen.py
# Improved: copy button, conversion history, cleaner layout, punctuation support

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
import collections

MORSE = {
    'A': '.-',    'B': '-...',  'C': '-.-.',  'D': '-..',
    'E': '.',     'F': '..-.',  'G': '--.',   'H': '....',
    'I': '..',    'J': '.---',  'K': '-.-',   'L': '.-..',
    'M': '--',    'N': '-.',    'O': '---',   'P': '.--.',
    'Q': '--.-',  'R': '.-.',   'S': '...',   'T': '-',
    'U': '..-',   'V': '...-',  'W': '.--',   'X': '-..-',
    'Y': '-.--',  'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--',
    '4': '....-', '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.',
    '.': '.-.-.-', ',': '--..--', '?': '..--..', "'": '.----.',
    '!': '-.-.--', '/': '-..-.',  '(': '-.--.',  ')': '-.--.-',
    '&': '.-...',  ':': '---...', ';': '-.-.-.',  '=': '-...-',
    '+': '.-.-.',  '-': '-....-', '_': '..--.-',  '"': '.-..-.',
    '$': '...-..-','@': '.--.-.',  ' ': '/',
}
REVERSE = {v: k for k, v in MORSE.items()}
HISTORY_MAX = 30


class MorseScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._history = collections.deque(maxlen=HISTORY_MAX)

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        root.add_widget(Label(
            text="[b]Morse Code Converter[/b]", markup=True,
            size_hint_y=None, height=dp(34), font_size=18,
        ))

        # ── input ──
        root.add_widget(Label(text="Input (text or morse):",
                              size_hint_y=None, height=dp(22), font_size=13))
        self.input = TextInput(
            hint_text="Type here…",
            size_hint_y=None, height=dp(100),
            background_color=(0.12, 0.12, 0.14, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        root.add_widget(self.input)

        # ── buttons ──
        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=8)
        t2m = Button(text="Text > Morse", font_size=14)
        m2t = Button(text="Morse > Text", font_size=14)
        clr = Button(text="Clear", size_hint_x=None, width=dp(70), font_size=13)
        t2m.bind(on_release=self._text_to_morse)
        m2t.bind(on_release=self._morse_to_text)
        clr.bind(on_release=lambda *a: (
            setattr(self.input, "text", ""),
            setattr(self.output, "text", ""),
        ))
        btn_row.add_widget(t2m)
        btn_row.add_widget(m2t)
        btn_row.add_widget(clr)
        root.add_widget(btn_row)

        # ── output ──
        root.add_widget(Label(text="Output:",
                              size_hint_y=None, height=dp(22), font_size=13))
        self.output = TextInput(
            text="", readonly=True,
            size_hint_y=None, height=dp(100),
            background_color=(0.10, 0.10, 0.12, 1),
            foreground_color=(0.85, 0.95, 0.85, 1),
        )
        root.add_widget(self.output)

        copy_btn = Button(text="Copy Copy Output", size_hint_y=None, height=dp(40))
        copy_btn.bind(on_release=lambda *a: Clipboard.copy(self.output.text))
        root.add_widget(copy_btn)

        # ── history ──
        root.add_widget(Label(text="History:", size_hint_y=None, height=dp(22),
                              font_size=13))
        sv = ScrollView(size_hint=(1, 0.25))
        self.hist_grid = GridLayout(cols=1, spacing=2, size_hint_y=None)
        self.hist_grid.bind(minimum_height=self.hist_grid.setter("height"))
        sv.add_widget(self.hist_grid)
        root.add_widget(sv)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "dashboard"))
        root.add_widget(back)

        self.add_widget(root)

    # ── conversion ──────────────────────────────────────────────────────────
    def _text_to_morse(self, *a):
        text = self.input.text.upper()
        parts = []
        unknown = []
        for ch in text:
            code = MORSE.get(ch)
            if code:
                parts.append(code)
            else:
                parts.append("?")
                if ch not in unknown:
                    unknown.append(ch)
        result = " ".join(parts)
        self.output.text = result
        note = f"  [unknown: {', '.join(unknown)}]" if unknown else ""
        self._push_history(f"T→M: {self.input.text[:30]}{note}")

    def _morse_to_text(self, *a):
        raw = self.input.text.strip()
        # words are separated by " / ", letters by " "
        words = raw.split(" / ")
        decoded_words = []
        for word in words:
            letters = word.strip().split()
            decoded_words.append(
                "".join(REVERSE.get(l, "?") for l in letters)
            )
        result = " ".join(decoded_words)
        self.output.text = result
        self._push_history(f"M→T: {result[:40]}")

    # ── history ─────────────────────────────────────────────────────────────
    def _push_history(self, entry: str):
        self._history.appendleft(entry)
        self.hist_grid.clear_widgets()
        for e in self._history:
            lbl = Label(text=e, size_hint_y=None, height=dp(24),
                        font_size=11, halign="left")
            lbl.bind(size=lbl.setter("text_size"))
            self.hist_grid.add_widget(lbl)
