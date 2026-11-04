# screens/math_steps_screen.py - Math Steps: type an equation (or an
# expression), then solve it one line at a time. Every line is checked by
# core/math_steps_core.py: the first wrong line is flagged and explained, hints
# come in three levels, and "Show solution" is there when you want it.
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core import math_steps_core as ms
from core import theme
from screens.scaffold import ToolScreen

GOOD, BAD, NOTE = "7fdc94", "ff8a80", "9fb0c8"
KEYS = ("x", "^", "/", "(", ")", "=", "*", "+", "-")


class MathStepsScreen(ToolScreen):
    title = "Math Steps"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.session = None
        self._hint_level = 0
        self._active = None                    # the input the keypad types into
        root = self.body

        prow = BoxLayout(size_hint_y=None, height=dp(44), spacing=theme.PAD["s"])
        self.problem_in = self._input("Problem, e.g.  3(x+2)=15  or  2x+3x")
        self.problem_in.bind(on_text_validate=lambda *a: self.start())
        start = Button(text="Start", size_hint_x=None, width=dp(84),
                       font_size=sp(13), background_color=theme.ACCENT)
        start.bind(on_release=lambda *a: self.start())
        prow.add_widget(self.problem_in)
        prow.add_widget(start)
        root.add_widget(prow)

        keys = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
        for k in KEYS:
            b = Button(text=k, font_size=sp(15))
            b.bind(on_release=lambda inst, k=k: self._type(k))
            keys.add_widget(b)
        root.add_widget(keys)

        self.info = self._label("Type a problem and press Start. Then write "
                                "each step of your solution on its own line.",
                                NOTE, dp(40))
        root.add_widget(self.info)

        sv = ScrollView(do_scroll_x=False)
        self.log = BoxLayout(orientation="vertical", size_hint_y=None,
                             spacing=dp(2), padding=(dp(2), dp(2)))
        self.log.bind(minimum_height=self.log.setter("height"))
        sv.add_widget(self.log)
        self._sv = sv
        root.add_widget(sv)

        self.feedback = self._label("", NOTE, dp(52))
        root.add_widget(self.feedback)

        srow = BoxLayout(size_hint_y=None, height=dp(44), spacing=theme.PAD["s"])
        self.step_in = self._input("Your next step")
        self.step_in.bind(on_text_validate=lambda *a: self.check())
        check = Button(text="Check", size_hint_x=None, width=dp(84),
                       font_size=sp(13), background_color=theme.ACCENT)
        check.bind(on_release=lambda *a: self.check())
        srow.add_widget(self.step_in)
        srow.add_widget(check)
        root.add_widget(srow)

        brow = BoxLayout(size_hint_y=None, height=dp(40), spacing=theme.PAD["s"])
        self.hint_btn = Button(text="Hint", font_size=sp(13))
        self.hint_btn.bind(on_release=lambda *a: self.hint())
        self.solve_btn = Button(text="Show solution", font_size=sp(13))
        self.solve_btn.bind(on_release=lambda *a: self.show_solution())
        for b in (self.hint_btn, self.solve_btn):
            brow.add_widget(b)
        root.add_widget(brow)
        self._enable(False)

    # ── small widget helpers ──────────────────────────────────────────────
    def _input(self, hint):
        ti = TextInput(hint_text=hint, multiline=False, font_size=sp(15),
                       write_tab=False)
        ti.bind(focus=lambda w, f: f and setattr(self, "_active", w))
        return ti

    def _label(self, text, color, height):
        lbl = Label(text=text, markup=True, font_size=sp(13), halign="left",
                    valign="middle", size_hint_y=None, height=height,
                    color=theme.TEXT)
        lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        lbl.bind(texture_size=lambda w, v: setattr(w, "height", max(v[1], height)))
        return lbl

    def _enable(self, on):
        for w in (self.step_in, self.hint_btn, self.solve_btn):
            w.disabled = not on

    def _type(self, text):
        ti = self._active or self.step_in
        if ti.disabled:
            ti = self.problem_in
        ti.insert_text(text)
        Clock.schedule_once(lambda dt: setattr(ti, "focus", True), 0)

    def _add_line(self, text, color=theme.TEXT):
        lbl = self._label(text, color, dp(24))
        self.log.add_widget(lbl)
        Clock.schedule_once(self._scroll_end, 0.05)

    def _scroll_end(self, dt):
        # keep the newest line in view; a short log stays at the top
        self._sv.scroll_y = 0 if self.log.height > self._sv.height else 1

    def _say(self, text, color):
        self.feedback.text = f"[color={color}]{text}[/color]"

    # ── actions ───────────────────────────────────────────────────────────
    def start(self, *a):
        text = self.problem_in.text.strip()
        try:
            self.session = ms.Session(text)
        except ms.NotSupported as e:
            self._say(str(e), BAD)
            return
        except ms.MathError as e:
            self._say(str(e), BAD)
            return
        self._hint_level = 0
        self.log.clear_widgets()
        self.step_in.text = ""
        kind = "equation" if self.session.first.kind == "equation" else "expression"
        self._add_line(f"[b]{self.session.first.text}[/b]")
        n = self.session.n_steps
        extra = (f"about {n} step" + ("" if n == 1 else "s")) if n else \
            "I'll check your steps, but can't solve this kind yet"
        self.info.text = (f"[color={NOTE}]{kind.capitalize()} - "
                          f"{self.session.level.lower()} ({extra}). "
                          f"Write your first step below.[/color]")
        self._say("", NOTE)
        self._enable(True)
        self._active = self.step_in
        Clock.schedule_once(lambda dt: setattr(self.step_in, "focus", True), 0.1)

    def check(self, *a):
        if not self.session:
            return
        text = self.step_in.text.strip()
        if not text:
            return
        r = self.session.submit(text)
        if r.kind == "ok":
            self._hint_level = 0
            self._add_line(f"[color={GOOD}]OK[/color]   {r.text}   "
                           f"[color={NOTE}]{r.rule}[/color]")
            self.step_in.text = ""
            if r.done:
                self._finish()
            else:
                self._say("Good. Keep going.", GOOD)
        elif r.kind == "wrong":
            self._add_line(f"[color={BAD}]X[/color]    {text}", BAD)
            self._say(r.message + "  Try again from the last good line.", BAD)
        else:
            self._say(r.message, NOTE)
        Clock.schedule_once(lambda dt: setattr(self.step_in, "focus", True), 0.05)

    def _finish(self):
        out = self.session.status()
        self._say(f"Done - {out}. {self.session.summary()}", GOOD)
        self.step_in.disabled = True
        self.hint_btn.disabled = True

    def hint(self, *a):
        if not self.session:
            return
        self._hint_level = min(self._hint_level + 1, 3)
        h = self.session.hint(self._hint_level)
        label = ("Hint", "Hint", "Next action", "Next line")[self._hint_level]
        self._say(f"{label}: {h}" + ("" if self._hint_level == 3
                                      else "  (press Hint again for more)"), NOTE)

    def show_solution(self, *a):
        if not self.session:
            return
        steps = self.session.solution_from_here()
        if not steps:
            self._say("I can't solve this kind of problem yet, but "
                      "I'll still check every line you write.", NOTE)
            return
        for text, why in steps:
            self._add_line(f"[color={NOTE}]>[/color]   {text}   "
                           f"[color={NOTE}]{why}[/color]")
        self._say("That was the solution. " + self.session.summary(), NOTE)
        self.step_in.disabled = True
        self.hint_btn.disabled = True
