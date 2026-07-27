# screens/converted/unhelpful_calc_screen.py
# Improved: more errors, running expression preview, "loading" animation, copy result

import random
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.metrics import dp

FAKE_ERRORS = [
    "Stnax Error: Unexpected cheese slice.",
    "Error 404: Answer not found.",
    "Fatal Error: You tried to divide by cucumber.",
    "Upgrade to Premium Math™ to continue.",
    "Your math privileges have been revoked.",
    "Calculator is on break. Try again later.",
    "Illegal equation detected. FBI notified.",
    "Processor overheated by this equation.",
    "Result classified. Security clearance required.",
    "Unexpected Error: Universe not ready.",
    "Nah. I'm good.",
    "LOL. No.",
    "Math not found. Have you tried turning it off?",
    "Critical math failure. Please contact your local wizard.",
    "Answer lost in transit. Estimated delivery: 2047.",
    "This equation has been reported for misinformation.",
    "NaN: Not a Number (Not your Number either).",
    "Error 418: I am a teapot, not a calculator.",
    "Segmentation fault (core dumped) — your fault.",
    "Results redacted for national security.",
    "Have you considered just guessing?",
    "Error: math.exe has stopped responding.",
    "Your equation violated our Terms of Service.",
    "Calculating... just kidding.",
    "Stack overflow in your brain detected.",
    "Please try again when Mercury is no longer in retrograde.",
    "ERROR: Too many numbers. Please use fewer numbers.",
    "This calculator runs on vibes. Vibes are low.",
]

LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class UnhelpfulCalcScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._expr = ""
        self._anim_ev = None
        self._anim_frame = 0

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)

        root.add_widget(Label(
            text="[b]Unhelpful Calculator[/b]", markup=True,
            size_hint_y=None, height=dp(32), font_size=17,
        ))

        # ── expression display (small) ──
        self.expr_label = Label(
            text="", font_size=14, halign="right", valign="middle",
            color=(0.6, 0.6, 0.6, 1),
            size_hint_y=None, height=dp(26),
        )
        self.expr_label.bind(size=self.expr_label.setter("text_size"))
        root.add_widget(self.expr_label)

        # ── main display ──
        self.display = Label(
            text="0", font_size=30, halign="right", valign="middle",
            size_hint_y=None, height=dp(56),
        )
        self.display.bind(size=self.display.setter("text_size"))
        root.add_widget(self.display)

        # ── button grid ──
        grid = GridLayout(cols=4, spacing=5, size_hint_y=0.65)
        layout_rows = [
            [("C", self._clear, (0.7, 0.2, 0.2, 1)),
             ("+/-", self._negate, None),
             ("%", lambda *a: self._press("%"), None),
             ("÷", lambda *a: self._press("÷"), (0.3, 0.55, 0.8, 1))],
            [("7", lambda *a: self._press("7"), None),
             ("8", lambda *a: self._press("8"), None),
             ("9", lambda *a: self._press("9"), None),
             ("×", lambda *a: self._press("×"), (0.3, 0.55, 0.8, 1))],
            [("4", lambda *a: self._press("4"), None),
             ("5", lambda *a: self._press("5"), None),
             ("6", lambda *a: self._press("6"), None),
             ("−", lambda *a: self._press("−"), (0.3, 0.55, 0.8, 1))],
            [("1", lambda *a: self._press("1"), None),
             ("2", lambda *a: self._press("2"), None),
             ("3", lambda *a: self._press("3"), None),
             ("+", lambda *a: self._press("+"), (0.3, 0.55, 0.8, 1))],
            [("0", lambda *a: self._press("0"), None),
             (".", lambda *a: self._press("."), None),
             ("Del", self._backspace, None),
             ("=", self._equals, (0.25, 0.70, 0.35, 1))],
        ]
        for row in layout_rows:
            for text, cb, color in row:
                kw = dict(text=text, font_size=20)
                if color:
                    kw["background_color"] = color
                b = Button(**kw)
                b.bind(on_release=cb)
                grid.add_widget(b)

        root.add_widget(grid)

        # ── copy & back ──
        bot = BoxLayout(size_hint_y=None, height=dp(42), spacing=8)
        copy_btn = Button(text="Copy Copy", font_size=13)
        copy_btn.bind(on_release=lambda *a: Clipboard.copy(self.display.text))
        back_btn = Button(text="< Back", font_size=13)
        back_btn.bind(on_release=self._go_back)
        bot.add_widget(copy_btn)
        bot.add_widget(back_btn)
        root.add_widget(bot)

        self.add_widget(root)

    # ── input handlers ────────────────────────────────────────────────────────
    def _press(self, key):
        # clear error state
        if self.display.text in FAKE_ERRORS or self.display.text in ("0", "..."):
            self._expr = ""
            self.display.text = ""
        if self.display.text == "" and key in "÷×−+":
            return
        self._expr += key
        self.display.text = self._expr
        self.expr_label.text = ""

    def _clear(self, *a):
        if self._anim_ev:
            self._anim_ev.cancel()
            self._anim_ev = None
        self._expr = ""
        self.display.text = "0"
        self.expr_label.text = ""

    def _backspace(self, *a):
        if self._expr:
            self._expr = self._expr[:-1]
            self.display.text = self._expr if self._expr else "0"

    def _negate(self, *a):
        if self._expr and self._expr[0] == "−":
            self._expr = self._expr[1:]
        elif self._expr and self._expr != "0":
            self._expr = "−" + self._expr
        self.display.text = self._expr or "0"

    def _equals(self, *a):
        if not self._expr:
            return
        self.expr_label.text = self._expr + " ="
        self.display.text = LOADING_FRAMES[0]
        self._anim_frame = 0
        if self._anim_ev:
            self._anim_ev.cancel()
        # animate spinner for 1.5–2.5 s then show error
        delay = 1.5 + random.random()
        self._anim_ev = Clock.schedule_interval(self._tick_anim, 0.08)
        Clock.schedule_once(self._show_error, delay)

    def _tick_anim(self, dt):
        self._anim_frame = (self._anim_frame + 1) % len(LOADING_FRAMES)
        self.display.text = LOADING_FRAMES[self._anim_frame]

    def _show_error(self, dt):
        if self._anim_ev:
            self._anim_ev.cancel()
            self._anim_ev = None
        self.display.text = random.choice(FAKE_ERRORS)
        self._expr = ""

    def _go_back(self, *a):
        if self._anim_ev:
            self._anim_ev.cancel()
        if self.manager:
            self.manager.current = "dashboard"
