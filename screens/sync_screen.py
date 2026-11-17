# screens/sync_screen.py - Folder Sync, two modes:
#   One way (mirror): make folder B match folder A (core/sync_core.py).
#   Two way: carry changes both ways, keep both versions on a conflict
#   (core/twoway_core.py).
# Always preview first; Sync is only enabled for the preview you just looked
# at. Whatever a sync would overwrite or remove is moved to a
# ".srboli-replaced" folder, never deleted.
import os
import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton

import app_data
from core import sync_core as sc
from core import twoway_core as tw
from core import theme
from core.backup_core import fmt_size
from core.jsonio import read_json, write_json_atomic
from screens.backup_screen import pick_folder
from screens.scaffold import ToolScreen

MAX_LINES = 200
HELP = {
    "mirror": "One way: the target is changed to match the source. The source "
              "is never touched. Files that would be overwritten or removed "
              "are moved to a \".srboli-replaced\" folder in the target, not "
              "deleted.",
    "two": "Two way: changes in either folder are carried to the other, and "
           "deleting a file on one side deletes it on the other. If both "
           "sides changed the same file, the newer one wins and the other "
           "version is kept next to it as \"(conflict ...)\". Nothing is "
           "really deleted: it goes to \".srboli-replaced\".",
}


def _cfg_path():
    return os.path.join(app_data.subdir("sync"), "config.json")


class SyncScreen(ToolScreen):
    title = "Folder Sync"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.a = ""
        self.b = ""
        self.mode = "mirror"
        self._plan = None
        self._busy = False
        self._stop = False
        root = self.body
        cfg = read_json(_cfg_path(), {})
        if isinstance(cfg, dict):
            self.a, self.b = cfg.get("a", ""), cfg.get("b", "")
            if cfg.get("mode") in HELP:
                self.mode = cfg["mode"]

        modes = BoxLayout(size_hint_y=None, height=dp(42), spacing=theme.PAD["s"])
        self._mode_btns = {}
        for key, label in (("mirror", "One way (mirror)"), ("two", "Two way")):
            b = ToggleButton(text=label, group="sync_mode", font_size=sp(14),
                             allow_no_selection=False,
                             state="down" if key == self.mode else "normal")
            b.bind(on_release=lambda inst, k=key: self._set_mode(k))
            b.bind(state=lambda inst, st: setattr(
                inst, "background_color",
                theme.ACCENT if st == "down" else theme.SURFACE2))
            b.background_color = theme.ACCENT if b.state == "down" else theme.SURFACE2
            self._mode_btns[key] = b
            modes.add_widget(b)
        root.add_widget(modes)

        self.a_btn, self.a_lbl = self._row(root, "", self._pick_a)
        self.b_btn, self.b_lbl = self._row(root, "", self._pick_b)
        self.help_lbl = self._text("", height=dp(76), color=theme.MUTED)
        root.add_widget(self.help_lbl)

        acts = BoxLayout(size_hint_y=None, height=dp(44), spacing=theme.PAD["s"])
        self.preview_btn = Button(text="Preview", font_size=sp(14))
        self.preview_btn.bind(on_release=lambda *a: self.preview())
        self.sync_btn = Button(text="Sync now", font_size=sp(14), disabled=True,
                               background_color=theme.ACCENT)
        self.sync_btn.bind(on_release=lambda *a: self.sync())
        self.stop_btn = Button(text="Stop", size_hint_x=None, width=dp(80),
                               disabled=True, font_size=sp(14))
        self.stop_btn.bind(on_release=lambda *a: self._request_stop())
        for w in (self.preview_btn, self.sync_btn, self.stop_btn):
            acts.add_widget(w)
        root.add_widget(acts)

        self.bar = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(8))
        root.add_widget(self.bar)
        self.status = self._text("", height=dp(70), color=theme.ACCENT)
        root.add_widget(self.status)

        sv = ScrollView(do_scroll_x=False)
        self.log = Label(text="", font_size=sp(11), halign="left", valign="top",
                         size_hint_y=None, color=theme.TEXT)
        self.log.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                      texture_size=lambda w, v: setattr(w, "height", v[1]))
        sv.add_widget(self.log)
        root.add_widget(sv)

        bottom = BoxLayout(size_hint_y=None, height=dp(40), spacing=theme.PAD["s"])
        self.replaced_lbl = self._text("", height=dp(40), color=theme.MUTED)
        self.clear_btn = Button(text="Clear old replaced files", size_hint_x=None,
                                width=dp(200), font_size=sp(12))
        self.clear_btn.bind(on_release=lambda *a: self._clear_replaced())
        bottom.add_widget(self.replaced_lbl)
        bottom.add_widget(self.clear_btn)
        root.add_widget(bottom)
        self._refresh()

    # ── builders ─────────────────────────────────────────────────────────
    @staticmethod
    def _text(text, height=dp(24), color=None):
        lbl = Label(text=text, markup=True, font_size=sp(13), halign="left",
                    valign="middle", size_hint_y=None, height=height,
                    color=color or theme.TEXT)
        lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        return lbl

    def _row(self, root, caption, handler):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=theme.PAD["s"])
        btn = Button(text=caption, size_hint_x=0.42, font_size=sp(13))
        btn.bind(on_release=lambda *a: handler())
        lbl = Label(text="", font_size=sp(12), halign="left", valign="middle",
                    shorten=True, shorten_from="left", color=theme.MUTED)
        lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        row.add_widget(btn)
        row.add_widget(lbl)
        root.add_widget(row)
        return btn, lbl

    # ── state ────────────────────────────────────────────────────────────
    def _save_cfg(self):
        try:
            write_json_atomic(_cfg_path(), {"a": self.a, "b": self.b,
                                            "mode": self.mode})
        except Exception:
            pass

    def _stale(self):
        self._plan = None
        self.sync_btn.disabled = True

    def _set_mode(self, mode):
        self.mode = mode
        self._stale()
        self.log.text = ""
        self._save_cfg()
        self._refresh()

    def _refresh(self):
        two = self.mode == "two"
        self.a_btn.text = "Folder A" if two else "Copy FROM"
        self.b_btn.text = "Folder B" if two else "Make this match (TO)"
        self.help_lbl.text = HELP[self.mode]
        self.a_lbl.text = self.a or "(none chosen)"
        self.b_lbl.text = self.b or "(none chosen)"
        n = size = 0
        if self.b and os.path.isdir(self.b):
            if two and self.a and os.path.isdir(self.a):
                n, size = tw.replaced_total(self.a, self.b)
            else:
                n, size = sc.replaced_info(self.b)
        self.replaced_lbl.text = (f"Replaced folder: {n} file(s), {fmt_size(size)}"
                                  if n else "")
        self.clear_btn.disabled = not n

    def _set_busy(self, busy):
        self._busy = busy
        self.preview_btn.disabled = busy
        self.stop_btn.disabled = not busy
        if busy:
            self.sync_btn.disabled = True

    def _say(self, text):
        self.status.text = text

    def _pick_a(self):
        def done(f):
            self.a = f
            self._stale(); self._save_cfg(); self._refresh()
        pick_folder("Folder A" if self.mode == "two" else "Copy FROM this folder",
                    self.a, done)

    def _pick_b(self):
        def done(f):
            self.b = f
            self._stale(); self._save_cfg(); self._refresh()
        pick_folder("Folder B" if self.mode == "two" else "Make THIS folder match",
                    self.b, done)

    # ── preview ──────────────────────────────────────────────────────────
    def preview(self):
        if self._busy:
            return
        problem = (tw if self.mode == "two" else sc).check_folders(self.a, self.b)
        if problem:
            self._say(problem)
            return
        self._set_busy(True)
        self._say("Comparing the folders...")
        self.log.text = ""
        a, b, mode = self.a, self.b, self.mode

        def work():
            try:
                plan = (tw if mode == "two" else sc).make_plan(a, b)
                Clock.schedule_once(lambda dt: self._preview_done(plan))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._failed(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _preview_done(self, plan):
        self._set_busy(False)
        self._plan = plan
        if self.mode == "two":
            groups = (("A -> B", plan.a2b), ("B -> A", plan.b2a),
                      ("DELETE on A", plan.del_a), ("DELETE on B", plan.del_b),
                      ("CONFLICT", plan.conflicts))
            head = (f"{len(plan.a2b)} to B, {len(plan.b2a)} to A, "
                    f"{len(plan.del_a) + len(plan.del_b)} deletions to carry over, "
                    f"{len(plan.conflicts)} conflict(s), "
                    f"{plan.same + len(plan.adopt)} already the same.")
            if plan.note:
                head += "\n" + plan.note
        else:
            groups = (("COPY", plan.new), ("REPLACE", plan.changed),
                      ("MOVE AWAY", plan.removed))
            head = (f"{len(plan.new)} new, {len(plan.changed)} changed (old "
                    f"version kept aside), {len(plan.removed)} only in the "
                    f"target (moved aside), {plan.same} the same. Copies "
                    f"{fmt_size(plan.copy_bytes)}.")
        lines = [f"{tag}  {r}" for tag, rels in groups for r in rels]
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"... and {len(lines) - MAX_LINES} more"]
        self.log.text = "\n".join(lines) if lines else "The folders already match."
        if plan.warning:
            head += "\n[b]Careful:[/b] " + plan.warning
        self._say(head)
        self.sync_btn.disabled = plan.work == 0

    # ── sync ─────────────────────────────────────────────────────────────
    def sync(self):
        if self._busy or self._plan is None or self._plan.work == 0:
            return
        plan = self._plan
        if plan.warning:
            self._confirm(plan)
        else:
            self._start(plan)

    def _confirm(self, plan):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        lbl = Label(text=plan.warning + "\n\nGo ahead anyway?", halign="center",
                    font_size=sp(13))
        lbl.bind(width=lambda w, v: setattr(w, "text_size", (v - 20, None)))
        box.add_widget(lbl)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        yes, no = Button(text="Sync anyway"), Button(text="Cancel")
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        popup = Popup(title="Check before syncing", content=box,
                      size_hint=(0.85, 0.5), auto_dismiss=False)
        no.bind(on_release=lambda *a: popup.dismiss())

        def _go(*a):
            popup.dismiss()
            self._start(plan)

        yes.bind(on_release=_go)
        popup.open()

    def _start(self, plan):
        self._set_busy(True)
        self._stop = False
        self.bar.value = 0
        self._say("Starting...")
        a, b, mode = self.a, self.b, self.mode

        def progress(done, total, rel):
            Clock.schedule_once(lambda dt: self._progress(done, total, rel))

        def work():
            try:
                res = (tw if mode == "two" else sc).run_sync(
                    a, b, progress=progress, stop=lambda: self._stop, plan=plan)
                Clock.schedule_once(lambda dt: self._done(res))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._failed(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done, total, rel):
        self.bar.max = max(1, total)
        self.bar.value = done
        if total:
            self._say(f"{done}/{total}  {rel}")

    def _request_stop(self):
        self._stop = True
        self.stop_btn.disabled = True
        self._say("Stopping after the current file... (run it again to carry on)")

    def _failed(self, msg):
        self._set_busy(False)
        self._say(f"Something went wrong: {msg}")

    def _done(self, res):
        self._set_busy(False)
        self._plan = None
        self.sync_btn.disabled = True
        self.bar.value = 0
        if res.error:
            self._say(res.error)
        else:
            head = 'Stopped' if res.stopped else 'Done'
            if self.mode == "two":
                text = (f"{head}: {res.to_b} to B, {res.to_a} to A, "
                        f"{res.deleted_a + res.deleted_b} deleted (kept in the "
                        f"replaced folder), {res.conflicts} conflict(s) with "
                        f"both versions kept.")
            else:
                text = (f"{head}: {res.copied} copied, {res.replaced} old "
                        f"version(s) and {res.removed} removed file(s) moved "
                        f"to the replaced folder.")
            if res.stopped:
                text += " Run Preview and Sync again to finish."
            if res.failed:
                text += (f"\n{len(res.failed)} file(s) could not be handled "
                         f"(e.g. {res.failed[0][0]}: {res.failed[0][1]}).")
            self._say(text)
        self._refresh()

    # ── replaced folder ──────────────────────────────────────────────────
    def _clear_replaced(self):
        if not self.b:
            return
        if self.mode == "two" and self.a and os.path.isdir(self.a):
            n, size = tw.replaced_total(self.a, self.b)
        else:
            n, size = sc.replaced_info(self.b)
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        box.add_widget(Label(
            text=f"Permanently delete replaced files older than 30 days?\n"
                 f"(The replaced folder holds {n} file(s), {fmt_size(size)}.)\n"
                 f"Newer ones are kept. This cannot be undone.",
            halign="center", font_size=sp(13)))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        yes, no = Button(text="Delete old ones"), Button(text="Keep all")
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        popup = Popup(title="Clear replaced files", content=box,
                      size_hint=(0.85, 0.45))
        no.bind(on_release=lambda *a: popup.dismiss())

        def _do(*a):
            popup.dismiss()
            if self.mode == "two" and self.a:
                k = tw.purge_both(self.a, self.b, 30)
            else:
                k = sc.purge_replaced(self.b, 30)
            self._say(f"Removed {k} old batch(es) from the replaced folder.")
            self._refresh()

        yes.bind(on_release=_do)
        popup.open()
