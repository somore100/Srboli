# screens/reminders_screen.py — Reminders / to-do list.
#
# The UI half of Phase 1. The actual scheduling logic (what's due, what
# "daily"/"weekly" mean, how "overdue" is decided) lives in
# core/reminders_core.py and is shared with the daemon's scheduler — this
# screen is just CRUD on reminders.json plus a popup for building one.
#
# A reminder with no due date is a plain to-do (checkbox, no time). One
# with a due date fires a background notification if the daemon is
# running; if it isn't, the reminder just waits — it'll be caught up
# (fired once, even if overdue) the next time the daemon starts.

import datetime
import random

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.clock import Clock

import core.reminders_core as rc
from core.daemon_ipc import send_command

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _nudge_daemon():
    """Best-effort — fine if the daemon isn't running; it'll pick up the
    change from disk on its own next tick regardless."""
    import threading
    threading.Thread(target=lambda: send_command("reload", timeout=1.0),
                     daemon=True).start()


class ReminderRow(BoxLayout):
    """One row in the list: checkbox (to-dos / one-time only), title +
    due description, Edit, Delete."""

    def __init__(self, reminder, on_toggle_done, on_toggle_enabled,
                on_edit, on_delete, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(52))
        super().__init__(spacing=6, padding=(4, 2), **kw)
        self.reminder = reminder

        with self.canvas.before:
            Color(0.14, 0.14, 0.17, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        can_check = reminder.get("due") is None or reminder.get("repeat", "none") == "none"
        if can_check:
            cb = CheckBox(active=bool(reminder.get("done")),
                         size_hint=(None, None), size=(dp(28), dp(28)))
            cb.bind(active=lambda inst, val: on_toggle_done(reminder, val))
            self.add_widget(cb)
        else:
            self.add_widget(Widget(size_hint=(None, None), size=(dp(28), dp(28))))

        info = BoxLayout(orientation="vertical")
        title_color = (0.5, 0.5, 0.5, 1) if reminder.get("done") else (1, 1, 1, 1)
        title = Label(text=reminder.get("title", "(untitled)"), font_size=14,
                      halign="left", valign="middle", color=title_color,
                      strikethrough=bool(reminder.get("done")))
        title.bind(size=lambda i, s: setattr(i, "text_size", s))
        info.add_widget(title)

        self._desc = Label(text="", font_size=11, halign="left", valign="middle")
        self._desc.bind(size=lambda i, s: setattr(i, "text_size", s))
        info.add_widget(self._desc)
        self.add_widget(info)
        self.refresh_description()

        if reminder.get("due") is not None:
            pause_btn = ToggleButton(
                text="Pause" if reminder.get("enabled", True) else "Resume",
                state="down" if not reminder.get("enabled", True) else "normal",
                size_hint_x=None, width=dp(64), font_size=11)
            pause_btn.bind(on_release=lambda inst: on_toggle_enabled(
                reminder, inst.state != "down"))
            self.add_widget(pause_btn)

        edit_btn = Button(text="Edit", size_hint_x=None, width=dp(52), font_size=11)
        edit_btn.bind(on_release=lambda *a: on_edit(reminder))
        self.add_widget(edit_btn)

        del_btn = Button(text="X", size_hint_x=None, width=dp(36), font_size=13,
                         background_color=(0.5, 0.2, 0.2, 1))
        del_btn.bind(on_release=lambda *a: on_delete(reminder))
        self.add_widget(del_btn)

    def _sync_bg(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def refresh_description(self):
        """Recompute the "Today 14:30" / "Overdue" / "(paused)" line
        without rebuilding the row — called on a timer so those labels
        stay current, and rebuilding the whole list every 30s would
        drop scroll position and risk detaching a widget mid-touch."""
        desc_text = rc.describe_next(self.reminder)
        if desc_text.startswith("Overdue"):
            self._desc.color = (0.95, 0.55, 0.3, 1)
        else:
            self._desc.color = (0.65, 0.65, 0.65, 1)
        if not self.reminder.get("enabled", True):
            desc_text += "  (paused)"
        self._desc.text = desc_text


class ReminderEditPopup(Popup):
    """Add or edit one reminder. Dates/times are plain text fields
    (YYYY-MM-DD / HH:MM) — no native date picker in this toolkit, but
    "Today"/"Tomorrow" quick-fill buttons cover the common case."""

    def __init__(self, on_save, existing=None, **kw):
        kw.setdefault("title", "Edit reminder" if existing else "New reminder")
        kw.setdefault("size_hint", (0.92, 0.9))
        super().__init__(**kw)
        self.on_save = on_save
        self.existing = existing
        now = datetime.datetime.now()

        due_dt = None
        if existing and existing.get("due"):
            try:
                due_dt = datetime.datetime.fromisoformat(existing["due"])
            except ValueError:
                pass

        # Scrollable form: on a phone (or with the keyboard up) the fields are
        # taller than the popup, so they scroll; Cancel/Save stay pinned.
        form = BoxLayout(orientation="vertical", spacing=6, padding=4,
                         size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        form.add_widget(Label(text="Title", size_hint_y=None, height=dp(20),
                              halign="left", font_size=12))
        self.title_in = TextInput(text=(existing or {}).get("title", ""),
                                  multiline=False, size_hint_y=None,
                                  height=dp(44), font_size=14)
        form.add_widget(self.title_in)

        form.add_widget(Label(text="Notes (optional — shown in the notification)",
                              size_hint_y=None, height=dp(20), halign="left",
                              font_size=12))
        self.notes_in = TextInput(text=(existing or {}).get("notes", ""),
                                  multiline=True, size_hint_y=None,
                                  height=dp(56), font_size=13)
        form.add_widget(self.notes_in)

        due_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        self.due_cb = CheckBox(active=due_dt is not None,
                               size_hint=(None, None), size=(dp(28), dp(28)))
        self.due_cb.bind(active=self._on_due_toggle)
        due_row.add_widget(self.due_cb)
        due_row.add_widget(Label(text="Remind me at a specific time",
                                 font_size=12, halign="left"))
        form.add_widget(due_row)

        self.datetime_box = BoxLayout(size_hint_y=None, height=dp(44), spacing=4)
        self.date_in = TextInput(
            text=(due_dt or now).strftime("%Y-%m-%d"), multiline=False,
            size_hint_x=0.4, font_size=13, hint_text="YYYY-MM-DD")
        self.time_in = TextInput(
            text=(due_dt or now.replace(minute=(now.minute // 5) * 5)).strftime("%H:%M"),
            multiline=False, size_hint_x=0.25, font_size=13, hint_text="HH:MM")
        today_btn = Button(text="Today", size_hint_x=0.17, font_size=11)
        tmr_btn = Button(text="Tomorrow", size_hint_x=0.18, font_size=11)
        today_btn.bind(on_release=lambda *a: setattr(
            self.date_in, "text", datetime.date.today().strftime("%Y-%m-%d")))
        tmr_btn.bind(on_release=lambda *a: setattr(
            self.date_in, "text",
            (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")))
        self.datetime_box.add_widget(self.date_in)
        self.datetime_box.add_widget(self.time_in)
        self.datetime_box.add_widget(today_btn)
        self.datetime_box.add_widget(tmr_btn)
        form.add_widget(self.datetime_box)

        rnd_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=6)
        self.rnd_sp = Spinner(text="within 3 h", size_hint_x=0.38, font_size=12,
                              values=("within 1 h", "within 3 h",
                                      "within 12 h", "within 24 h"))
        rnd_btn = Button(text="Remind me at a random time", font_size=12)
        rnd_btn.bind(on_release=self._pick_random)
        rnd_row.add_widget(rnd_btn)
        rnd_row.add_widget(self.rnd_sp)
        form.add_widget(rnd_row)

        repeat_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        repeat_row.add_widget(Label(text="Repeat", size_hint_x=None,
                                    width=dp(60), font_size=12))
        self.repeat_sp = Spinner(
            text={"none": "Never", "daily": "Daily",
                 "weekly": "Weekly"}.get((existing or {}).get("repeat", "none"), "Never"),
            values=("Never", "Daily", "Weekly"), font_size=12)
        self.repeat_sp.bind(text=self._on_repeat_change)
        repeat_row.add_widget(self.repeat_sp)
        form.add_widget(repeat_row)

        self.weekday_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=4)
        existing_days = set((existing or {}).get("weekdays", []) or [due_dt.weekday()] if due_dt else [])
        self.day_buttons = []
        for i, lbl in enumerate(_WEEKDAY_LABELS):
            b = ToggleButton(text=lbl, font_size=11,
                             state="down" if i in existing_days else "normal")
            self.day_buttons.append(b)
            self.weekday_row.add_widget(b)
        form.add_widget(self.weekday_row)

        self.error_lbl = Label(text="", font_size=12, color=(1, 0.5, 0.5, 1),
                               size_hint_y=None, height=dp(20))
        form.add_widget(self.error_lbl)

        
        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
        cancel_btn = Button(text="Cancel", font_size=13)
        save_btn = Button(text="Save", font_size=13,
                          background_color=(0.2, 0.5, 0.25, 1))
        cancel_btn.bind(on_release=lambda *a: self.dismiss())
        save_btn.bind(on_release=self._save)
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(save_btn)
        outer = BoxLayout(orientation="vertical", spacing=6, padding=8)
        sv = ScrollView(do_scroll_x=False)
        sv.add_widget(form)
        outer.add_widget(sv)
        outer.add_widget(btn_row)


        # Same fix as Script Mode: tapping a Spinner while a TextInput holds
        # focus lets the keyboard-dismiss resize close the dropdown. Drop
        # focus first.
        def _defocus(widget, touch):
            if widget.collide_point(*touch.pos):
                for ti in (self.title_in, self.notes_in, self.date_in, self.time_in):
                    ti.focus = False
            return False
        self.repeat_sp.bind(on_touch_down=_defocus)
        self.rnd_sp.bind(on_touch_down=_defocus)

        self.content = outer
        self._on_due_toggle(self.due_cb, self.due_cb.active)
        self._on_repeat_change(self.repeat_sp, self.repeat_sp.text)

    def _pick_random(self, *a):
        """Fill the date/time with a random moment in the chosen window and
        switch 'remind at a specific time' on."""
        hours = int(self.rnd_sp.text.split()[1])
        when = (datetime.datetime.now()
                + datetime.timedelta(minutes=random.randint(1, hours * 60)))
        self.due_cb.active = True
        self.date_in.text = when.strftime("%Y-%m-%d")
        self.time_in.text = when.strftime("%H:%M")
        self.error_lbl.text = f"Random time picked: {when.strftime('%H:%M')}"

    def _on_due_toggle(self, cb, active):
        self.datetime_box.disabled = not active
        self.datetime_box.opacity = 1 if active else 0.4
        if not active:
            self.repeat_sp.text = "Never"
        self.repeat_sp.disabled = not active

    def _on_repeat_change(self, spinner, text):
        show_days = (text == "Weekly")
        self.weekday_row.disabled = not show_days
        self.weekday_row.opacity = 1 if show_days else 0.25

    def _save(self, *a):
        title = self.title_in.text.strip()
        if not title:
            self.error_lbl.text = "Please enter a title."
            return

        due = None
        repeat = "none"
        weekdays = []
        if self.due_cb.active:
            try:
                date_part = datetime.datetime.strptime(
                    self.date_in.text.strip(), "%Y-%m-%d").date()
                time_part = datetime.datetime.strptime(
                    self.time_in.text.strip(), "%H:%M").time()
            except ValueError:
                self.error_lbl.text = "Date must be YYYY-MM-DD, time must be HH:MM."
                return
            due = datetime.datetime.combine(date_part, time_part).isoformat(
                timespec="seconds")
            repeat = {"Never": "none", "Daily": "daily",
                     "Weekly": "weekly"}[self.repeat_sp.text]
            if repeat == "weekly":
                weekdays = [i for i, b in enumerate(self.day_buttons)
                           if b.state == "down"]
                if not weekdays:
                    self.error_lbl.text = "Pick at least one day for a weekly reminder."
                    return

        if self.existing:
            r = dict(self.existing)
            r.update(title=title, notes=self.notes_in.text.strip(),
                    due=due, repeat=repeat, weekdays=weekdays)
        else:
            r = rc.new_reminder(title, due=due, repeat=repeat,
                               weekdays=weekdays, notes=self.notes_in.text.strip())
        self.dismiss()
        self.on_save(r)


class RemindersScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._reminders = []

        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        header = BoxLayout(size_hint_y=None, height=dp(44))
        header.add_widget(Label(text="[b]Reminders[/b]", markup=True,
                                font_size=20, halign="left", valign="middle"))
        new_btn = Button(text="+ New", size_hint_x=None, width=dp(76), font_size=13,
                         background_color=(0.2, 0.5, 0.25, 1))
        new_btn.bind(on_release=lambda *a: self._open_editor(None))
        header.add_widget(new_btn)
        root.add_widget(header)

        self._empty_lbl = Label(
            text="Nothing here yet. \"+ New\" adds a to-do, or a reminder "
                 "with a time. On desktop the background service (see Settings) "
                 "notifies you even if Srboli is closed; on Android reminders "
                 "fire while the app is open or running in the background.",
            font_size=12, color=(0.6, 0.6, 0.6, 1), halign="center",
            valign="middle")
        root.add_widget(self._empty_lbl)

        sv = ScrollView()
        self._list = GridLayout(cols=1, size_hint_y=None, spacing=4)
        self._list.bind(minimum_height=self._list.setter("height"))
        sv.add_widget(self._list)
        root.add_widget(sv)

        back = Button(text="< Back", size_hint_y=None, height=dp(42))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    def on_enter(self, *a):
        self._reload()
        # keep "Overdue" / "Today" / "Tomorrow" labels fresh without
        # requiring the person to leave and re-enter the screen
        self._tick_ev = Clock.schedule_interval(lambda dt: self._refresh_labels(), 30)

    def on_leave(self, *a):
        ev = getattr(self, "_tick_ev", None)
        if ev:
            ev.cancel()

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"

    # -- data --------------------------------------------------------------
    def _reload(self):
        self._reminders = rc.load_reminders()
        self._render()

    def _save(self):
        rc.save_reminders(self._reminders)
        _nudge_daemon()

    def _render(self):
        self._list.clear_widgets()
        now = datetime.datetime.now()
        ordered = sorted(self._reminders, key=lambda r: rc.sort_key(r, now))
        if ordered:
            self._empty_lbl.opacity = 0
            self._empty_lbl.size_hint_y = None
            self._empty_lbl.height = 0
        else:
            self._empty_lbl.opacity = 1
            self._empty_lbl.size_hint_y = 1
            self._empty_lbl.height = 0        # size_hint_y=1 overrides this anyway
        for r in ordered:
            self._list.add_widget(ReminderRow(
                r, on_toggle_done=self._toggle_done,
                on_toggle_enabled=self._toggle_enabled,
                on_edit=self._open_editor, on_delete=self._delete))

    def _refresh_labels(self):
        # cosmetic-only tick: update each row's due-description text in
        # place. Never tears down/rebuilds the list, so it can't yank a
        # widget out from under an in-flight touch or reset the scroll
        # position while someone's looking at it.
        for row in self._list.children:
            if hasattr(row, "refresh_description"):
                row.refresh_description()

    def _find(self, reminder):
        for i, r in enumerate(self._reminders):
            if r["id"] == reminder["id"]:
                return i
        return None

    def _toggle_done(self, reminder, value):
        i = self._find(reminder)
        if i is not None:
            self._reminders[i]["done"] = bool(value)
            self._save()
            self._render()

    def _toggle_enabled(self, reminder, value):
        i = self._find(reminder)
        if i is not None:
            self._reminders[i]["enabled"] = bool(value)
            self._save()
            self._render()

    def _open_editor(self, reminder):
        ReminderEditPopup(on_save=self._on_editor_save, existing=reminder).open()

    def _on_editor_save(self, reminder):
        i = self._find(reminder)
        if i is not None:
            self._reminders[i] = reminder
        else:
            self._reminders.append(reminder)
        self._save()
        self._render()

    def _delete(self, reminder):
        i = self._find(reminder)
        if i is not None:
            del self._reminders[i]
            self._save()
            self._render()
