# screens/binary_screen.py — Text <-> Binary / Hex / Decimal converter (offline)

import re
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp

from core import theme
from screens.scaffold import ToolScreen

BASES = {"Binary": (2, 8), "Hex": (16, 2), "Decimal": (10, 0)}


def text_to_codes(text, base_name):
    base, width = BASES[base_name]
    out = []
    for b in text.encode("utf-8"):
        if base == 2:
            out.append(format(b, "08b"))
        elif base == 16:
            out.append(format(b, "02x"))
        else:
            out.append(str(b))
    return " ".join(out)


def codes_to_text(raw, base_name):
    base, width = BASES[base_name]
    raw = raw.strip()
    if not raw:
        return ""
    toks = raw.split()
    # no spaces -> binary/hex chunked by fixed width ("0100100001101001")
    if len(toks) == 1 and width and len(toks[0]) > width:
        t = toks[0]
        toks = [t[i:i + width] for i in range(0, len(t), width)]
    data = bytearray()
    for t in toks:
        t = re.sub(r"^0[bx]", "", t.lower())
        v = int(t, base)          # ValueError -> caller shows message
        if not 0 <= v <= 255:
            raise ValueError(f"{t} is out of byte range")
        data.append(v)
    return data.decode("utf-8", errors="replace")


class BinaryScreen(ToolScreen):
    title = "Binary / Hex / Decimal"

    def __init__(self, **kw):
        super().__init__(**kw)
        root = self.body

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        row.add_widget(Label(text="Format:", size_hint_x=None, width=dp(60),
                             font_size=sp(13)))
        self._base = Spinner(text="Binary", values=list(BASES),
                             font_size=sp(14))
        row.add_widget(self._base)
        root.add_widget(row)

        self.input = TextInput(hint_text="Type text or codes here…",
                               size_hint_y=0.35)
        root.add_widget(self.input)

        btns = BoxLayout(size_hint_y=None, height=dp(46), spacing=8)
        a = Button(text="Text > Code", font_size=sp(14))
        b = Button(text="Code > Text", font_size=sp(14))
        c = Button(text="Clear", size_hint_x=None, width=dp(70),
                   font_size=sp(13))
        a.bind(on_release=self._enc)
        b.bind(on_release=self._dec)
        c.bind(on_release=lambda *x: (setattr(self.input, "text", ""),
                                      setattr(self.output, "text", "")))
        for w in (a, b, c):
            btns.add_widget(w)
        root.add_widget(btns)

        self.output = TextInput(readonly=True, size_hint_y=0.35,
                                background_color=theme.SURFACE2,
                                foreground_color=theme.TEXT)
        root.add_widget(self.output)

        cp = Button(text="Copy Output", size_hint_y=None, height=dp(42))
        cp.bind(on_release=lambda *x: Clipboard.copy(self.output.text))
        root.add_widget(cp)

    def _enc(self, *a):
        self.output.text = text_to_codes(self.input.text, self._base.text)

    def _dec(self, *a):
        try:
            self.output.text = codes_to_text(self.input.text, self._base.text)
        except ValueError as e:
            self.output.text = f"Invalid {self._base.text.lower()} input: {e}"
