# screens/backup_screen.py - Backup: full, incremental and differential
# backups of a folder, with a preview first, a list of the backups you have,
# and restore. The engine is core/backup_core.py (no UI, tested with real
# folders); this screen only drives it.
import os
import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton

import app_data
from core import backup_core as bc
from core import theme
from core.jsonio import read_json, write_json_atomic
from screens.scaffold import ToolScreen


def _cfg_path():
    return os.path.join(app_data.subdir("backup"), "config.json")


def _home():
    from core.android_storage import shared_storage_root
    return shared_storage_root()


def pick_folder(title, start, on_pick):
    """A popup to choose a folder; on_pick(folder) is called with it."""
    chooser = FileChooserIconView(path=start if start and os.path.isdir(start)
                                  else _home(), dirselect=True)
    use = Button(text="Use this folder", size_hint_y=None, height=dp(44))
    lay = BoxLayout(orientation="vertical")
    lay.add_widget(chooser)
    lay.add_widget(use)
    popup = Popup(title=title, content=lay, size_hint=(0.92, 0.92))

    def _use(*a):
        folder = chooser.selection[0] if chooser.selection else chooser.path
        if os.path.isfile(folder):
            folder = os.path.dirname(folder)
        popup.dismiss()
        on_pick(folder)

    use.bind(on_release=_use)
    popup.open()


class BackupScreen(ToolScreen):
    title = "Backup"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.source = ""
        self.dest = ""
        self.kind = "incr"
        self._plan = None
        self._busy = False
        self._stop = False
        root = self.body

        cfg = read_json(_cfg_path(), {})
        if isinstance(cfg, dict):
            self.source = cfg.get("source", "") if os.path.isdir(cfg.get("source", "")) else ""
            self.dest = cfg.get("dest", "")
            if cfg.get("kind") in bc.KINDS:
                self.kind = cfg["kind"]

        self.src_btn, self.src_lbl = self._folder_row(
            root, "Folder to back up", self._pick_source)
        self.dst_btn, self.dst_lbl = self._folder_row(
            root, "Put the backups in", self._pick_dest)

        kinds = BoxLayout(size_hint_y=None, height=dp(42), spacing=theme.PAD["s"])
        self._kind_btns = {}
        for k in bc.KINDS:
            b = ToggleButton(text=bc.KIND_LABELS[k], group="backup_kind",
                             allow_no_selection=False, font_size=sp(14),
                             state="down" if k == self.kind else "normal")
            b.bind(on_release=lambda inst, k=k: self._set_kind(k))
            b.bind(state=lambda inst, st: setattr(
                inst, "background_color",
                theme.ACCENT if st == "down" else theme.SURFACE2))
            b.background_color = theme.ACCENT if b.state == "down" else theme.SURFACE2
            self._kind_btns[k] = b
            kinds.add_widget(b)
        root.add_widget(kinds)

        self.help_lbl = self._text("", height=dp(48), color=theme.MUTED)
        root.add_widget(self.help_lbl)

        vrow = BoxLayout(size_hint_y=None, height=dp(30), spacing=theme.PAD["s"])
        self.verify_cb = CheckBox(active=bool(cfg.get("verify", False)) if isinstance(cfg, dict) else False,
                                  size_hint=(None, None), size=(dp(24), dp(24)))
        vrow.add_widget(self.verify_cb)
        vrow.add_widget(self._text("Check every copied file afterwards (slower, "
                                   "catches a bad copy)", height=dp(30)))
        root.add_widget(vrow)

        acts = BoxLayout(size_hint_y=None, height=dp(44), spacing=theme.PAD["s"])
        self.preview_btn = Button(text="Preview", font_size=sp(14))
        self.preview_btn.bind(on_release=lambda *a: self.preview())
        self.run_btn = Button(text="Back up now", font_size=sp(14),
                              background_color=theme.ACCENT)
        self.run_btn.bind(on_release=lambda *a: self.run())
        self.stop_btn = Button(text="Stop", size_hint_x=None, width=dp(80),
                               disabled=True, font_size=sp(14))
        self.stop_btn.bind(on_release=lambda *a: self._request_stop())
        for w in (self.preview_btn, self.run_btn, self.stop_btn):
            acts.add_widget(w)
        root.add_widget(acts)

        self.bar = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(8))
        root.add_widget(self.bar)
        self.status = self._text("", height=dp(40), color=theme.ACCENT)
        root.add_widget(self.status)

        root.add_widget(self._text("[b]Your backups[/b]", height=dp(24)))
        sv = ScrollView(do_scroll_x=False)
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                  spacing=dp(4))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        sv.add_widget(self.list_box)
        root.add_widget(sv)

        self._refresh_all()

    # ── small builders ───────────────────────────────────────────────────
    @staticmethod
    def _text(text, height=dp(24), color=None):
        lbl = Label(text=text, markup=True, font_size=sp(13), halign="left",
                    valign="middle", size_hint_y=None, height=height,
                    color=color or theme.TEXT)
        lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        return lbl

    def _folder_row(self, root, caption, handler):
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
            write_json_atomic(_cfg_path(), {"source": self.source,
                                            "dest": self.dest, "kind": self.kind,
                                            "verify": self.verify_cb.active})
        except Exception:
            pass

    def _set_kind(self, k):
        self.kind = k
        self._plan = None
        self.help_lbl.text = bc.KIND_HELP[k]
        self._save_cfg()

    def _refresh_all(self):
        self.src_lbl.text = self.source or "(none chosen)"
        self.dst_lbl.text = self.dest or "(none chosen)"
        self.help_lbl.text = bc.KIND_HELP[self.kind]
        self._refresh_list()

    def _set_busy(self, busy):
        self._busy = busy
        self.preview_btn.disabled = busy
        self.run_btn.disabled = busy
        self.stop_btn.disabled = not busy

    def _say(self, text):
        self.status.text = text

    # ── choosing folders ─────────────────────────────────────────────────
    def _pick_folder(self, title, start, on_pick):
        pick_folder(title, start, on_pick)

    def _pick_source(self):
        def done(f):
            self.source = f
            self._plan = None
            self._save_cfg()
            self._refresh_all()
        self._pick_folder("Folder to back up", self.source, done)

    def _pick_dest(self):
        def done(f):
            self.dest = f
            self._plan = None
            self._save_cfg()
            self._refresh_all()
        self._pick_folder("Where should the backups go?", self.dest, done)

    # ── preview / run ────────────────────────────────────────────────────
    def _problem(self):
        return bc.check_folders(self.source, self.dest)

    def preview(self):
        if self._busy:
            return
        problem = self._problem()
        if problem:
            self._say(problem)
            return
        self._set_busy(True)
        self._say("Looking at the folder...")
        src, dst, kind = self.source, self.dest, self.kind

        def work():
            try:
                plan = bc.make_plan(src, dst, kind)
                Clock.schedule_once(lambda dt: self._preview_done(plan))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._failed(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _preview_done(self, plan):
        self._set_busy(False)
        self._plan = plan
        lines = [f"{bc.KIND_LABELS[plan.kind]} backup: {len(plan.to_copy)} of "
                 f"{plan.total_files} files to copy ({bc.fmt_size(plan.bytes)}), "
                 f"{plan.unchanged} unchanged."]
        if plan.removed:
            lines.append(f"{plan.removed} file(s) are gone from the folder "
                         f"since then; older backups keep them.")
        if plan.note:
            lines.append(plan.note)
        self._say("\n".join(lines))

    def run(self):
        if self._busy:
            return
        problem = self._problem()
        if problem:
            self._say(problem)
            return
        self._set_busy(True)
        self._stop = False
        self.bar.value = 0
        self._save_cfg()
        src, dst, kind, verify = self.source, self.dest, self.kind, self.verify_cb.active
        self._say("Starting...")

        def progress(done, total, rel):
            Clock.schedule_once(lambda dt: self._progress(done, total, rel))

        def work():
            try:
                res = bc.run_backup(src, dst, kind, verify=verify,
                                    progress=progress, stop=lambda: self._stop)
                Clock.schedule_once(lambda dt: self._run_done(res))
            except Exception as e:
                Clock.schedule_once(lambda dt: self._failed(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _progress(self, done, total, rel):
        self.bar.max = max(1, total)
        self.bar.value = done
        if total:
            self._say(f"Copying {done}/{total}  {rel}")

    def _request_stop(self):
        self._stop = True
        self.stop_btn.disabled = True
        self._say("Stopping... (nothing half-finished is kept)")

    def _failed(self, msg):
        self._set_busy(False)
        self._say(f"Something went wrong: {msg}")

    def _run_done(self, res):
        self._set_busy(False)
        self._plan = None
        self.bar.value = 0
        if res.stopped:
            self._say("Stopped. That backup was removed, earlier ones are untouched.")
        elif res.error:
            self._say(res.error)
        else:
            text = (f"Done: {bc.KIND_LABELS[res.kind]} backup, {res.copied} "
                    f"file(s), {bc.fmt_size(res.bytes)}.")
            if res.note:
                text += " " + res.note
            if res.failed:
                text += (f"\n{len(res.failed)} file(s) could not be copied "
                         f"(e.g. {res.failed[0][0]}: {res.failed[0][1]}). "
                         f"They are tried again next time.")
            self._say(text)
        self._refresh_list()

    # ── list of backups, restore, delete ─────────────────────────────────
    def _set_dir(self):
        if not (self.source and self.dest and os.path.isdir(self.dest)):
            return None
        return bc.set_dir_for(self.dest, self.source)

    def _refresh_list(self):
        self.list_box.clear_widgets()
        sd = self._set_dir()
        backups = bc.list_backups(sd) if sd else []
        if not backups:
            self.list_box.add_widget(self._text(
                "No backups yet for this folder and place.", color=theme.MUTED))
            return
        for b in reversed(backups):
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
            info = (f"{b['created']}  [b]{bc.KIND_LABELS.get(b['kind'], b['kind'])}[/b]"
                    f"\n{b['files']} files, {b['copied']} copied "
                    f"({bc.fmt_size(b['bytes'])})"
                    + ("  verified" if b["verified"] else ""))
            lbl = Label(text=info, markup=True, font_size=sp(12), halign="left",
                        valign="middle")
            lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
            row.add_widget(lbl)
            rb = Button(text="Restore", size_hint_x=None, width=dp(84),
                        font_size=sp(12))
            rb.bind(on_release=lambda inst, n=b["name"]: self._restore(n))
            db = Button(text="Delete", size_hint_x=None, width=dp(70),
                        font_size=sp(12))
            db.bind(on_release=lambda inst, n=b["name"]: self._delete(n))
            row.add_widget(rb)
            row.add_widget(db)
            self.list_box.add_widget(row)

    def _restore(self, name):
        if self._busy:
            return
        sd = self._set_dir()
        if not sd:
            return

        def go(target):
            self._set_busy(True)
            self._stop = False
            self._say("Restoring...")

            def progress(done, total, rel):
                Clock.schedule_once(lambda dt: self._progress(done, total, rel))

            def work():
                try:
                    res = bc.run_restore(sd, name, target, progress=progress,
                                         stop=lambda: self._stop)
                    Clock.schedule_once(lambda dt: self._restore_done(res, target))
                except Exception as e:
                    Clock.schedule_once(lambda dt: self._failed(str(e)))

            threading.Thread(target=work, daemon=True).start()

        self._pick_folder("Restore into this folder (files already there "
                          "are kept)", self.dest, go)

    def _restore_done(self, res, target):
        self._set_busy(False)
        self.bar.value = 0
        if res.error:
            self._say(res.error)
        elif res.stopped:
            self._say("Restore stopped. Files already restored stay in the folder.")
        else:
            text = f"Restored {res.restored} file(s) into {target}."
            if res.skipped:
                text += f" {len(res.skipped)} already there, left untouched."
            if res.failed:
                text += f" {len(res.failed)} could not be restored."
            self._say(text)

    def _delete(self, name):
        sd = self._set_dir()
        if not sd:
            return
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        box.add_widget(Label(text=f"Delete this backup?\n{name}\n"
                                  f"The folder you backed up is not touched.",
                             halign="center", font_size=sp(13)))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        yes, no = Button(text="Delete"), Button(text="Keep it")
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        popup = Popup(title="Delete backup", content=box, size_hint=(0.8, 0.4))
        no.bind(on_release=lambda *a: popup.dismiss())

        def _do(*a):
            popup.dismiss()
            ok, msg = bc.delete_backup(sd, name)
            self._say(msg)
            self._refresh_list()

        yes.bind(on_release=_do)
        popup.open()
