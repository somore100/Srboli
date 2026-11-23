# screens/cleanup_screen.py - Cleanup: scan for junk files (caches, temp files, thumbnails,
# optionally the Trash), look at exactly what would go, then remove it; and see which
# programs use the most memory. Nothing is deleted without a scan, a preview option and a
# confirmation. Logic and safety rules: core/cleanup_core.py.
import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView

import app_data
from core import cleanup_core as core
from core import theme
from screens.scaffold import ToolScreen

try:
    import psutil
except Exception:                                   # Android: no psutil
    psutil = None

OFF = (0.25, 0.25, 0.25, 1)


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))


def _label(text="", size=12, color=None, h=None, halign="left"):
    lb = Label(text=text, font_size=sp(size), halign=halign, valign="middle", markup=True,
               **({"color": color} if color else {}))
    if h:
        lb.size_hint_y = None
        lb.height = dp(h)
    lb.bind(size=lambda w, v: setattr(w, "text_size", v))
    return lb


def _own_cache_dirs():
    try:
        return [p for p in (__import__("os").path.join(app_data.get_data_dir(), n)
                            for n in app_data.CACHE_DIRS)]
    except Exception:
        return []


class CleanupScreen(ToolScreen):
    title = "Cleanup"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tab = "junk"
        self.results = []
        self.sel = {}
        self._busy = False
        self._cancel = False

        tabs = _row()
        self.tab_btns = {}
        for key, label in (("junk", "Junk files"), ("memory", "Memory")):
            b = Button(text=label, font_size=sp(13))
            b.bind(on_release=lambda *a, k=key: self.set_tab(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        self.body.add_widget(tabs)
        self.holder = BoxLayout()
        self.body.add_widget(self.holder)
        self._build_junk()
        self._build_memory()
        self.set_tab("junk")

    def set_tab(self, tab):
        self.tab = tab
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == tab else OFF
        self.holder.clear_widgets()
        self.holder.add_widget(self.junk_panel if tab == "junk" else self.mem_panel)
        if tab == "memory":
            self.refresh_memory()

    # =============== junk ===============
    def _build_junk(self):
        p = BoxLayout(orientation="vertical", spacing=dp(4))
        p.add_widget(_label("Step 1: scan. Step 2: look at what was found (Preview). Step 3: "
                            "clean the ones you tick. Your own documents, downloads and "
                            "pictures are never touched.", 11, theme.MUTED, h=48))
        self.scan_btn = Button(text="Scan for junk", size_hint_y=None, height=dp(44),
                               font_size=sp(14))
        self.scan_btn.bind(on_release=lambda *a: self.scan())
        p.add_widget(self.scan_btn)
        self.progress = _label("", 11, theme.MUTED, h=20)
        p.add_widget(self.progress)
        sv = ScrollView(do_scroll_x=False)
        self.list = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.list.bind(minimum_height=self.list.setter("height"))
        sv.add_widget(self.list)
        p.add_widget(sv)
        self.total = _label("", 13, h=26)
        p.add_widget(self.total)
        self.clean_btn = Button(text="Clean the ticked items", size_hint_y=None, height=dp(46),
                                font_size=sp(14), disabled=True)
        self.clean_btn.bind(on_release=lambda *a: self.confirm_clean())
        p.add_widget(self.clean_btn)
        self.status = _label("", 12, theme.MUTED, h=40)
        p.add_widget(self.status)
        self.junk_panel = p

    def scan(self):
        if self._busy:
            return
        self._busy = True
        self._cancel = False
        self.scan_btn.disabled = True
        self.clean_btn.disabled = True
        self.status.text = ""
        cats = core.categories(own_cache_dirs=_own_cache_dirs())
        if not cats:
            self._busy = False
            self.scan_btn.disabled = False
            self.status.text = "There is nothing this tool can safely clean on this device."
            return
        self.results, self.sel = [], {}

        def prog(i, n, label):
            Clock.schedule_once(lambda dt: setattr(self.progress, "text",
                                                   f"Scanning {label} ({i + 1}/{n})..."), 0)

        def work():
            res = core.scan(cats, cancel=lambda: self._cancel, progress=prog)
            Clock.schedule_once(lambda dt: self._scan_done(res), 0)

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, res):
        self._busy = False
        self.scan_btn.disabled = False
        self.progress.text = ""
        self.results = res
        self.sel = {r["key"]: r["default_on"] and r["total"] > 0 for r in res}
        self.draw_results()

    def draw_results(self):
        self.list.clear_widgets()
        for r in self.results:
            row = _row(58)
            on = self.sel.get(r["key"], False)
            tg = Button(text="On" if on else "Off", size_hint_x=None, width=dp(52),
                        font_size=sp(12), background_color=theme.ACCENT if on else OFF,
                        disabled=r["total"] == 0)
            tg.bind(on_release=lambda *a, k=r["key"]: self.toggle(k))
            row.add_widget(tg)
            more = "+" if r["truncated"] else ""
            row.add_widget(_label(
                f"[b]{r['label']}[/b]\n{core.human(r['total'])}, {len(r['files'])}{more} files\n"
                f"[color=9aa0ad]{r['note']}[/color]", 11))
            pv = Button(text="Preview", size_hint_x=None, width=dp(74), font_size=sp(11),
                        disabled=not r["files"])
            pv.bind(on_release=lambda *a, rr=r: self.preview(rr))
            row.add_widget(pv)
            self.list.add_widget(row)
        if not self.results:
            self.list.add_widget(_label("Nothing scanned.", 12, theme.MUTED, h=30))
        self._sync_total()

    def toggle(self, key):
        self.sel[key] = not self.sel.get(key)
        self.draw_results()

    def _selected(self):
        return [r for r in self.results if self.sel.get(r["key"]) and r["files"]]

    def _sync_total(self):
        chosen = self._selected()
        size = sum(r["total"] for r in chosen)
        count = sum(len(r["files"]) for r in chosen)
        self.total.text = (f"Selected: {core.human(size)} in {count} files" if chosen
                           else "Nothing selected.")
        self.clean_btn.disabled = not chosen or self._busy

    def preview(self, r):
        files = sorted(r["files"], key=lambda f: f[1], reverse=True)[:150]
        text = "\n".join(f"{core.human(s):>9}  {p}" for p, s in files)
        if len(r["files"]) > len(files):
            text += f"\n... and {len(r['files']) - len(files)} more (smaller) files"
        lb = Label(text=text, font_size=sp(10), halign="left", valign="top", size_hint_y=None,
                   markup=False)
        lb.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        lb.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(10)))
        sv = ScrollView(do_scroll_x=False)
        sv.add_widget(lb)
        close = Button(text="Close", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(_label(f"Biggest files in: {r['root']}", 11, theme.MUTED, h=22))
        lay.add_widget(sv)
        lay.add_widget(close)
        pop = Popup(title=r["label"], content=lay, size_hint=(0.95, 0.9))
        close.bind(on_release=lambda *a: pop.dismiss())
        pop.open()

    def confirm_clean(self):
        chosen = self._selected()
        if not chosen:
            return
        size = core.human(sum(r["total"] for r in chosen))
        count = sum(len(r["files"]) for r in chosen)
        names = ", ".join(r["label"] for r in chosen)
        warn = "\n[color=e05555]This permanently deletes the Trash.[/color]" if any(
            r["key"] == "trash" for r in chosen) else ""
        go = Button(text=f"Delete {size}")
        no = Button(text="Cancel")
        row = _row(46)
        row.add_widget(no)
        row.add_widget(go)
        lay = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        lay.add_widget(_label(f"Delete {count} files ({size}) from:\n{names}\n\n"
                              f"This cannot be undone.{warn}", 12))
        lay.add_widget(row)
        pop = Popup(title="Clean these?", content=lay, size_hint=(0.88, 0.5))
        no.bind(on_release=lambda *a: pop.dismiss())
        go.bind(on_release=lambda *a: (pop.dismiss(), self.run_clean(chosen)))
        pop.open()

    def run_clean(self, chosen):
        if self._busy:
            return
        self._busy = True
        self.scan_btn.disabled = True
        self.clean_btn.disabled = True
        self.status.text = "Cleaning..."
        self.status.color = theme.MUTED

        def work():
            out = core.clean(chosen)
            Clock.schedule_once(lambda dt: self._clean_done(out), 0)

        threading.Thread(target=work, daemon=True).start()

    def _clean_done(self, out):
        self._busy = False
        self.scan_btn.disabled = False
        extra = ""
        if out["failed"] or out["skipped"]:
            extra = f" ({out['skipped']} skipped as in use or changed, {out['failed']} failed)"
        self.status.text = f"Freed {core.human(out['freed'])}: {out['deleted']} files removed{extra}."
        self.status.color = theme.SUCCESS
        self.results, self.sel = [], {}
        self.draw_results()

    # =============== memory ===============
    def _build_memory(self):
        p = BoxLayout(orientation="vertical", spacing=dp(4))
        self.mem_info = _label("", 13, h=48)
        p.add_widget(self.mem_info)
        self.mem_bar = ProgressBar(max=100, value=0, size_hint_y=None, height=dp(10))
        p.add_widget(self.mem_bar)
        row = _row()
        free = Button(text="Free Srboli's own memory", font_size=sp(12))
        free.bind(on_release=lambda *a: self.free_own())
        ref = Button(text="Refresh", font_size=sp(12), size_hint_x=0.4)
        ref.bind(on_release=lambda *a: self.refresh_memory())
        row.add_widget(free)
        row.add_widget(ref)
        p.add_widget(row)
        p.add_widget(_label("Biggest programs of yours. Closing one asks it to quit politely "
                            "(unsaved work in it may be lost). System programs are protected.",
                            11, theme.MUTED, h=44))
        sv = ScrollView(do_scroll_x=False)
        self.procs = GridLayout(cols=1, spacing=dp(3), size_hint_y=None)
        self.procs.bind(minimum_height=self.procs.setter("height"))
        sv.add_widget(self.procs)
        p.add_widget(sv)
        self.mem_status = _label("", 12, theme.MUTED, h=30)
        p.add_widget(self.mem_status)
        self.mem_panel = p

    def refresh_memory(self):
        self.procs.clear_widgets()
        if psutil is None:
            self.mem_info.text = ("Android decides by itself which apps stay in memory, and an "
                                  "app may not close others. Use the phone's Settings > Battery "
                                  "or Device care to free memory.")
            return
        try:
            vm = psutil.virtual_memory()
            self.mem_info.text = (f"Memory in use: {core.human(vm.total - vm.available)} of "
                                  f"{core.human(vm.total)} ({vm.percent:.0f}%)")
            self.mem_bar.value = vm.percent
            for pr in core.top_processes(psutil, 15):
                row = _row(34)
                row.add_widget(_label(f"{pr['name']}   [color=9aa0ad]{core.human(pr['rss'])}[/color]", 12))
                b = Button(text="Protected" if pr["protected"] else "Close", size_hint_x=None,
                           width=dp(86), font_size=sp(11), disabled=pr["protected"])
                b.bind(on_release=lambda *a, d=pr: self.confirm_close(d))
                row.add_widget(b)
                self.procs.add_widget(row)
        except Exception as e:
            self.mem_info.text = f"Could not read memory use: {e}"

    def free_own(self):
        n = core.free_own_memory()
        self.mem_status.text = f"Srboli released unused memory ({n} objects)."

    def confirm_close(self, pr):
        go = Button(text=f"Close {pr['name']}")
        no = Button(text="Cancel")
        row = _row(46)
        row.add_widget(no)
        row.add_widget(go)
        lay = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        lay.add_widget(_label(f"Ask {pr['name']} ({core.human(pr['rss'])}) to close?\n"
                              "Unsaved work in it may be lost.", 12))
        lay.add_widget(row)
        pop = Popup(title="Close this program?", content=lay, size_hint=(0.85, 0.4))
        no.bind(on_release=lambda *a: pop.dismiss())

        def do(*a):
            pop.dismiss()
            ok, msg = core.close_process(psutil, pr["pid"])
            self.mem_status.text = msg
            self.mem_status.color = theme.SUCCESS if ok else theme.DANGER
            Clock.schedule_once(lambda dt: self.refresh_memory(), 1.0)

        go.bind(on_release=do)
        pop.open()
