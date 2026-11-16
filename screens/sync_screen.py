# screens/sync_screen.py - Folder Sync: make one folder match another (one
# way). Always preview first; Sync is only enabled for the preview you just
# looked at. Whatever a sync would overwrite or remove is moved to a
# ".srboli-replaced" folder in the target, never deleted. Engine:
# core/sync_core.py.
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

import app_data
from core import sync_core as sc
from core import theme
from core.backup_core import fmt_size
from core.jsonio import read_json, write_json_atomic
from screens.backup_screen import pick_folder
from screens.scaffold import ToolScreen

MAX_LINES = 200


def _cfg_path():
    return os.path.join(app_data.subdir("sync"), "config.json")


class SyncScreen(ToolScreen):
    title = "Folder Sync"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.a = ""
        self.b = ""
        self._plan = None
        self._busy = False
        self._stop = False
        root = self.body
        cfg = read_json(_cfg_path(), {})
        if isinstance(cfg, dict):
            self.a, self.b = cfg.get("a", ""), cfg.get("b", "")

        self.a_lbl = self._row(root, "Copy FROM", self._pick_a)
        self.b_lbl = self._row(root, "Make this match (TO)", self._pick_b)
        root.add_widget(self._text(
            "One way: the target is changed to match the source. The source "
            "is never touched. Files that would be overwritten or removed "
            "are moved to a \".srboli-replaced\" folder in the target, not "
            "deleted.", height=dp(64), color=theme.MUTED))

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
        return lbl

    # ── state ────────────────────────────────────────────────────────────
    def _save_cfg(self):
        try:
            write_json_atomic(_cfg_path(), {"a": self.a, "b": self.b})
        except Exception:
            pass

    def _stale(self):
        self._plan = None
        self.sync_btn.disabled = True

    def _refresh(self):
        self.a_lbl.text = self.a or "(none chosen)"
        self.b_lbl.text = self.b or "(none chosen)"
        n, size = (sc.replaced_info(self.b) if self.b and os.path.isdir(self.b)
                   else (0, 0))
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
        pick_folder("Copy FROM this folder", self.a, done)

    def _pick_b(self):
        def done(f):
            self.b = f
            self._stale(); self._save_cfg(); self._refresh()
        pick_folder("Make THIS folder match", self.b, done)

    # ── preview ──────────────────────────────────────────────────────────
    def preview(self):
        if self._busy:
            return
        problem = sc.check_folders(self.a, self.b)
        if problem:
            self._say(problem)
            return
        self._set_busy(True)
        self._say("Comparing the folders...")
        self.log.text = ""
        a, b = self.a, self.b

        def work():
            try:
                plan = sc.make_plan(a, b)
                Clock.schedule_once(lambda dt: self._preview_done(plan))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._failed(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _preview_done(self, plan):
        self._set_busy(False)
        self._plan = plan
        lines = []
        for tag, rels in (("COPY   ", plan.new), ("REPLACE", plan.changed),
                          ("MOVE AWAY", plan.removed)):
            lines += [f"{tag}  {r}" for r in rels]
        if len(lines) > MAX_LINES:
            lines = lines[:MAX_LINES] + [f"... and {len(lines) - MAX_LINES} more"]
        self.log.text = "\n".join(lines) if lines else "The folders already match."
        head = (f"{len(plan.new)} new, {len(plan.changed)} changed (old version "
                f"kept aside), {len(plan.removed)} only in the target (moved "
                f"aside), {plan.same} the same. Copies {fmt_size(plan.copy_bytes)}.")
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
        a, b = self.a, self.b

        def progress(done, total, rel):
            Clock.schedule_once(lambda dt: self._progress(done, total, rel))

        def work():
            try:
                res = sc.run_sync(a, b, progress=progress,
                                  stop=lambda: self._stop, plan=plan)
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
            text = (f"{'Stopped' if res.stopped else 'Done'}: {res.copied} "
                    f"copied, {res.replaced} old version(s) and {res.removed} "
                    f"removed file(s) moved to the replaced folder.")
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
            k = sc.purge_replaced(self.b, 30)
            self._say(f"Removed {k} old batch(es) from the replaced folder.")
            self._refresh()

        yes.bind(on_release=_do)
        popup.open()
