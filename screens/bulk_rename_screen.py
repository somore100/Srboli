# screens/bulk_rename_screen.py - Bulk Renamer.
# Pick a folder, stack rules (replace, case, numbers, dates, ...), look at the
# live preview (old -> new, problems in red), press Rename. Undo puts the names
# back. The logic is in core/bulk_rename_core.py.

import os
import time

import app_data
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from core import bulk_rename_core as core
from core import theme
from screens.backup_screen import pick_folder
from screens.scaffold import ToolScreen

SHOW_MAX = 200                    # preview rows drawn (the rename itself does all)
GREEN = (0.2, 0.55, 0.2, 1)
RULE_LABELS = [v[0] for v in core.RULES.values()]


def undo_path():
    return os.path.join(app_data.subdir("config"), "bulk_rename_undo.json")


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(6))


class RuleRow(BoxLayout):
    """One step of the chain: a kind, up to two option boxes, a remove button."""

    def __init__(self, screen, op="replace", **kw):
        super().__init__(size_hint_y=None, height=dp(40), spacing=dp(4), **kw)
        self.screen = screen
        self.spin = Spinner(text=core.RULES[op][0], values=RULE_LABELS,
                            font_size=sp(11), size_hint_x=0.4)
        self.a = TextInput(multiline=False, font_size=sp(12), size_hint_x=0.25)
        self.b = TextInput(multiline=False, font_size=sp(12), size_hint_x=0.25)
        rm = Button(text="x", size_hint_x=None, width=dp(34), font_size=sp(13))
        for w in (self.spin, self.a, self.b, rm):
            self.add_widget(w)
        self.spin.bind(text=lambda *a: self._sync())
        self.a.bind(text=lambda *a: screen.changed())
        self.b.bind(text=lambda *a: screen.changed())
        rm.bind(on_release=lambda *a: screen.remove_rule(self))
        self._sync(notify=False)

    @property
    def op(self):
        for k, v in core.RULES.items():
            if v[0] == self.spin.text:
                return k
        return "replace"

    def _sync(self, notify=True):
        fields = core.RULES[self.op][1]
        for box, name in ((self.a, "a"), (self.b, "b")):
            hint = next((h for f, h in fields if f == name), None)
            box.disabled = hint is None
            box.opacity = 1 if hint else 0
            box.hint_text = hint or ""
            if hint is None:
                box.text = ""
        if notify:
            self.screen.changed()

    def rule(self):
        return {"op": self.op, "a": self.a.text, "b": self.b.text}


class BulkRenameScreen(ToolScreen):
    title = "Bulk Renamer"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.folder = ""
        self.plan = []
        self._ev = None
        root = self.body

        r = _row()
        self.folder_lbl = Label(text="No folder chosen", font_size=sp(11),
                                color=theme.MUTED, halign="left", valign="middle",
                                shorten=True, shorten_from="left")
        self.folder_lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        r.add_widget(self.folder_lbl)
        pick = Button(text="Choose folder...", size_hint_x=None, width=dp(130),
                      font_size=sp(12))
        pick.bind(on_release=lambda *a: pick_folder("Folder with the files",
                                                    self.folder, self.set_folder))
        r.add_widget(pick)
        root.add_widget(r)

        r = _row(36)
        self.pattern = TextInput(multiline=False, font_size=sp(12),
                                 hint_text="only these files, e.g. *.jpg *.png (empty = all)")
        self.pattern.bind(text=lambda *a: self.changed())
        r.add_widget(self.pattern)
        self.sort = Spinner(text=core.SORTS["name"], values=list(core.SORTS.values()),
                            font_size=sp(11), size_hint_x=None, width=dp(130))
        self.sort.bind(text=lambda *a: self.changed())
        r.add_widget(self.sort)
        root.add_widget(r)

        self.rules_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                   spacing=dp(4))
        self.rules_box.bind(minimum_height=self.rules_box.setter("height"))
        sv = ScrollView(size_hint_y=0.28, do_scroll_x=False)
        sv.add_widget(self.rules_box)
        root.add_widget(sv)

        r = _row(36)
        add = Button(text="+ Add a rule", font_size=sp(12))
        add.bind(on_release=lambda *a: self.add_rule())
        r.add_widget(add)
        root.add_widget(r)

        self.preview = Label(text="", markup=True, font_size=sp(12), halign="left",
                             valign="top", size_hint_y=None)
        self.preview.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                          texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(8)))
        psv = ScrollView(do_scroll_x=False)
        psv.add_widget(self.preview)
        root.add_widget(psv)

        self.status = Label(text="", font_size=sp(11), color=theme.MUTED,
                            size_hint_y=None, height=dp(34), halign="left",
                            valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(self.status)

        r = _row(42)
        self.go = Button(text="Rename", background_color=GREEN, disabled=True)
        self.go.bind(on_release=lambda *a: self.confirm())
        self.undo_btn = Button(text="Undo last", disabled=True)
        self.undo_btn.bind(on_release=lambda *a: self.undo())
        r.add_widget(self.go)
        r.add_widget(self.undo_btn)
        root.add_widget(r)

        self.add_rule("replace", refresh=False)
        self._sync_undo()

    def on_pre_enter(self, *a):
        self._sync_undo()

    # ── rules ───────────────────────────────────────────────────────────
    def add_rule(self, op="replace", refresh=True):
        self.rules_box.add_widget(RuleRow(self, op))
        if refresh:
            self.changed()

    def remove_rule(self, row):
        self.rules_box.remove_widget(row)
        self.changed()

    def rules(self):
        return [w.rule() for w in reversed(self.rules_box.children)]

    # ── preview ─────────────────────────────────────────────────────────
    def set_folder(self, folder):
        self.folder = folder
        self.folder_lbl.text = folder
        self.refresh()

    def changed(self):
        """Debounced: typing in a box doesn't recompute on every key."""
        if self._ev:
            self._ev.cancel()
        self._ev = Clock.schedule_once(lambda dt: self.refresh(), 0.3)

    def _sort_key(self):
        return next((k for k, v in core.SORTS.items() if v == self.sort.text), "name")

    def refresh(self):
        self._ev = None
        self.plan = []
        self.go.disabled = True
        if not self.folder:
            self.preview.text = ""
            self.status.text = "Choose a folder to start."
            return
        rules = [r for r in self.rules() if self._complete(r)]
        try:
            self.plan = core.build_plan(self.folder, rules, self.pattern.text,
                                        self._sort_key())
        except core.RenameError as e:
            self.preview.text = ""
            self.status.text = str(e)
            return
        n = core.summary(self.plan)
        lines = []
        for p in self.plan[:SHOW_MAX]:
            old, new = _esc(p["old"]), _esc(p["new"])
            if p["status"] == "ok":
                lines.append(f"{old}  [color=7fbf7f]->  {new}[/color]")
            elif p["status"] == "same":
                lines.append(f"[color=888888]{old}  (unchanged)[/color]")
            else:
                lines.append(f"{old}  [color=ff6666]->  {new}   ({_esc(p['why'])})[/color]")
        if len(self.plan) > SHOW_MAX:
            lines.append(f"[color=888888]... and {len(self.plan) - SHOW_MAX} more[/color]")
        self.preview.text = "\n".join(lines) if lines else "No files in this folder match."
        bad = n["conflict"] + n["invalid"]
        self.status.text = (f"{len(self.plan)} files: {n['ok']} will be renamed, "
                            f"{n['same']} unchanged"
                            + (f", {bad} with a problem (fix those first)." if bad else "."))
        self.go.disabled = not n["ok"] or bool(bad)

    @staticmethod
    def _complete(rule):
        """A rule whose required box is still empty is skipped in the preview
        (so half-typed rules don't flash errors)."""
        need = core.RULES[rule["op"]][1]
        if rule["op"] in ("number", "number_front", "date", "date_end", "spaces"):
            return True
        return all(rule.get(f) for f, _h in need[:1])

    # ── do it ───────────────────────────────────────────────────────────
    def confirm(self):
        if not self.plan or self.go.disabled:
            return
        n = core.summary(self.plan)["ok"]
        lay = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        lay.add_widget(Label(text=f"Rename {n} file{'s' if n != 1 else ''}?\n"
                                  "You can undo it afterwards.", font_size=sp(13)))
        row = _row(42)
        yes = Button(text="Rename", background_color=GREEN)
        no = Button(text="Cancel")
        row.add_widget(yes)
        row.add_widget(no)
        lay.add_widget(row)
        pop = Popup(title="Bulk rename", content=lay, size_hint=(0.8, 0.32))
        yes.bind(on_release=lambda *a: (pop.dismiss(), self.do_rename()))
        no.bind(on_release=lambda *a: pop.dismiss())
        pop.open()

    def do_rename(self):
        try:
            # rebuild so nothing that changed since the preview is trusted
            rules = [r for r in self.rules() if self._complete(r)]
            plan = core.build_plan(self.folder, rules, self.pattern.text,
                                   self._sort_key())
            n = core.apply_plan(plan, undo_path())
        except core.RenameError as e:
            self.status.text = str(e)
            self.refresh()
            return
        self.refresh()
        self.status.text = f"Renamed {n} file{'s' if n != 1 else ''}. Undo is available."
        self._sync_undo()

    def undo(self):
        try:
            n = core.undo_last(undo_path())
        except core.RenameError as e:
            self.status.text = str(e)
            return
        self.refresh()
        self.status.text = f"Put {n} name{'s' if n != 1 else ''} back."
        self._sync_undo()

    def _sync_undo(self):
        info = core.undo_info(undo_path())
        self.undo_btn.disabled = info is None
        self.undo_btn.text = ("Undo last" if info is None else
                              f"Undo last ({info[0]} files, "
                              f"{time.strftime('%H:%M', time.localtime(info[1]))})")


def _esc(s):
    return s.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")
