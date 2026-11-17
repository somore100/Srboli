# screens/text_workbench_screen.py - Text Workbench: one screen, five tabs
# (Lines, Extract, Regex, Diff, Stats) over the same text. The logic lives in
# core/text_workbench_core.py; this file only lays it out.
#
# Input on top, result below. "Use result as input" chains the tools: sort,
# then dedupe, then number, without copying anything out.

import os

from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from core import text_workbench_core as core
from core import theme
from screens.scaffold import ToolScreen

TABS = [("lines", "Lines"), ("extract", "Extract"), ("regex", "Regex"),
        ("diff", "Diff"), ("stats", "Stats")]
ON = (0.2, 0.45, 0.75, 1)
OFF = (0.25, 0.25, 0.25, 1)


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(6))


def _tick(row, text):
    """A tick box with a label; returns the CheckBox."""
    cb = CheckBox(size_hint=(None, None), size=(dp(26), dp(26)))
    row.add_widget(cb)
    lbl = Label(text=text, font_size=sp(11), halign="left", valign="middle",
                color=theme.MUTED, size_hint_x=None, width=dp(96))
    lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
    row.add_widget(lbl)
    return cb


class TextWorkbenchScreen(ToolScreen):
    title = "Text Workbench"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tab = "lines"
        root = self.body

        tabs = _row(38)
        self.tab_btns = {}
        for key, label in TABS:
            b = Button(text=label, font_size=sp(12), background_normal="",
                       background_color=OFF)
            b.bind(on_release=lambda i, k=key: self.show_tab(k))
            self.tab_btns[key] = b
            tabs.add_widget(b)
        root.add_widget(tabs)

        self.input = TextInput(hint_text="Paste or type your text here "
                                         "(or use Open file...)",
                               font_size=sp(13))
        root.add_widget(self.input)
        self.input_b = TextInput(hint_text="The second text, to compare with",
                                 font_size=sp(13), size_hint_y=None, height=0,
                                 opacity=0, disabled=True)
        root.add_widget(self.input_b)

        # per-tab option rows (only the current one is shown)
        self.opts = {}
        self._build_lines()
        self._build_extract()
        self._build_regex()
        self._build_diff()
        self._build_stats()
        self.opt_holder = BoxLayout(orientation="vertical", size_hint_y=None,
                                    height=0, spacing=dp(4))
        root.add_widget(self.opt_holder)

        self.status = Label(text="", font_size=sp(11), color=theme.MUTED,
                            size_hint_y=None, height=dp(20), halign="left",
                            valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.status)

        self.output = TextInput(readonly=True, font_size=sp(13),
                                hint_text="The result appears here")
        root.add_widget(self.output)

        bottom = _row(40)
        for text, fn in (("Copy result", self.copy_result),
                         ("Use result as input", self.use_result),
                         ("Open file...", self.open_file),
                         ("Clear", self.clear)):
            b = Button(text=text, font_size=sp(11))
            b.bind(on_release=lambda i, f=fn: f())
            bottom.add_widget(b)
        root.add_widget(bottom)
        self.show_tab("lines")

    # ── helpers ─────────────────────────────────────────────────────────
    def say(self, text):
        self.status.text = text

    def show_result(self, text, note=""):
        self.output.text = text
        self.say(note)

    def _guard(self, fn):
        try:
            fn()
        except core.TextError as e:
            self.show_result("", str(e))

    def show_tab(self, key):
        self.tab = key
        for k, b in self.tab_btns.items():
            b.background_color = ON if k == key else OFF
        holder = self.opt_holder
        holder.clear_widgets()
        rows = self.opts[key]
        for r in rows:
            holder.add_widget(r)
        holder.height = sum(r.height for r in rows) + dp(4) * (len(rows) - 1)
        diff = key == "diff"
        self.input_b.disabled = not diff
        self.input_b.opacity = 1 if diff else 0
        self.input_b.size_hint_y = 0.5 if diff else None
        if not diff:
            self.input_b.height = 0
        if key == "stats":
            self.run_stats()

    # ── Lines ───────────────────────────────────────────────────────────
    def _build_lines(self):
        self._line_keys = list(core.LINE_OPS)
        r1 = _row()
        self.line_op = Spinner(text=core.LINE_OPS["sort"][0],
                               values=[v[0] for v in core.LINE_OPS.values()],
                               font_size=sp(12))
        self.line_op.bind(text=lambda *a: self._line_hint())
        r1.add_widget(self.line_op)
        run = Button(text="Run", size_hint_x=None, width=dp(80),
                     background_color=(0.2, 0.55, 0.2, 1))
        run.bind(on_release=lambda *a: self.run_lines())
        r1.add_widget(run)
        r2 = _row()
        self.line_arg = TextInput(multiline=False, font_size=sp(12),
                                  hint_text="option")
        r2.add_widget(self.line_arg)
        self.line_ic = _tick(r2, "ignore case")
        self.opts["lines"] = [r1, r2]

    def _line_key(self):
        for k, (label, _hint) in core.LINE_OPS.items():
            if label == self.line_op.text:
                return k
        return "sort"

    def _line_hint(self):
        hint = core.LINE_OPS[self._line_key()][1]
        self.line_arg.hint_text = hint or "(this one needs no option)"
        self.line_arg.disabled = not hint

    def run_lines(self):
        self._guard(lambda: self._do_lines())

    def _do_lines(self):
        key = self._line_key()
        out = core.apply_lines(key, self.input.text, self.line_arg.text,
                               ignore_case=self.line_ic.active)
        before, after = len(self.input.text.splitlines()), len(out.splitlines())
        self.show_result(out, f"{before} lines in, {after} out.")

    # ── Extract ─────────────────────────────────────────────────────────
    def _build_extract(self):
        r1 = _row()
        self.ex_kind = Spinner(text=core.EXTRACTORS["emails"][0],
                               values=[v[0] for v in core.EXTRACTORS.values()],
                               font_size=sp(12))
        r1.add_widget(self.ex_kind)
        run = Button(text="Find", size_hint_x=None, width=dp(80),
                     background_color=(0.2, 0.55, 0.2, 1))
        run.bind(on_release=lambda *a: self._guard(self._do_extract))
        r1.add_widget(run)
        r2 = _row(34)
        self.ex_unique = _tick(r2, "no repeats")
        self.ex_unique.active = True
        self.ex_sort = _tick(r2, "sort")
        self.opts["extract"] = [r1, r2]

    def _do_extract(self):
        kind = next((k for k, v in core.EXTRACTORS.items()
                     if v[0] == self.ex_kind.text), "emails")
        found, text = core.extract(kind, self.input.text,
                                   self.ex_unique.active, self.ex_sort.active)
        self.show_result(text, f"{len(found)} found." if found else "Nothing found.")

    # ── Regex ───────────────────────────────────────────────────────────
    def _build_regex(self):
        r1 = _row()
        self.rx_pat = TextInput(multiline=False, font_size=sp(12),
                                hint_text="pattern, e.g. (\\d+)-(\\w+)")
        self.rx_pat.bind(text=lambda *a: self._rx_live())
        r1.add_widget(self.rx_pat)
        r2 = _row()
        self.rx_rep = TextInput(multiline=False, font_size=sp(12),
                                hint_text="replace with (\\1 = group 1)")
        r2.add_widget(self.rx_rep)
        r3 = _row(34)
        self.rx_i = _tick(r3, "ignore case")
        self.rx_m = _tick(r3, "^ $ per line")
        self.rx_s = _tick(r3, ". matches \\n")
        r4 = _row()
        test = Button(text="Show matches", font_size=sp(12))
        test.bind(on_release=lambda *a: self._guard(self._do_rx_test))
        rep = Button(text="Replace all", font_size=sp(12),
                     background_color=(0.2, 0.55, 0.2, 1))
        rep.bind(on_release=lambda *a: self._guard(self._do_rx_replace))
        r4.add_widget(test)
        r4.add_widget(rep)
        self.opts["regex"] = [r1, r2, r3, r4]

    def _flags(self):
        return dict(ignore_case=self.rx_i.active, multiline=self.rx_m.active,
                    dotall=self.rx_s.active)

    def _rx_live(self):
        """Typing a pattern shows the matches at once (when the text is small)."""
        if self.tab != "regex" or len(self.input.text) > 20000:
            return
        if not self.rx_pat.text:
            return
        self._guard(self._do_rx_test)

    def _do_rx_test(self):
        self.show_result(core.regex_report(self.rx_pat.text, self.input.text,
                                           **self._flags()))

    def _do_rx_replace(self):
        out, n = core.regex_replace(self.rx_pat.text, self.rx_rep.text,
                                    self.input.text, **self._flags())
        self.show_result(out, f"{n} replacement{'s' if n != 1 else ''}.")

    # ── Diff ────────────────────────────────────────────────────────────
    def _build_diff(self):
        r1 = _row(34)
        self.df_space = _tick(r1, "ignore spaces")
        self.df_case = _tick(r1, "ignore case")
        r2 = _row()
        run = Button(text="Compare (top = A, middle = B)", font_size=sp(12),
                     background_color=(0.2, 0.55, 0.2, 1))
        run.bind(on_release=lambda *a: self._guard(self._do_diff))
        r2.add_widget(run)
        self.opts["diff"] = [r1, r2]

    def _do_diff(self):
        text, (added, removed, blocks) = core.diff_texts(
            self.input.text, self.input_b.text,
            ignore_space=self.df_space.active, ignore_case=self.df_case.active)
        self.show_result(text, f"{blocks} changed place{'s' if blocks != 1 else ''}: "
                               f"+{added} / -{removed} lines. (- only in A, + only in B)")

    # ── Stats ───────────────────────────────────────────────────────────
    def _build_stats(self):
        r = _row()
        run = Button(text="Count again", font_size=sp(12))
        run.bind(on_release=lambda *a: self.run_stats())
        r.add_widget(run)
        self.opts["stats"] = [r]

    def run_stats(self):
        self._guard(lambda: self.show_result(core.stats_report(self.input.text)))

    # ── bottom buttons ──────────────────────────────────────────────────
    def copy_result(self):
        if self.output.text:
            Clipboard.copy(self.output.text)
            self.say("Copied.")

    def use_result(self):
        if self.output.text:
            self.input.text = self.output.text
            self.output.text = ""
            self.say("The result is now the input.")

    def clear(self):
        self.input.text = self.input_b.text = self.output.text = ""
        self.say("")

    def open_file(self):
        start = os.path.expanduser("~")
        try:
            from core.android_storage import shared_storage_root
            start = shared_storage_root() or start
        except Exception:
            pass
        chooser = FileChooserIconView(path=start)
        use = Button(text="Open this file", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Open a text file", content=lay, size_hint=(0.92, 0.92))

        def _use(*a):
            if not chooser.selection:
                return
            pop.dismiss()
            self._load(chooser.selection[0])

        use.bind(on_release=_use)
        pop.open()

    def _load(self, path):
        try:
            if os.path.getsize(path) > core.MAX_CHARS * 4:
                raise core.TextError("That file is too big for this tool.")
            with open(path, "rb") as f:
                data = f.read()
            text = data.decode("utf-8", errors="replace")
            if "\x00" in text[:2000]:
                raise core.TextError("That looks like a binary file, not text.")
            core.check_size(text)
        except core.TextError as e:
            self.say(str(e))
            return
        except OSError as e:
            self.say(f"Couldn't read the file: {e}")
            return
        target = self.input_b if (self.tab == "diff" and self.input.text) else self.input
        target.text = text
        self.say(f"Opened {os.path.basename(path)}"
                 + (" into the second box." if target is self.input_b else "."))
