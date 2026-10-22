# screens/learn_screen.py - Learn: import an AI-written course (JSON) and
# study it Duolingo-style. Engine lives in core/learn_core.py.
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core import learn_core as L

BG_BTN = (0.17, 0.18, 0.21, 1)
GOOD = (0.25, 0.65, 0.35, 1)
BAD = (0.80, 0.30, 0.30, 1)
ACCENT = (0.25, 0.45, 0.80, 1)
PICKED = (0.30, 0.40, 0.65, 1)


def _wrap_label(text, font_size=15, **kw):
    """Label that wraps to its width and grows tall enough for its text."""
    lb = Label(text=text, font_size=font_size, halign="left", valign="top",
               size_hint_y=None, markup=kw.pop("markup", False), **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lb.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(6)))
    return lb


def _btn(text, cb, h=44, color=None, **kw):
    b = Button(text=text, size_hint_y=None, height=dp(h), **kw)
    if color:
        b.background_normal = ""
        b.background_color = color
    b.bind(on_release=lambda *a: cb())
    return b


class LearnScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._root = BoxLayout(orientation="vertical", padding=dp(10),
                               spacing=dp(8))
        self.add_widget(self._root)
        self._plan = None
        self._les = None
        self._locked = False
        self._picked = set()
        self._opt_btns = []
        self._input = None

    def on_pre_enter(self, *a):
        self._show_home()

    # ---- helpers ---------------------------------------------------------
    def _clear(self):
        self._root.clear_widgets()

    def _scroll(self):
        """Scrollable vertical column; returns the column to add into."""
        sv = ScrollView(do_scroll_x=False)
        col = BoxLayout(orientation="vertical", size_hint_y=None,
                        spacing=dp(8), padding=(0, 0, 0, dp(8)))
        col.bind(minimum_height=col.setter("height"))
        sv.add_widget(col)
        self._root.add_widget(sv)
        return col

    def _back_row(self, text, cb):
        self._root.add_widget(_btn(text, cb))

    def _toast(self, msg, title="Learn"):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        box.add_widget(_wrap_label(msg, 14))
        ok = _btn("OK", lambda: p.dismiss())
        box.add_widget(ok)
        p = Popup(title=title, content=box, size_hint=(0.9, 0.5))
        p.open()

    # ---- home ------------------------------------------------------------
    def _show_home(self):
        self._clear()
        self._les = None
        st = L.load_progress()
        self._root.add_widget(Label(
            text="[b]Learn[/b]", markup=True, size_hint_y=None,
            height=dp(34), font_size=20))
        self._root.add_widget(Label(
            text=f"XP {st['xp']}    Streak {L.current_streak(st)} day(s)",
            size_hint_y=None, height=dp(22), font_size=14,
            color=(0.8, 0.8, 0.6, 1)))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        row.add_widget(_btn("Import course", self._import_popup,
                            color=ACCENT))
        row.add_widget(_btn("Get AI prompt", self._prompt_popup))
        self._root.add_widget(row)

        col = self._scroll()
        plans = L.list_plans()
        if not plans:
            col.add_widget(_wrap_label(
                "No courses yet.\n\n1. Tap [Get AI prompt], enter a topic, "
                "copy the prompt.\n2. Paste it into any AI chat.\n3. Copy "
                "the JSON it answers with, tap [Import course] and paste it.",
                14, color=(0.75, 0.75, 0.75, 1)))
        for p in plans:
            done, total = L.plan_counts(st, p)
            col.add_widget(_btn(
                f"{p['title']}\n{done}/{total} lessons"
                + (f"  -  {p['level']}" if p["level"] else ""),
                lambda p=p: self._show_plan(p), h=64, color=BG_BTN,
                halign="center"))
        self._back_row("< Back", self._leave)

    def _leave(self):
        self.manager.current = "dashboard"

    # ---- import / prompt popups ------------------------------------------
    def _import_popup(self):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        box.add_widget(Label(
            text="Paste the course JSON the AI gave you:",
            size_hint_y=None, height=dp(24), font_size=13))
        ti = TextInput(hint_text="{ ... }", multiline=True)
        box.add_widget(ti)
        msg = _wrap_label("", 13, color=(1, 0.6, 0.5, 1))
        box.add_widget(msg)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))

        def paste():
            try:
                ti.text = Clipboard.paste() or ""
            except Exception:
                msg.text = "Could not read the clipboard - paste by hand."

        def do_import():
            try:
                plan, warns = L.parse_plan(ti.text)
            except ValueError as e:
                msg.color = (1, 0.6, 0.5, 1)
                msg.text = str(e)
                return
            L.save_plan(plan)
            p.dismiss()
            self._show_home()
            if warns:
                self._toast("Imported, but some parts were skipped:\n"
                            + "\n".join(warns[:8]))

        row.add_widget(_btn("Paste", paste))
        row.add_widget(_btn("Import", do_import, color=ACCENT))
        row.add_widget(_btn("Cancel", lambda: p.dismiss()))
        box.add_widget(row)
        p = Popup(title="Import course", content=box, size_hint=(0.95, 0.85))
        p.open()

    def _prompt_popup(self):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        topic = TextInput(hint_text="Topic, e.g. Python for beginners",
                          multiline=False, size_hint_y=None, height=dp(40))
        level = TextInput(text="beginner", multiline=False,
                          size_hint_y=None, height=dp(40))
        box.add_widget(topic)
        box.add_widget(level)
        sv = ScrollView()
        out = _wrap_label("", 11, color=(0.8, 0.8, 0.8, 1))
        sv.add_widget(out)
        box.add_widget(sv)

        def refresh(*a):
            out.text = L.build_prompt(topic.text, level.text)

        topic.bind(text=refresh)
        level.bind(text=refresh)
        refresh()

        def copy():
            try:
                Clipboard.copy(L.build_prompt(topic.text, level.text))
                msg.text = "Copied. Paste it into your AI chat."
            except Exception:
                msg.text = "Could not copy - select the text by hand."

        msg = Label(text="", size_hint_y=None, height=dp(20), font_size=12,
                    color=(0.6, 0.9, 0.6, 1))
        box.add_widget(msg)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(_btn("Copy prompt", copy, color=ACCENT))
        row.add_widget(_btn("Close", lambda: p.dismiss()))
        box.add_widget(row)
        p = Popup(title="Prompt for the AI", content=box,
                  size_hint=(0.95, 0.9))
        p.open()

    # ---- course view -----------------------------------------------------
    def _show_plan(self, plan):
        self._plan = plan
        self._clear()
        st = L.load_progress()
        done, total = L.plan_counts(st, plan)
        self._root.add_widget(_wrap_label(f"[b]{plan['title']}[/b]", 18,
                                          markup=True))
        if plan["description"]:
            self._root.add_widget(_wrap_label(plan["description"], 13,
                                              color=(0.75, 0.75, 0.75, 1)))
        bar = ProgressBar(max=max(total, 1), value=done, size_hint_y=None,
                          height=dp(10))
        self._root.add_widget(bar)
        nxt = L.next_lesson(st, plan)
        if nxt:
            self._root.add_widget(_btn(
                "Continue: " + plan["units"][nxt[0]]["lessons"][nxt[1]]["title"],
                lambda: self._start_lesson(*nxt), h=50, color=GOOD))
        else:
            self._root.add_widget(Label(
                text="Course complete!", size_hint_y=None, height=dp(30),
                color=(0.6, 1, 0.6, 1)))
        col = self._scroll()
        for ui, u in enumerate(plan["units"]):
            col.add_widget(_wrap_label(f"[b]{ui + 1}. {u['title']}[/b]", 15,
                                       markup=True, color=(0.9, 0.85, 0.6, 1)))
            for li, les in enumerate(u["lessons"]):
                sc = L.best_score(st, plan["id"], ui, li)
                tag = "  [not started]" if sc is None else f"  [{sc}%]"
                col.add_widget(_btn(
                    f"{les['title']}{tag}",
                    lambda ui=ui, li=li: self._start_lesson(ui, li),
                    color=BG_BTN if sc is None else (0.15, 0.30, 0.20, 1)))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        row.add_widget(_btn("< Courses", self._show_home))
        row.add_widget(_btn("Delete course", lambda: self._confirm_delete(plan),
                            color=(0.35, 0.18, 0.18, 1)))
        self._root.add_widget(row)

    def _confirm_delete(self, plan):
        box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        box.add_widget(_wrap_label(
            f"Delete '{plan['title']}' and its progress?", 14))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))

        def yes():
            L.delete_plan(plan["id"])
            p.dismiss()
            self._show_home()

        row.add_widget(_btn("Delete", yes, color=BAD))
        row.add_widget(_btn("Cancel", lambda: p.dismiss()))
        box.add_widget(row)
        p = Popup(title="Delete course", content=box, size_hint=(0.9, 0.35))
        p.open()

    # ---- lesson runner ---------------------------------------------------
    def _start_lesson(self, ui, li):
        plan = self._plan
        les = plan["units"][ui]["lessons"][li]
        steps = []
        if les["intro"]:
            steps.append({"type": "info", "text": les["intro"]})
        steps += [dict(i, _first=True) for i in les["items"]]
        self._les = {"ui": ui, "li": li, "steps": steps, "pos": 0,
                     "correct": 0, "total": sum(
                         1 for i in steps if i["type"] != "info")}
        self._show_step()

    def _show_step(self):
        s = self._les
        if s["pos"] >= len(s["steps"]):
            return self._finish_lesson()
        item = s["steps"][s["pos"]]
        self._clear()
        les = self._plan["units"][s["ui"]]["lessons"][s["li"]]
        top = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        top.add_widget(_btn("X", self._quit_lesson, h=30, size_hint_x=None,
                            width=dp(40)))
        top.add_widget(ProgressBar(max=len(s["steps"]), value=s["pos"]))
        self._root.add_widget(top)
        self._root.add_widget(_wrap_label(f"[b]{les['title']}[/b]", 14,
                                          markup=True,
                                          color=(0.7, 0.7, 0.8, 1)))
        col = self._scroll()
        if item["type"] == "info":
            col.add_widget(_wrap_label(item["text"], 16))
            self._root.add_widget(_btn("Continue", self._next_step, h=50,
                                       color=ACCENT))
            return
        col.add_widget(_wrap_label(item["q"], 17))
        self._picked = set()
        self._opt_btns = []
        self._input = None
        if item["type"] in ("choice", "multi"):
            if item["type"] == "multi":
                col.add_widget(_wrap_label("(pick all that apply)", 12,
                                           color=(0.7, 0.7, 0.7, 1)))
            for i, o in enumerate(item["options"]):
                b = _btn(o, lambda i=i: self._pick(item, i), h=48,
                         color=BG_BTN)
                self._opt_btns.append(b)
                col.add_widget(b)
        elif item["type"] == "tf":
            for val, text in ((True, "True"), (False, "False")):
                b = _btn(text, lambda v=val: self._pick(item, v), h=48,
                         color=BG_BTN)
                self._opt_btns.append(b)
                col.add_widget(b)
        else:
            self._input = TextInput(hint_text="Your answer", multiline=False,
                                    size_hint_y=None, height=dp(44))
            self._input.bind(on_text_validate=lambda *a: self._check(item))
            col.add_widget(self._input)
        self._feedback = _wrap_label("", 15)
        col.add_widget(self._feedback)
        self._action = _btn("Check", lambda: self._check(item), h=50,
                            color=ACCENT)
        self._root.add_widget(self._action)

    def _pick(self, item, val):
        if getattr(self, "_locked", False):
            return
        if item["type"] == "multi":
            self._picked ^= {val}
        else:
            self._picked = {val}
        keys = ([True, False] if item["type"] == "tf"
                else range(len(item["options"])))
        for k, b in zip(keys, self._opt_btns):
            b.background_color = PICKED if k in self._picked else BG_BTN

    def _check(self, item):
        if getattr(self, "_locked", False):
            return
        t = item["type"]
        if t == "type":
            given = self._input.text
            if not given.strip():
                return
        elif not self._picked:
            return
        elif t == "multi":
            given = sorted(self._picked)
        else:
            given = next(iter(self._picked))
        ok = L.check_answer(item, given)
        s = self._les
        if ok and item.get("_first"):
            s["correct"] += 1
        if not ok and item.get("_first"):
            # wrong first time: ask it again at the end of the lesson
            s["steps"].append(dict(item, _first=False))
        self._locked = True
        expl = ("\n" + item["explain"]) if item.get("explain") else ""
        if ok:
            self._feedback.color = (0.5, 0.95, 0.55, 1)
            self._feedback.text = "Correct!" + expl
        else:
            self._feedback.color = (1, 0.55, 0.5, 1)
            self._feedback.text = ("Not quite. Answer: "
                                   + L.answer_text(item) + expl)
        self._root.remove_widget(self._action)
        self._action = _btn("Continue", self._next_step, h=50,
                            color=GOOD if ok else BAD)
        self._root.add_widget(self._action)

    def _next_step(self):
        self._locked = False
        self._les["pos"] += 1
        self._show_step()

    def _quit_lesson(self):
        self._locked = False
        self._show_plan(self._plan)

    def _finish_lesson(self):
        s = self._les
        st = L.load_progress()
        gained = L.record_lesson(st, self._plan["id"], s["ui"], s["li"],
                                 s["correct"], s["total"])
        L.save_progress(st)
        self._clear()
        pct = int(round(100 * s["correct"] / s["total"])) if s["total"] else 100
        self._root.add_widget(Label(
            text=("[b]Lesson complete![/b]\n\n"
                  f"{s['correct']}/{s['total']} right first try ({pct}%)\n"
                  f"+{gained} XP    Streak {L.current_streak(st)} day(s)"),
            markup=True, halign="center", font_size=18))
        nxt = L.next_lesson(st, self._plan)
        if nxt:
            self._root.add_widget(_btn(
                "Next lesson", lambda: self._start_lesson(*nxt), h=50,
                color=GOOD))
        self._root.add_widget(_btn("Back to course",
                                   lambda: self._show_plan(self._plan)))
