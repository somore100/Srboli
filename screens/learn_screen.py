# screens/learn_screen.py - Learn: import an AI-written course (JSON) and
# study it Duolingo-style. Engine lives in core/learn_core.py.
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.screenmanager import Screen
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import escape_markup as esc

from core import learn_core as L

BG_BTN = (0.17, 0.18, 0.21, 1)
GOOD = (0.25, 0.65, 0.35, 1)
BAD = (0.80, 0.30, 0.30, 1)
ACCENT = (0.25, 0.45, 0.80, 1)
PICKED = (0.30, 0.40, 0.65, 1)
GOLD = (0.85, 0.65, 0.15, 1)
LOCKED = (0.20, 0.21, 0.24, 1)


def _wrap_label(text, font_size=sp(15), **kw):
    """Label that wraps to its width and grows tall enough for its text."""
    lb = Label(text=text, font_size=font_size, halign="left", valign="top",
               size_hint_y=None, markup=kw.pop("markup", False), **kw)
    lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lb.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(6)))
    return lb


def _mode_spinner(*inputs):
    """The course-mode picker. Pass the popup's TextInputs: with the keyboard up, the
    tap that opens the dropdown also closes it (window resize), so the choice could not
    be picked - take focus off the inputs first (same fix as Script Mode)."""
    sp_ = Spinner(text=L.MODE_LABELS["course"], values=list(L.MODE_LABELS.values()),
                  size_hint_y=None, height=dp(40))

    def defocus(w, touch):
        if w.collide_point(*touch.pos):
            for ti in inputs:
                ti.focus = False
        return False

    sp_.bind(on_touch_down=defocus)
    return sp_


def _mode_of(sp_):
    return next((k for k, v in L.MODE_LABELS.items() if v == sp_.text), "course")


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
        self._sv = sv
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
            height=dp(34), font_size=sp(20)))
        self._root.add_widget(Label(
            text=f"XP {st['xp']}    Streak {L.current_streak(st)} day(s)",
            size_hint_y=None, height=dp(22), font_size=sp(14),
            color=(0.8, 0.8, 0.6, 1)))
        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        row.add_widget(_btn("Import course", self._import_popup,
                            color=ACCENT))
        row.add_widget(_btn("Get AI prompt", self._prompt_popup))
        self._root.add_widget(row)
        from screens import ai_ui
        if ai_ui.is_on("learn"):
            self._root.add_widget(_btn("Write a course with AI...", self._ai_course,
                                       color=ACCENT))

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

    def _ai_course(self):
        """Ask the AI in Settings for a course; it is imported like a pasted one."""
        from screens import ai_ui
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        topic = TextInput(hint_text="What do you want to learn?", multiline=False,
                          size_hint_y=None, height=dp(40))
        level = TextInput(text="beginner", multiline=False, size_hint_y=None,
                          height=dp(40))
        box.add_widget(topic)
        box.add_widget(level)
        mode_sp = _mode_spinner(topic, level)
        box.add_widget(mode_sp)
        box.add_widget(_wrap_label(
            "A whole course is a lot to write: a local model can take several "
            "minutes, and small ones often get it wrong. Your topic is sent to "
            "the AI you set up in Settings.", 12, color=(0.7, 0.7, 0.7, 1)))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        go = _btn("Write it", lambda: start(), color=ACCENT)
        row.add_widget(go)
        row.add_widget(_btn("Cancel", lambda: p.dismiss()))
        box.add_widget(row)
        p = Popup(title="Course from AI", content=box, size_hint=(0.92, 0.7))

        def start():
            t, lv = topic.text.strip(), level.text.strip() or "beginner"
            if not t:
                return
            p.dismiss()

            def done(res, err):
                if err:
                    return ai_ui.show_error(err)
                plan, warns = res
                L.save_plan(plan)
                self._show_home()
                if warns:
                    self._toast("Made, but some parts were skipped:\n"
                                + "\n".join(warns[:8]))

            md = _mode_of(mode_sp)
            ai_ui.work(lambda: L.ai_course(t, lv, mode=md), done,
                       title="Writing the course...")

        p.open()

    # ---- import / prompt popups ------------------------------------------
    def _import_popup(self):
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        box.add_widget(Label(
            text="Paste the course JSON the AI gave you:",
            size_hint_y=None, height=dp(24), font_size=sp(13)))
        ti = TextInput(hint_text="{ ... }", multiline=True)
        box.add_widget(ti)
        msg = _wrap_label("", 13, color=(1, 0.6, 0.5, 1))
        box.add_widget(msg)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        err = {"text": ""}

        def copy_error():
            try:
                Clipboard.copy(err["text"])
                msg.text = err["text"] + "\n(copied - paste it to the AI and ask it to fix the JSON)"
            except Exception:
                pass

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
                err["text"] = "The course JSON has an error. " + str(e)
                msg.text = str(e)
                copy_btn.disabled = False
                return
            L.save_plan(plan)
            p.dismiss()
            self._show_home()
            if warns:
                self._toast("Imported, but some parts were skipped:\n"
                            + "\n".join(warns[:8]))

        row.add_widget(_btn("Paste", paste))
        copy_btn = _btn("Copy error", copy_error)
        copy_btn.disabled = True
        row.add_widget(copy_btn)
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
        mode_sp = _mode_spinner(topic, level)
        box.add_widget(mode_sp)
        # read-only TextInput: stays put, drag selects text, scrolls inside
        out = TextInput(text="", readonly=True, font_size=sp(12),
                        background_color=(0.12, 0.12, 0.14, 1),
                        foreground_color=(0.85, 0.85, 0.85, 1))
        box.add_widget(out)

        def refresh(*a):
            text = L.build_prompt(topic.text, level.text, _mode_of(mode_sp))
            if out.text != text:                # re-laying out the long box is the slow part
                out.text = text

        def refresh_soon(*a):
            # Rebuilding the prompt box on every keystroke made typing lag on phones;
            # wait until the typing pauses.
            Clock.unschedule(refresh)
            Clock.schedule_once(refresh, 0.5)

        topic.bind(text=refresh_soon)
        level.bind(text=refresh_soon)
        mode_sp.bind(text=refresh_soon)
        refresh()
        self._prompt_refresh = refresh

        def copy():
            try:
                Clock.unschedule(refresh)
                Clipboard.copy(L.build_prompt(topic.text, level.text, _mode_of(mode_sp)))
                msg.text = "Copied. Paste it into your AI chat."
            except Exception:
                msg.text = "Could not copy - select the text by hand."

        msg = Label(text="", size_hint_y=None, height=dp(20), font_size=sp(12),
                    color=(0.6, 0.9, 0.6, 1))
        box.add_widget(msg)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(_btn("Copy prompt", copy, color=ACCENT))
        row.add_widget(_btn("Close", lambda: p.dismiss()))
        box.add_widget(row)
        p = Popup(title="Prompt for the AI", content=box,
                  size_hint=(0.95, 0.9))
        p.bind(on_dismiss=lambda *a: Clock.unschedule(refresh))
        self._prompt = (p, topic, level, out)
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
        general = plan.get("mode") == "general"
        graded = L.is_graded(st, plan["id"])
        self._root.add_widget(_wrap_label(
            L.MODE_LABELS.get(plan.get("mode"), "") + ("  -  points on" if graded else "  -  points off"),
            12, color=(0.65, 0.7, 0.8, 1)))
        bar = ProgressBar(max=max(total, 1), value=done, size_hint_y=None,
                          height=dp(10))
        self._root.add_widget(bar)
        nxt = L.next_lesson(st, plan)
        if general:
            self._root.add_widget(_btn(
                "Mixed practice (10 random questions)", self._start_mixed, h=50, color=GOOD))
        elif nxt:
            self._root.add_widget(_btn(
                "Continue: " + plan["units"][nxt[0]]["lessons"][nxt[1]]["title"],
                lambda: self._start_lesson(*nxt), h=50, color=GOOD))
        else:
            self._root.add_widget(Label(
                text="Course complete!", size_hint_y=None, height=dp(30),
                color=(0.6, 1, 0.6, 1)))
        tools = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        if not general and plan.get("mode") != "lesson":
            tools.add_widget(_btn(
                "Open all lessons: " + ("on" if st.get("free_roam") else "off"),
                self._toggle_free_roam, h=34, color=ACCENT if st.get("free_roam") else BG_BTN))
        tools.add_widget(_btn("Points: " + ("on" if graded else "off"), self._toggle_graded,
                              h=34, color=ACCENT if graded else BG_BTN))
        self._root.add_widget(tools)
        miss = L.missed_items(st, plan)
        if miss:
            self._root.add_widget(_btn(f"Practice what I missed ({len(miss)})",
                                       lambda: self._start_practice(miss, "Missed questions"),
                                       h=40, color=BAD))
        col = self._scroll()
        current_row = None
        for n in L.path_nodes(st, plan):
            if n["kind"] == "unit":
                banner = _wrap_label(
                    f"[b]Unit {n['ui'] + 1}: {n['title']}[/b]   {n['done']}/{n['total']}", 15,
                    markup=True, color=(0.95, 0.9, 0.65, 1))
                col.add_widget(banner)
                continue
            row = self._path_row(plan, n)
            col.add_widget(row)
            if n["kind"] == "lesson" and n["state"] == "current":
                current_row = row
        if current_row is not None:
            Clock.schedule_once(lambda dt: self._sv.scroll_to(current_row, padding=dp(60),
                                                              animate=False), 0.1)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        row.add_widget(_btn("< Courses", self._show_home))
        row.add_widget(_btn("Delete course", lambda: self._confirm_delete(plan),
                            color=(0.35, 0.18, 0.18, 1)))
        self._root.add_widget(row)

    def _toggle_free_roam(self):
        st = L.load_progress()
        st["free_roam"] = not st.get("free_roam")
        L.save_progress(st)
        self._show_plan(self._plan)

    def _toggle_graded(self):
        st = L.load_progress()
        L.set_graded(st, self._plan["id"], not L.is_graded(st, self._plan["id"]))
        L.save_progress(st)
        self._show_plan(self._plan)

    def _start_mixed(self):
        items = L.mixed_items(self._plan, 10)
        if items:
            self._start_practice(items, "Mixed practice")

    def _path_row(self, plan, n):
        """One step of the winding path: a round node in one of five sideways slots."""
        slots = [Widget() for _ in range(5)]
        if n["kind"] == "milestone":
            done = n["state"] == "done"
            btn = _btn("UNIT\nDONE" if done else "UNIT", lambda: self._milestone_info(plan, n),
                       h=64, color=GOLD if done else LOCKED, size_hint_x=None, width=dp(64))
            title = "+%d XP" % L.XP_UNIT_BONUS if not done else "Milestone reached"
        else:
            state = n["state"]
            if state == "done":
                text, color = "*" * max(1, n["stars"]), GOOD
            elif state == "current":
                text, color = "START", ACCENT
            elif state == "open":
                text, color = str(n["li"] + 1), BG_BTN
            else:
                text, color = "locked", LOCKED
            big = state == "current"
            btn = _btn(text, lambda: self._node_tapped(n), h=76 if big else 64, color=color,
                       size_hint_x=None, width=dp(76 if big else 64),
                       font_size=sp(18 if state == "done" else 13))
            if state == "done":
                btn.color = (1, 0.88, 0.3, 1)
            elif state == "locked":
                btn.color = (0.55, 0.57, 0.62, 1)
            title = n["title"]
        cell = BoxLayout(orientation="vertical", spacing=dp(2))
        anchor = AnchorLayout(anchor_x="center", anchor_y="center")
        anchor.add_widget(btn)
        cell.add_widget(anchor)
        lbl = Label(text=title, font_size=sp(10), size_hint_y=None, height=dp(24),
                    shorten=True, shorten_from="right", halign="center",
                    color=(0.7, 0.72, 0.78, 1))
        lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        cell.add_widget(lbl)
        row = BoxLayout(size_hint_y=None, height=dp(110))
        slots[2 + n["col"]] = cell
        for w in slots:
            row.add_widget(w)
        return row

    def _node_tapped(self, n):
        if n["state"] == "locked":
            self._toast("Finish the earlier lessons first.\n\nYou can also turn on "
                        "\"Open all lessons\" above to try any lesson.")
            return
        self._start_lesson(n["ui"], n["li"])

    def _milestone_info(self, plan, n):
        if n["state"] == "done":
            self._toast("You finished every lesson in this unit.")
        else:
            self._toast("Finish every lesson in this unit to reach this milestone "
                        f"(+{L.XP_UNIT_BONUS} XP).")

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
        self._les = {"ui": ui, "li": li, "steps": steps, "pos": 0, "records": [],
                     "kind": "lesson", "title": les["title"],
                     "correct": 0, "total": sum(
                         1 for i in steps if i["type"] != "info")}
        self._show_step()

    def _start_practice(self, items, title):
        steps = [dict(L.clean_item(i), _first=True) for i in items]
        self._les = {"ui": None, "li": None, "steps": steps, "pos": 0, "records": [],
                     "kind": "practice", "title": title, "correct": 0,
                     "total": len(steps)}
        self._show_step()

    def _show_step(self):
        s = self._les
        if s["pos"] >= len(s["steps"]):
            return self._finish_lesson()
        item = s["steps"][s["pos"]]
        self._clear()
        les = {"title": s["title"]}
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
            # keyboard_suggestions=False: phone keyboards keep the word being typed
            # in a "composing" state that Kivy only sees when the box loses focus
            # (tapping Check), so answers looked untypeable until then
            self._input = TextInput(hint_text="Your answer", multiline=False,
                                    size_hint_y=None, height=dp(44),
                                    keyboard_suggestions=False)
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
        s["records"].append(L.make_record(item, given, ok, bool(item.get("_first"))))
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
        pid = self._plan["id"]
        graded = L.is_graded(st, pid)
        notes = []
        if s["kind"] == "lesson":
            gained = L.record_lesson(st, pid, s["ui"], s["li"], s["correct"], s["total"])
            bonus, notes = L.award_milestones(st, self._plan, s["ui"])
            gained += bonus
        else:
            gained = L.record_practice(st, pid, s["correct"])
        L.note_results(st, pid, s["records"])
        L.save_progress(st)
        summ = L.review_summary(s["records"])
        self._summary = summ
        self._clear()
        pct = summ["pct"]
        head = "Lesson complete!" if s["kind"] == "lesson" else "Practice complete!"
        lines = [f"[b]{head}[/b]", "",
                 f"{len(summ['right'])}/{summ['total']} right first try"
                 + (f" ({pct}%)" if graded else "")]
        if graded:
            lines.append(f"+{gained} XP    Streak {L.current_streak(st)} day(s)")
        else:
            lines.append(f"Streak {L.current_streak(st)} day(s)    (points are off)")
        text = "\n".join(lines) + "".join(
            f"\n\n[color=ffd24d][b]{m}[/b][/color]" for m in notes)
        self._root.add_widget(Label(text=text, markup=True, halign="center", font_size=sp(18)))
        wrong = summ["wrong"]
        self._root.add_widget(_btn(
            f"Review my answers ({len(summ['right'])} right, {len(wrong)} wrong)",
            lambda: self._show_review(summ), h=46, color=ACCENT))
        if wrong:
            items = [r["item"] for r in wrong]
            self._root.add_widget(_btn("Retry the ones I got wrong",
                                       lambda: self._start_practice(items, "Retry"), h=44,
                                       color=BAD))
            from screens import ai_ui
            if ai_ui.is_on("learn"):
                self._root.add_widget(_btn("AI: new questions on my weak spots",
                                           lambda: self._ai_followups(wrong), h=44, color=ACCENT))
        nxt = L.next_lesson(st, self._plan)
        if nxt and s["kind"] == "lesson" and self._plan.get("mode") != "general":
            self._root.add_widget(_btn(
                "Next lesson", lambda: self._start_lesson(*nxt), h=50,
                color=GOOD))
        self._root.add_widget(_btn("Back to course",
                                   lambda: self._show_plan(self._plan)))

    def _ai_followups(self, wrong):
        from screens import ai_ui

        def done(res, err):
            if err:
                return ai_ui.show_error(err)
            self._start_practice(res, "AI follow-up")

        ai_ui.work(lambda: L.ai_followups(self._plan, wrong), done,
                   title="Writing new questions...")

    def _show_review(self, summ):
        self._clear()
        self._root.add_widget(_wrap_label(
            f"[b]Review[/b]   {len(summ['right'])} right, {len(summ['wrong'])} wrong",
            18, markup=True))
        col = self._scroll()
        if not (summ["right"] or summ["wrong"]):
            col.add_widget(_wrap_label("No questions were answered.", 14))
        for r in summ["wrong"] + summ["right"]:
            mark = "[color=ff8c80][b]Wrong[/b][/color]" if not r["ok"] else \
                "[color=80ee90][b]Right[/b][/color]"
            body = f"{mark}  {esc(r['q'])}\nYou answered: {esc(r['given'])}"
            if not r["ok"]:
                body += f"\nCorrect answer: {esc(r['answer'])}"
            if r["explain"]:
                body += f"\n[i]{esc(r['explain'])}[/i]"
            col.add_widget(_wrap_label(body, 14, markup=True))
        self._root.add_widget(_btn("Back", lambda: self._show_plan(self._plan)))
