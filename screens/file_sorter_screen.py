# screens/file_sorter_screen.py
#
# Rule-based file sorter. A "rule" = one or more conditions (extension,
# name, size, date modified/created, image metadata) combined with
# AND/OR, plus an action (move/copy/rename/delete).
#
# Conflict handling (multiple rules matching the same file): each rule
# has a "continue after match" toggle. Default OFF = classic first-match-
# wins (stop evaluating once this rule hits). Turn it ON for a rule and
# evaluation keeps going to the next rule too, so you get "apply all"
# behaviour exactly where you ask for it, rule by rule, rather than one
# global all-or-nothing switch.
#
# Actions chain in order against the SAME file: if rule 1 renames and
# rule 2 (continue=on) also matches, rule 2 acts on the renamed file. If
# a rule deletes the file, any further matched rules for that file are
# skipped (nothing left to act on) and this is logged, not silently
# dropped.
#
# Always run "Preview" before "Apply" — Apply is disabled until a preview
# has been generated against the current rules + folder, since actions
# here (move/delete especially) aren't easily undoable.

import os, json, time, threading
from core.jsonio import read_json, write_json_atomic

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.utils import platform as _platform

# The engine (rule matching, plan building, applying an action to a file)
# lives in core/file_sorter_core.py, Kivy-free, so the headless --daemon
# folder watcher can use the exact same code this screen does. This
# screen only adds the UI on top.
from core.file_sorter_core import (
    FIELDS, FIELD_ORDER, FIELD_LABELS,
    FILE_TYPE_NAMES, ACTION_TYPES, ACTION_LABELS,
    LAST_USED_KEY, STABLE_POLL_INTERVAL, SETTLE_SECONDS, APPLY_MAX_WAIT,
    HAS_SEND2TRASH,
    _home, _rulesets_dir, _fmt_size,
    save_ruleset, load_ruleset, list_rulesets,
    export_ruleset_to_path, import_ruleset_from_path,
    build_plan, wait_for_stable_file, apply_action, clear_meta_cache,
    rule_one_liner, rule_title, auto_rule_name, condition_problem,
)
from core import file_safety


class ConditionRow(BoxLayout):
    def __init__(self, on_remove, initial=None, **kw):
        super().__init__(orientation="vertical", size_hint_y=None,
                         height=dp(78), spacing=4, **kw)
        initial = initial or {}
        top = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)

        self.field_sp = Spinner(
            text=FIELD_LABELS.get(initial.get("field", "file_type"), "File type"),
            values=[FIELD_LABELS[k] for k in FIELD_ORDER], font_size=sp(13))
        self.field_sp.bind(text=lambda *a: self._rebuild_value_row())
        top.add_widget(self.field_sp)

        rm = Button(text="x", size_hint_x=None, width=dp(36))
        rm.bind(on_release=lambda *a: on_remove(self))
        top.add_widget(rm)
        self.add_widget(top)

        self._value_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        self.add_widget(self._value_row)

        self._init_op = initial.get("op")
        self._init_value = initial.get("value", "")
        self._rebuild_value_row()

    def _field_key(self):
        label = self.field_sp.text
        for k, v in FIELD_LABELS.items():
            if v == label:
                return k
        return "extension"

    def _rebuild_value_row(self):
        self._value_row.clear_widgets()
        field = self._field_key()
        spec = FIELDS[field]
        ops = spec["ops"]
        op_text = self._init_op if self._init_op in ops else ops[0]
        self._init_op = None  # only honor initial value on first build
        self.op_sp = Spinner(text=op_text, values=ops, font_size=sp(13),
                             size_hint_x=0.45)
        self._value_row.add_widget(self.op_sp)

        kind = spec["kind"]
        if kind == "bool":
            self.value_input = None
            self._value_row.add_widget(Label(text="(no value needed)",
                                             font_size=sp(12), color=(0.6,0.6,0.6,1)))
        elif kind == "category":
            init = self._init_value if self._init_value in FILE_TYPE_NAMES else FILE_TYPE_NAMES[0]
            self.value_input = Spinner(text=init, values=FILE_TYPE_NAMES,
                                       font_size=sp(13), size_hint_x=0.55)
            self._value_row.add_widget(self.value_input)
        else:
            hint = {"text_list": "jpg, png, mp4", "text": "text or pattern",
                    "size": "e.g. 500MB or 1GB", "days": "e.g. 30"}.get(kind, "")
            self.value_input = TextInput(text=self._init_value or "",
                                         hint_text=hint, multiline=False,
                                         font_size=sp(13), size_hint_x=0.55)
            self._value_row.add_widget(self.value_input)
        self._init_value = ""

    def get_condition(self):
        return {
            "field": self._field_key(),
            "op": self.op_sp.text,
            "value": self.value_input.text if self.value_input else "",
        }


# ── rule editor popup ────────────────────────────────────────────────────
class RuleEditorPopup(Popup):
    NO_GROUP = "(none)"
    NEW_GROUP = "+ New group..."

    def __init__(self, on_save, existing=None, existing_groups=None, **kw):
        super().__init__(title="Rule Editor", size_hint=(None, None), **kw)
        self._on_save = on_save
        existing = existing or {}
        self._existing = existing
        self._condition_rows = []
        existing_groups = sorted(g for g in (existing_groups or []) if g)
        self._fit()
        Window.bind(size=self._fit)

        outer = BoxLayout(orientation="vertical", padding=8, spacing=6)
        # Everything but the Save/Cancel buttons scrolls, so nothing is ever
        # squeezed or cut off on a small screen, and there is no dead space
        # on a big one.
        sv = ScrollView(do_scroll_x=False, bar_width=dp(6))
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=8,
                         padding=(0, 0, dp(8), 0))
        form.bind(minimum_height=form.setter("height"))
        sv.add_widget(form)
        outer.add_widget(sv)

        # Name: optional. Left empty, the rule is named after itself.
        name_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        name_row.add_widget(Label(text="Rule name:", size_hint_x=None,
                                  width=dp(96), font_size=sp(13)))
        had_custom = bool(existing.get("name")) and not existing.get("auto_name")
        self.name_input = TextInput(
            text=existing.get("name", "") if had_custom else "",
            hint_text="(optional)", multiline=False, font_size=sp(13))
        name_row.add_widget(self.name_input)
        form.add_widget(name_row)
        self._auto_lbl = Label(font_size=sp(11), halign="left", valign="top",
                               size_hint_y=None, height=dp(32),
                               color=(0.6, 0.8, 0.6, 1))
        self._auto_lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        form.add_widget(self._auto_lbl)

        # Group: purely organizational (doesn't affect evaluation order
        # or matching).
        group_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        group_row.add_widget(Label(text="Group:", size_hint_x=None,
                                   width=dp(96), font_size=sp(13)))
        NEW_GROUP = self.NEW_GROUP
        NO_GROUP = self.NO_GROUP
        current_group = existing.get("group", "") or NO_GROUP
        known = [NO_GROUP] + existing_groups
        if current_group not in known:
            known.append(current_group)
        spinner_values = known + [NEW_GROUP]

        self.group_sp = Spinner(text=current_group, values=spinner_values,
                                font_size=sp(13), size_hint_x=0.45)
        self.group_new_input = TextInput(
            hint_text="new group name", multiline=False, font_size=sp(13),
            size_hint_x=0.55)
        self.group_new_input.opacity = 0
        self.group_new_input.disabled = True

        def _on_group_change(*a):
            show_new = self.group_sp.text == NEW_GROUP
            self.group_new_input.opacity = 1 if show_new else 0
            self.group_new_input.disabled = not show_new
            if show_new:
                self.group_new_input.text = ""

        self.group_sp.bind(text=_on_group_change)
        group_row.add_widget(self.group_sp)
        group_row.add_widget(self.group_new_input)
        form.add_widget(group_row)

        # "IF" section - one or more conditions, combined with AND/OR.
        if_header = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
        if_header.add_widget(Label(text="[b]IF[/b]", markup=True,
                                   size_hint_x=None, width=dp(30),
                                   font_size=sp(15), color=(0.6, 0.85, 1, 1)))
        self.logic_sp = Spinner(text=existing.get("logic", "AND"),
                                values=["AND", "OR"], font_size=sp(13),
                                size_hint_x=None, width=dp(70))
        if_header.add_widget(self.logic_sp)
        self._if_note = Label(font_size=sp(12), halign="left", color=(0.6, 0.6, 0.6, 1))
        self._if_note.bind(size=self._if_note.setter("text_size"))

        def _update_if_note(*a):
            self._if_note.text = (
                "of these match (all must be true):" if self.logic_sp.text == "AND"
                else "of these match (any one is enough):")

        self.logic_sp.bind(text=_update_if_note)
        _update_if_note()
        if_header.add_widget(self._if_note)
        form.add_widget(if_header)

        self._cond_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                   spacing=6)
        self._cond_box.bind(minimum_height=self._cond_box.setter("height"))
        form.add_widget(self._cond_box)

        add_cond_btn = Button(text="+ Add condition", size_hint_y=None,
                              height=dp(36), font_size=sp(13))
        add_cond_btn.bind(on_release=lambda *a: self._add_condition())
        form.add_widget(add_cond_btn)

        for c in existing.get("conditions") or [{}]:
            self._add_condition(c)

        then_header = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
        then_header.add_widget(Label(text="[b]THEN[/b]", markup=True,
                                     size_hint_x=None, width=dp(50),
                                     font_size=sp(15), color=(1, 0.8, 0.5, 1)))
        action = existing.get("action", {"type": "move"})
        self.action_sp = Spinner(text=ACTION_LABELS[action.get("type", "move")],
                                 values=[ACTION_LABELS[t] for t in ACTION_TYPES],
                                 font_size=sp(13))
        self.action_sp.bind(text=lambda *a: self._rebuild_action_row())
        then_header.add_widget(self.action_sp)
        form.add_widget(then_header)

        self._action_row = BoxLayout(size_hint_y=None, height=dp(100), spacing=4)
        form.add_widget(self._action_row)
        self._init_action = action
        self._rebuild_action_row()

        self.continue_cb = CheckBox(active=existing.get("continue_after_match", False),
                                    size_hint=(None, None), size=(dp(24), dp(24)))
        cont_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        cont_row.add_widget(self.continue_cb)
        cont_lbl = Label(text="Keep checking later rules too (off = stop "
                              "here once this rule matches)",
                         font_size=sp(12), halign="left")
        cont_lbl.bind(size=cont_lbl.setter("text_size"))
        cont_row.add_widget(cont_lbl)
        form.add_widget(cont_row)

        btn_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=6)
        save_btn = Button(text="Save Rule")
        save_btn.bind(on_release=self._save)
        cancel_btn = Button(text="Cancel")
        cancel_btn.bind(on_release=lambda *a: self.dismiss())
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        outer.add_widget(btn_row)

        self.content = outer
        self._auto_ev = Clock.schedule_interval(self._refresh_auto, 0.4)
        self._refresh_auto()

    def _fit(self, *a):
        """Whole-pixel size and position: a popup that lands on half pixels
        draws every label and input soft."""
        W, H = Window.size
        mx, my = int(round(W * 0.03)), int(round(H * 0.04))
        self.size = (W - 2 * mx, H - 2 * my)

    def on_dismiss(self):
        try:
            self._auto_ev.cancel()
            Window.unbind(size=self._fit)
        except Exception:
            pass

    # what the rule looks like right now (nothing validated)
    def _draft(self):
        kind = self._action_key()
        if kind in ("move", "copy"):
            action = {"type": kind, "dest": getattr(self, "_dest_path", "")}
        elif kind == "rename":
            action = {"type": "rename",
                      "pattern": self._rename_input.text.strip() or "{name}{ext}"}
        else:
            action = {"type": "delete",
                      "auto_delete": self.auto_delete_cb.active}
        return {"logic": self.logic_sp.text,
                "conditions": [r.get_condition() for r in self._condition_rows],
                "action": action}

    def _refresh_auto(self, *a):
        try:
            auto = auto_rule_name(self._draft())
        except Exception:
            return
        if self.name_input.text.strip():
            self._auto_lbl.text = ""
        else:
            self._auto_lbl.text = "Left empty, it will be named:\n" + auto

    def _add_condition(self, initial=None):
        if initial is None:
            # a new condition starts on a field no other row uses, so adding
            # one never creates an identical copy by accident
            used = {r._field_key() for r in self._condition_rows}
            free = [k for k in FIELD_ORDER if k not in used]
            initial = {"field": free[0]} if free else {}
        row = ConditionRow(on_remove=self._remove_condition, initial=initial)
        self._condition_rows.append(row)
        self._cond_box.add_widget(row)

    def _remove_condition(self, row):
        if len(self._condition_rows) <= 1:
            return  # keep at least one condition
        self._condition_rows.remove(row)
        self._cond_box.remove_widget(row)

    def _action_key(self):
        label = self.action_sp.text
        for k, v in ACTION_LABELS.items():
            if v == label:
                return k
        return "move"

    def _rebuild_action_row(self):
        self._action_row.clear_widgets()
        kind = self._action_key()
        init = self._init_action if self._init_action.get("type") == kind else {}
        self._init_action = {}
        self._action_row.height = dp(100)

        if kind in ("move", "copy"):
            col = BoxLayout(orientation="vertical", spacing=4)
            self._dest_path = init.get("dest", "")
            to_row = BoxLayout(size_hint_y=None, height=dp(22), spacing=4)
            to_row.add_widget(Label(text="[b]TO[/b]", markup=True,
                                    size_hint_x=None, width=dp(30),
                                    font_size=sp(13), color=(0.7, 1, 0.7, 1)))
            to_row.add_widget(Label(text="this folder:", font_size=sp(12),
                                    halign="left", color=(0.6, 0.6, 0.6, 1)))
            col.add_widget(to_row)
            btn = Button(text="Pick destination folder...", size_hint_y=None,
                         height=dp(38), font_size=sp(13))
            lbl = Label(text=self._dest_path or "(none chosen)", font_size=sp(11),
                       halign="left", color=(0.7, 0.9, 0.7, 1),
                       size_hint_y=None, height=dp(26))
            lbl.bind(size=lbl.setter("text_size"))
            self._dest_lbl = lbl

            def _pick(*a):
                chooser = FileChooserIconView(path=self._dest_path or _home(),
                                              dirselect=True)
                pick_btn = Button(text="Use this folder", size_hint_y=None,
                                  height=dp(44))
                lay = BoxLayout(orientation="vertical")
                lay.add_widget(chooser)
                lay.add_widget(pick_btn)
                popup = Popup(title="Choose destination", content=lay,
                             size_hint=(0.9, 0.9))

                def _use(*b):
                    folder = (chooser.selection[0] if chooser.selection
                             else chooser.path)
                    self._dest_path = folder
                    self._dest_lbl.text = folder
                    popup.dismiss()

                pick_btn.bind(on_release=_use)
                popup.open()

            btn.bind(on_release=_pick)
            col.add_widget(btn)
            col.add_widget(lbl)
            self._action_row.add_widget(col)

        elif kind == "rename":
            col = BoxLayout(orientation="vertical", spacing=4)
            to_row = BoxLayout(size_hint_y=None, height=dp(22), spacing=4)
            to_row.add_widget(Label(text="[b]TO[/b]", markup=True,
                                    size_hint_x=None, width=dp(30),
                                    font_size=sp(13), color=(0.7, 1, 0.7, 1)))
            to_row.add_widget(Label(text="this name pattern:", font_size=sp(12),
                                    halign="left", color=(0.6, 0.6, 0.6, 1)))
            col.add_widget(to_row)
            self._rename_input = TextInput(
                text=init.get("pattern", "{name}{ext}"), multiline=False,
                font_size=sp(13), size_hint_y=None, height=dp(36))
            col.add_widget(self._rename_input)
            hint = Label(text="Tokens: {name} {ext} {counter} {date}  "
                              "({ext} already includes the leading dot)",
                        font_size=sp(11), color=(0.6, 0.6, 0.6, 1),
                        size_hint_y=None, height=dp(26))
            col.add_widget(hint)
            self._action_row.add_widget(col)

        elif kind == "delete":
            self._action_row.height = dp(80)
            col = BoxLayout(orientation="vertical", spacing=4)
            warn = Label(
                text=("Sends to recycle bin/trash." if HAS_SEND2TRASH else
                     "PERMANENT delete - send2trash not installed, "
                     "there is no recycle bin fallback."),
                font_size=sp(12), halign="left",
                color=(0.7, 0.9, 0.7, 1) if HAS_SEND2TRASH else (1, 0.5, 0.4, 1))
            warn.bind(size=warn.setter("text_size"))
            col.add_widget(warn)

            auto_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
            self.auto_delete_cb = CheckBox(
                active=init.get("auto_delete", False),
                size_hint=(None, None), size=(dp(24), dp(24)))
            auto_row.add_widget(self.auto_delete_cb)
            auto_lbl = Label(
                text="Auto-delete, no confirmation each time (off = "
                    "ask before every delete, like the OS trash does)",
                font_size=sp(11), halign="left", color=(0.75, 0.75, 0.5, 1))
            auto_lbl.bind(size=auto_lbl.setter("text_size"))
            auto_row.add_widget(auto_lbl)
            col.add_widget(auto_row)
            self._action_row.add_widget(col)

    def _save(self, *a):
        conditions = [row.get_condition() for row in self._condition_rows]
        problem = condition_problem(conditions, self.logic_sp.text)
        if problem:
            self._flash_error(problem)
            return
        draft = self._draft()
        action = draft["action"]
        if action["type"] in ("move", "copy") and not action.get("dest"):
            self._flash_error("Pick a destination folder first.")
            return

        if self.group_sp.text == self.NEW_GROUP:
            group = self.group_new_input.text.strip()
        elif self.group_sp.text == self.NO_GROUP:
            group = ""
        else:
            group = self.group_sp.text

        rule = {
            "name": self.name_input.text.strip(),
            "group": group,
            "enabled": self._existing.get("enabled", True),
            "logic": draft["logic"],
            "conditions": conditions,
            "action": action,
            "continue_after_match": self.continue_cb.active,
        }
        if not rule["name"]:
            rule["name"] = auto_rule_name(rule)
            rule["auto_name"] = True
        self._on_save(rule)
        self.dismiss()

    def _flash_error(self, msg):
        lbl = Label(text=msg, font_size=sp(13), halign="center")
        lbl.bind(width=lambda w, v: setattr(w, "text_size", (v - 20, None)))
        Popup(title="Check the rule", content=lbl,
              size_hint=(0.7, 0.35)).open()


# ── main screen ──────────────────────────────────────────────────────────
class FileSorterScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._rules = []
        self._source_folder = ""
        self._plan = None       # last computed preview plan
        self._plan_stale = True
        self._busy = False
        self._stop_requested = False

        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        root.add_widget(Label(text="[b]File Sorter[/b] (rule-based)",
                              markup=True, font_size=sp(18), size_hint_y=None,
                              height=dp(30)))

        # rules list
        root.add_widget(Label(text="Rules (evaluated top to bottom):",
                              size_hint_y=None, height=dp(20), font_size=sp(12)))

        filter_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=6)
        filter_row.add_widget(Label(text="Show group:", size_hint_x=None,
                                    width=dp(90), font_size=sp(11)))
        self._group_filter_sp = Spinner(text="All groups", values=["All groups"],
                                        font_size=sp(11), size_hint_x=0.5)
        self._group_filter_sp.bind(text=lambda *a: self._refresh_rules_list())
        filter_row.add_widget(self._group_filter_sp)
        note = Label(text="(Up/Down move a rule's real evaluation position, "
                          "even while filtered)", font_size=sp(9),
                     color=(0.55, 0.55, 0.55, 1), halign="left")
        note.bind(size=note.setter("text_size"))
        filter_row.add_widget(note)
        root.add_widget(filter_row)

        rules_sv = ScrollView(size_hint_y=0.42)
        self._rules_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                    spacing=3)
        self._rules_box.bind(minimum_height=self._rules_box.setter("height"))
        rules_sv.add_widget(self._rules_box)
        root.add_widget(rules_sv)

        add_rule_btn = Button(text="+ Add Rule", size_hint_y=None, height=dp(38))
        add_rule_btn.bind(on_release=lambda *a: self._open_rule_editor())
        root.add_widget(add_rule_btn)

        # AI: only there when switched on in Settings (see ai_ui.sync_button)
        self._ai_btn = Button(text="Describe a rule in words (AI)...",
                              size_hint_y=None, height=0, opacity=0,
                              disabled=True, font_size=sp(13))
        self._ai_btn.bind(on_release=lambda *a: self._ai_rule())
        root.add_widget(self._ai_btn)

        # source folder
        src_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=4)
        self._src_lbl = Label(text="(no source folder chosen)", font_size=sp(11),
                              halign="left", color=(0.7, 0.9, 0.7, 1))
        self._src_lbl.bind(size=self._src_lbl.setter("text_size"))
        pick_src_btn = Button(text="Pick Source Folder", size_hint_x=None,
                              width=dp(160))
        pick_src_btn.bind(on_release=self._pick_source)
        src_row.add_widget(pick_src_btn)
        src_row.add_widget(self._src_lbl)
        root.add_widget(src_row)

        self._recursive_cb = CheckBox(active=True, size_hint=(None, None),
                                      size=(dp(24), dp(24)))
        self._recursive_cb.bind(active=lambda *a: self._mark_stale())
        rec_row = BoxLayout(size_hint_y=None, height=dp(30), spacing=6)
        rec_row.add_widget(self._recursive_cb)
        rec_row.add_widget(self._left_label("Include subfolders"))
        root.add_widget(rec_row)

        # How long a file must stay unchanged before a rule touches it, so a
        # file that is still being generated / downloaded / saved is left alone.
        settle_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=6)
        settle_row.add_widget(self._left_label(
            "Only touch files unchanged for (seconds):"))
        self._settle_in = TextInput(text=f"{SETTLE_SECONDS:g}", multiline=False,
                                    input_filter="float", font_size=sp(13),
                                    size_hint_x=None, width=dp(64))
        self._settle_in.bind(text=lambda *a: self._sync_watch_cfg())
        settle_row.add_widget(self._settle_in)
        root.add_widget(settle_row)

        # Background watching (desktop): the Background service applies the
        # saved rules to this folder every ~20 s, even with the app closed.
        self._watch_syncing = False
        self._watch_cb = CheckBox(active=False, size_hint=(None, None),
                                  size=(dp(24), dp(24)))
        self._watch_cb.bind(active=self._on_watch_toggle)
        if _platform != "android":
            watch_row = BoxLayout(size_hint_y=None, height=dp(30), spacing=6)
            watch_row.add_widget(self._watch_cb)
            watch_row.add_widget(self._left_label(
                "Auto-apply in background (needs Background service)"))
            root.add_widget(watch_row)

        # actions
        act_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        self._preview_btn = Button(text="Preview")
        self._preview_btn.bind(on_release=self._run_preview)
        self._apply_btn = Button(text="Apply", disabled=True)
        self._apply_btn.bind(on_release=self._run_apply)
        self._stop_btn = Button(text="Stop", disabled=True, size_hint_x=None,
                                width=dp(70))
        self._stop_btn.bind(on_release=self._request_stop)
        act_row.add_widget(self._preview_btn)
        act_row.add_widget(self._apply_btn)
        act_row.add_widget(self._stop_btn)
        root.add_widget(act_row)

        self._status = Label(text="", size_hint_y=None, height=dp(20),
                             font_size=sp(11), color=(0.6, 0.8, 1, 1))
        root.add_widget(self._status)

        log_sv = ScrollView(size_hint_y=0.26)
        self._log_lbl = Label(text="", font_size=sp(10), halign="left",
                              valign="top", size_hint_y=None, markup=False)
        self._log_lbl.bind(texture_size=lambda *a: setattr(
            self._log_lbl, "height", self._log_lbl.texture_size[1]))
        self._log_lbl.bind(width=lambda *a: setattr(
            self._log_lbl, "text_size", (self._log_lbl.width, None)))
        log_sv.add_widget(self._log_lbl)
        root.add_widget(log_sv)

        # ruleset save/load - one "Rulesets..." button opens a popup with
        # its own save-as-new / overwrite-existing / load-existing
        # options, instead of an always-visible name field + two buttons
        # taking up permanent space on the main screen.
        rs_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        self._current_ruleset_name = ""
        rulesets_btn = Button(text="Rulesets... (Save/Load)")
        rulesets_btn.bind(on_release=self._show_rulesets_popup)
        rs_row.add_widget(rulesets_btn)
        root.add_widget(rs_row)

        # export/import to an arbitrary file location - distinct from
        # Save/Load above, which only ever read/write the app's own
        # internal named rulesets folder. This is what makes a ruleset
        # actually shareable or backupable outside the app.
        io_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        export_btn = Button(text="Export...", size_hint_x=None, width=dp(90))
        export_btn.bind(on_release=self._show_export_popup)
        import_btn = Button(text="Import...", size_hint_x=None, width=dp(90))
        import_btn.bind(on_release=self._show_import_popup)
        io_row.add_widget(export_btn)
        io_row.add_widget(import_btn)
        io_row.add_widget(Label(
            text="(save/load a ruleset to any file, e.g. to share it)",
            font_size=sp(10), color=(0.6, 0.6, 0.6, 1), halign="left"))
        root.add_widget(io_row)

        back = Button(text="< Back", size_hint_y=None, height=dp(40))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)
        self._load_last_used()

    @staticmethod
    def _left_label(text):
        lbl = Label(text=text, font_size=sp(12), halign="left")
        lbl.bind(size=lbl.setter("text_size"))
        return lbl

    def on_pre_enter(self, *a):
        from screens import ai_ui
        ai_ui.sync_button(self._ai_btn, "file_sorter", dp(38))

    def _ai_rule(self):
        from screens import ai_ui
        from core import ai_rules

        def go(text):
            def done(res, err):
                if err:
                    return ai_ui.show_error(err)
                rule, note = res
                if rule is None:
                    return ai_ui.show_error(note)
                self._open_ai_rule(rule, note)
            ai_ui.work(lambda: ai_rules.rule_from_words(text), done)

        ai_ui.ask("Describe the rule",
                  "e.g. move every video with roblox in its name to my "
                  "Videos/roblox folder", go, button="Write the rule")

    def _open_ai_rule(self, rule, note):
        """Open the Rule Editor on the AI's proposal. Nothing is added until
        the user presses Save Rule there."""
        groups = sorted({r.get("group", "") for r in self._rules
                         if r.get("group")})

        def _on_save(saved):
            self._rules.append(saved)
            self._refresh_group_filter_values()
            self._refresh_rules_list()
            self._mark_stale()
            self._autosave_last_used()

        RuleEditorPopup(on_save=_on_save, existing=rule,
                        existing_groups=groups).open()
        if note:
            from screens import ai_ui
            ai_ui._msg("Written by the AI - check it", note + "\n\nThe rule is "
                       "open in the editor. Nothing is saved until you press "
                       "Save Rule.", 0.4)

    # ── rules list management ───────────────────────────────────────────
    def _mark_stale(self):
        self._plan_stale = True
        self._apply_btn.disabled = True

    def _open_rule_editor(self, index=None):
        existing = self._rules[index] if index is not None else None
        existing_groups = sorted({r.get("group", "") for r in self._rules
                                  if r.get("group")})

        def _on_save(rule):
            if index is not None:
                self._rules[index] = rule
            else:
                self._rules.append(rule)
            self._refresh_group_filter_values()
            self._refresh_rules_list()
            self._mark_stale()
            self._autosave_last_used()

        RuleEditorPopup(on_save=_on_save, existing=existing,
                       existing_groups=existing_groups).open()

    def _refresh_group_filter_values(self):
        groups = sorted({r.get("group", "") for r in self._rules if r.get("group")})
        values = ["All groups"] + groups
        if groups:
            values.append("(ungrouped)")
        self._group_filter_sp.values = values
        if self._group_filter_sp.text not in values:
            self._group_filter_sp.text = "All groups"

    def _refresh_rules_list(self):
        self._rules_box.clear_widgets()
        filt = self._group_filter_sp.text
        for i, rule in enumerate(self._rules):
            group = rule.get("group", "")
            if filt == "All groups":
                pass
            elif filt == "(ungrouped)":
                if group:
                    continue
            elif group != filt:
                continue
            self._rules_box.add_widget(self._build_rule_card(i, rule))

    def _build_rule_card(self, index, rule):
        card = BoxLayout(size_hint_y=None, height=dp(46), spacing=4,
                         padding=(4, 2))
        n_cond = len(rule.get("conditions", []))
        group = rule.get("group", "")
        group_tag = f"[{group}] " if group else ""
        enabled = rule.get("enabled", True)

        enabled_cb = CheckBox(active=enabled, size_hint=(None, None),
                              size=(dp(24), dp(24)))

        def _toggle(cb, value, idx=index):
            self._rules[idx]["enabled"] = value
            self._mark_stale()
            self._autosave_last_used()

        enabled_cb.bind(active=_toggle)
        card.add_widget(enabled_cb)

        summary = f"{group_tag}{rule_title(rule)}"
        text_color = (0.9, 0.9, 0.9, 1) if enabled else (0.5, 0.5, 0.5, 1)
        lbl = Label(text=summary, font_size=sp(10), halign="left", color=text_color)
        lbl.bind(size=lbl.setter("text_size"))
        card.add_widget(lbl)

        up = Button(text="Up", font_size=sp(11), size_hint_x=None, width=dp(40))
        up.bind(on_release=lambda *a: self._move_rule(index, -1))
        down = Button(text="Dn", font_size=sp(11), size_hint_x=None, width=dp(40))
        down.bind(on_release=lambda *a: self._move_rule(index, 1))
        edit = Button(text="Edit", size_hint_x=None, width=dp(50))
        edit.bind(on_release=lambda *a: self._open_rule_editor(index))
        rm = Button(text="Del", size_hint_x=None, width=dp(44))
        rm.bind(on_release=lambda *a: self._delete_rule(index))
        for w in (up, down, edit, rm):
            card.add_widget(w)
        return card

    def _move_rule(self, index, direction):
        j = index + direction
        if 0 <= j < len(self._rules):
            self._rules[index], self._rules[j] = self._rules[j], self._rules[index]
            self._refresh_rules_list()
            self._mark_stale()
            self._autosave_last_used()

    def _delete_rule(self, index):
        del self._rules[index]
        self._refresh_rules_list()
        self._mark_stale()
        self._autosave_last_used()

    # ── source folder ────────────────────────────────────────────────────
    def _pick_source(self, *a):
        chooser = FileChooserIconView(path=self._source_folder or _home(),
                                      dirselect=True)
        btn = Button(text="Use this folder", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Choose source folder", content=layout,
                      size_hint=(0.92, 0.92))

        def _use(*b):
            folder = chooser.selection[0] if chooser.selection else chooser.path
            self._source_folder = folder
            self._src_lbl.text = folder
            self._mark_stale()
            self._autosave_last_used()
            popup.dismiss()

        btn.bind(on_release=_use)
        popup.open()

    # ── ruleset persistence ──────────────────────────────────────────────
    def _show_rulesets_popup(self, *a):
        names = list_rulesets()
        layout = BoxLayout(orientation="vertical", spacing=6, padding=8)

        new_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=4)
        name_input = TextInput(text=self._current_ruleset_name or "my_rules",
                               multiline=False, font_size=sp(12))
        save_new_btn = Button(text="Save as new", size_hint_x=None, width=dp(100))
        new_row.add_widget(name_input)
        new_row.add_widget(save_new_btn)
        layout.add_widget(new_row)

        layout.add_widget(Label(text="Existing rulesets:", size_hint_y=None,
                                height=dp(20), font_size=sp(12), halign="left"))

        sv = ScrollView()
        grid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=2)
        grid.bind(minimum_height=grid.setter("height"))
        if not names:
            grid.add_widget(Label(text="No saved rulesets yet.",
                                  size_hint_y=None, height=dp(30)))

        popup = Popup(title="Rulesets - Save / Load", content=layout,
                      size_hint=(0.75, 0.7))

        def _refresh_status(msg):
            self._status.text = msg

        def _save_as(*b):
            name = name_input.text.strip()
            if not name:
                self._status.text = "Enter a name first."
                return
            ok = save_ruleset(name, self._rules)
            self._current_ruleset_name = name if ok else self._current_ruleset_name
            _refresh_status(f"Saved ruleset '{name}'." if ok else "Save failed.")
            popup.dismiss()

        save_new_btn.bind(on_release=_save_as)

        for n in names:
            row = BoxLayout(size_hint_y=None, height=dp(38), spacing=4)
            row.add_widget(Label(text=n, font_size=sp(12), halign="left"))
            load_btn = Button(text="Load", size_hint_x=None, width=dp(70))
            overwrite_btn = Button(text="Save over", size_hint_x=None, width=dp(90))

            def _load(inst, name=n):
                self._rules = load_ruleset(name)
                self._current_ruleset_name = name
                self._refresh_group_filter_values()
                self._refresh_rules_list()
                self._mark_stale()
                self._autosave_last_used()
                _refresh_status(f"Loaded ruleset '{name}'.")
                popup.dismiss()

            def _overwrite(inst, name=n):
                ok = save_ruleset(name, self._rules)
                self._current_ruleset_name = name if ok else self._current_ruleset_name
                _refresh_status(f"Saved over '{name}'." if ok else "Save failed.")
                popup.dismiss()

            load_btn.bind(on_release=_load)
            overwrite_btn.bind(on_release=_overwrite)
            row.add_widget(load_btn)
            row.add_widget(overwrite_btn)
            grid.add_widget(row)

        sv.add_widget(grid)
        layout.add_widget(sv)

        close_btn = Button(text="Close", size_hint_y=None, height=dp(38))
        close_btn.bind(on_release=lambda *b: popup.dismiss())
        layout.add_widget(close_btn)
        popup.open()

    def _show_export_popup(self, *a):
        if not self._rules:
            self._status.text = "No rules to export yet."
            return

        chooser = FileChooserIconView(path=_home(), dirselect=True)
        layout = BoxLayout(orientation="vertical", spacing=4, padding=6)
        layout.add_widget(chooser)

        name_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)
        name_row.add_widget(Label(text="File name:", size_hint_x=None,
                                  width=dp(80), font_size=sp(12)))
        filename_input = TextInput(
            text=(self._current_ruleset_name.strip() or "my_rules") + ".json",
            multiline=False, font_size=sp(12))
        name_row.add_widget(filename_input)
        layout.add_widget(name_row)

        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        export_btn = Button(text="Export here")
        cancel_btn = Button(text="Cancel")
        btn_row.add_widget(export_btn)
        btn_row.add_widget(cancel_btn)
        layout.add_widget(btn_row)

        popup = Popup(title="Export Ruleset To...", content=layout,
                      size_hint=(0.92, 0.92))
        cancel_btn.bind(on_release=lambda *b: popup.dismiss())

        def _do_export(*b):
            folder = chooser.selection[0] if chooser.selection else chooser.path
            if os.path.isfile(folder):
                folder = os.path.dirname(folder)
            fname = filename_input.text.strip() or "ruleset.json"
            if not fname.lower().endswith(".json"):
                fname += ".json"
            full_path = os.path.join(folder, fname)
            ok, err = export_ruleset_to_path(full_path, self._rules)
            self._status.text = (f"Exported to {full_path}" if ok
                                 else f"Export failed: {err}")
            popup.dismiss()

        export_btn.bind(on_release=_do_export)
        popup.open()

    def _show_import_popup(self, *a):
        chooser = FileChooserIconView(path=_home(), filters=["*.json"])
        layout = BoxLayout(orientation="vertical", spacing=4, padding=6)
        layout.add_widget(chooser)

        btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=6)
        import_btn = Button(text="Import selected file")
        cancel_btn = Button(text="Cancel")
        btn_row.add_widget(import_btn)
        btn_row.add_widget(cancel_btn)
        layout.add_widget(btn_row)

        popup = Popup(title="Import Ruleset From...", content=layout,
                      size_hint=(0.92, 0.92))
        cancel_btn.bind(on_release=lambda *b: popup.dismiss())

        def _do_import(*b):
            if not chooser.selection:
                return
            path = chooser.selection[0]
            rules, err, skipped = import_ruleset_from_path(path)
            if err:
                self._status.text = f"Import failed: {err}"
                popup.dismiss()
                return
            if not rules:
                self._status.text = "That file had no usable rules in it."
                popup.dismiss()
                return
            self._rules = rules
            self._refresh_group_filter_values()
            self._refresh_rules_list()
            self._mark_stale()
            self._autosave_last_used()
            note = f", skipped {skipped} malformed entr{'y' if skipped == 1 else 'ies'}" \
                if skipped else ""
            self._status.text = f"Imported {len(rules)} rules from {path}{note}."
            popup.dismiss()

        import_btn.bind(on_release=_do_import)
        popup.open()

    def _settle(self):
        """Seconds from the box; the default if it is empty or not a number."""
        try:
            return max(0.0, min(3600.0, float(self._settle_in.text)))
        except ValueError:
            return float(SETTLE_SECONDS)

    def _sync_watch_cfg(self):
        try:
            from core import file_sorter_watch as fsw
            fsw.save_config({"enabled": bool(self._watch_cb.active),
                             "source_folder": self._source_folder,
                             "recursive": self._recursive_cb.active,
                             "ruleset": LAST_USED_KEY,
                             "settle_seconds": self._settle()})
        except Exception as e:
            print(f"FileSorter: watch config save failed: {e}")

    def _on_watch_toggle(self, cb, active):
        if self._watch_syncing:
            return
        if active and (not self._source_folder or not self._rules):
            self._watch_syncing = True
            cb.active = False
            self._watch_syncing = False
            self._status.text = "Pick a source folder and add rules first."
            return
        self._autosave_last_used()      # also writes the watch config
        try:
            from core.daemon_ipc import send_command
            threading.Thread(target=lambda: send_command("reload"),
                             daemon=True).start()
        except Exception:
            pass
        if active:
            self._status.text = ("Background watching ON - rules run on this "
                                 "folder every ~20 s while the Background "
                                 "service is running (Settings). Existing "
                                 "matching files are sorted too.")
        else:
            self._status.text = "Background watching OFF."

    def _autosave_last_used(self):
        save_ruleset(LAST_USED_KEY, self._rules)
        self._sync_watch_cfg()
        cfg_path = os.path.join(_rulesets_dir(), f"{LAST_USED_KEY}_folder.json")
        try:
            write_json_atomic(cfg_path, {"source_folder": self._source_folder,
                                         "recursive": self._recursive_cb.active})
        except Exception:
            pass

    def _load_last_used(self):
        # Reads two small files off disk - cheap most of the time, but
        # this is called from __init__, i.e. at screen-build time. Doing
        # any disk I/O synchronously there stalls the UI for a moment on
        # first navigation to this screen, working against the app's own
        # lazy-loading philosophy (screens should build instantly, then
        # fill in). Load in the background instead.
        def worker():
            rules = load_ruleset(LAST_USED_KEY)
            cfg_path = os.path.join(_rulesets_dir(), f"{LAST_USED_KEY}_folder.json")
            cfg = read_json(cfg_path, {})
            if not isinstance(cfg, dict):
                cfg = {}
            Clock.schedule_once(lambda dt: self._apply_last_used(rules, cfg))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_last_used(self, rules, cfg):
        self._rules = rules
        self._refresh_group_filter_values()
        self._refresh_rules_list()
        self._source_folder = cfg.get("source_folder", "")
        if self._source_folder:
            self._src_lbl.text = self._source_folder
        self._recursive_cb.active = cfg.get("recursive", True)
        try:
            from core import file_sorter_watch as fsw
            self._watch_syncing = True
            wcfg = fsw.load_config()
            self._watch_cb.active = wcfg["enabled"]
            self._settle_in.text = f"{wcfg['settle_seconds']:g}"
        except Exception:
            pass
        finally:
            self._watch_syncing = False

    # ── preview ──────────────────────────────────────────────────────────
    def _collect_files(self):
        if not self._source_folder or not os.path.isdir(self._source_folder):
            return []
        files = []
        if self._recursive_cb.active:
            for root_dir, _dirs, names in os.walk(self._source_folder):
                for n in names:
                    files.append(os.path.join(root_dir, n))
        else:
            for n in os.listdir(self._source_folder):
                p = os.path.join(self._source_folder, n)
                if os.path.isfile(p):
                    files.append(p)
        return files

    def _run_preview(self, *a):
        if self._busy:
            return
        if not self._source_folder:
            self._status.text = "Pick a source folder first."
            return
        if not self._rules:
            self._status.text = "Add at least one rule first."
            return
        self._busy = True
        self._preview_btn.disabled = True
        self._apply_btn.disabled = True
        self._status.text = "Scanning..."
        self._log_lbl.text = ""
        clear_meta_cache()

        rules_snapshot = [dict(r) for r in self._rules]

        def worker():
            files = self._collect_files()
            plan = build_plan(files, rules_snapshot)
            # Only on the (small) matched set: say which files are not ready
            # to be touched yet (still being written, empty, open elsewhere,
            # editor lock file ...), so Apply's waiting isn't a surprise.
            incomplete = {}
            settle = self._settle()
            for path, _rules in plan[:200]:
                ready = file_safety.check(path, settle)
                if not ready.ready:
                    incomplete[path] = ready.reason
            Clock.schedule_once(
                lambda dt: self._on_preview_done(files, plan, incomplete))

        threading.Thread(target=worker, daemon=True).start()

    def _on_preview_done(self, files, plan, incomplete=None):
        incomplete = incomplete or {}
        self._busy = False
        self._preview_btn.disabled = False
        self._plan = plan
        self._plan_stale = False
        self._apply_btn.disabled = (len(plan) == 0)
        note = f" - {len(incomplete)} aren't ready to be touched yet" \
            if incomplete else ""
        self._status.text = (
            f"Scanned {len(files)} files - {len(plan)} match at least "
            f"one rule{note}.")
        lines = []
        for path, rules in plan[:200]:
            names = " -> ".join(f"{r['name']}({r['action']['type']})" for r in rules)
            flag = (f"  [!] not ready: {incomplete[path]} - Apply will wait "
                    f"for it" if path in incomplete else "")
            lines.append(f"{path}{flag}\n    {names}")
        if len(plan) > 200:
            lines.append(f"... and {len(plan) - 200} more (not shown in preview)")
        self._log_lbl.text = "\n".join(lines) if lines else "No files matched any rule."

    # ── apply ────────────────────────────────────────────────────────────
    def _run_apply(self, *a):
        if self._busy or self._plan_stale or not self._plan:
            return
        self._busy = True
        self._stop_requested = False
        self._apply_btn.disabled = True
        self._preview_btn.disabled = True
        self._stop_btn.disabled = False
        self._status.text = f"Applying to {len(self._plan)} files..."
        self._log_lines = []
        plan_snapshot = self._plan
        settle = self._settle()

        def log(msg):
            self._log_lines.append(msg)

        def set_status(text):
            Clock.schedule_once(lambda dt: setattr(self._status, "text", text))

        def worker():
            counter = 1
            total = len(plan_snapshot)
            for i, (path, rules) in enumerate(plan_snapshot, start=1):
                if self._stop_requested:
                    log("Stopped by user.")
                    break
                log(f"{path}")
                current = path
                exists = True
                for rule in rules:
                    if self._stop_requested:
                        log("  Stopped by user.")
                        exists = False
                        break
                    if not exists:
                        log(f"  skipped rule '{rule['name']}' "
                           f"(file no longer exists)")
                        continue

                    # Don't touch a file that's still being written to -
                    # e.g. a download/install still in progress. Wait it
                    # out (or bail if the user hits Stop, or the file
                    # disappears on its own).
                    def progress(elapsed, size, _current=current):
                        if elapsed > 0 and elapsed % 5 < STABLE_POLL_INTERVAL:
                            set_status(
                                f"Applying ({i}/{total}) - waiting for "
                                f"{os.path.basename(_current)} to finish "
                                f"writing ({_fmt_size(size)}, {int(elapsed)}s)...")

                    stable = wait_for_stable_file(
                        current, log=log,
                        stop_check=lambda: self._stop_requested,
                        progress=progress, settle=settle,
                        max_wait=APPLY_MAX_WAIT)
                    if not stable:
                        if self._stop_requested:
                            log(f"  skipped rule '{rule['name']}' "
                               f"(stopped while waiting for file to finish)")
                        elif os.path.exists(current):
                            log(f"  skipped rule '{rule['name']}' (still in use "
                                f"after {int(APPLY_MAX_WAIT)}s - left where it is; "
                                f"Apply again later)")
                        else:
                            log(f"  skipped rule '{rule['name']}' "
                               f"(file disappeared while waiting for it to finish)")
                        exists = False
                        continue

                    set_status(f"Applying ({i}/{total})...")
                    current, exists = apply_action(
                        current, rule["action"], counter, log,
                        confirm_delete=self._confirm_delete_blocking)
                counter += 1
            Clock.schedule_once(lambda dt: self._on_apply_done())

        threading.Thread(target=worker, daemon=True).start()

    def _confirm_delete_blocking(self, path):
        """Runs on the APPLY WORKER thread and blocks it (never the UI
        thread) until the user answers a real popup, or Stop is hit.
        This is the OS-trash-style "are you sure?" for any delete rule
        that doesn't have its own Auto-delete checkbox on."""
        event = threading.Event()
        result = {"ok": False}
        holder = {"popup": None}

        def _show(dt):
            content = BoxLayout(orientation="vertical", spacing=8, padding=10)
            content.add_widget(Label(
                text=f"Delete this file?\n\n{path}", font_size=sp(12),
                halign="center"))
            btn_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
            yes = Button(text="Delete")
            no = Button(text="Skip")
            btn_row.add_widget(yes)
            btn_row.add_widget(no)
            content.add_widget(btn_row)
            popup = Popup(title="Confirm delete", content=content,
                          size_hint=(0.75, 0.35), auto_dismiss=False)
            holder["popup"] = popup

            def _answer(ok):
                result["ok"] = ok
                popup.dismiss()
                event.set()

            yes.bind(on_release=lambda *a: _answer(True))
            no.bind(on_release=lambda *a: _answer(False))
            popup.open()

        Clock.schedule_once(_show)
        while not event.wait(timeout=0.2):
            if self._stop_requested:
                if holder["popup"]:
                    Clock.schedule_once(lambda dt: holder["popup"].dismiss())
                return False
        return result["ok"]

    def _request_stop(self, *a):
        self._stop_requested = True
        self._stop_btn.disabled = True
        self._status.text = "Stopping... (finishing current file)"

    def _on_apply_done(self):
        self._busy = False
        self._preview_btn.disabled = False
        self._stop_btn.disabled = True
        self._plan_stale = True
        self._apply_btn.disabled = True
        self._status.text = "Done. Re-run Preview before applying again."
        self._log_lbl.text = "\n".join(self._log_lines)

    # ── nav ──────────────────────────────────────────────────────────────
    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
