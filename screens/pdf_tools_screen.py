# screens/pdf_tools_screen.py - PDF Tools: merge PDFs into one, or split one apart (every
# page, N pages per file, or pick pages into a new file). Originals are never changed:
# results go to a "srboli_pdf" folder next to the first file. Logic: core/pdf_tools_core.py.
import os
import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from core import pdf_tools_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)
SPLIT_MODES = {"One file per page": "each", "N pages per file": "chunks",
               "Pick pages into a new file": "pick"}


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))


class PDFToolsScreen(ToolScreen):
    title = "PDF Tools"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mode = "merge"
        self.paths = []
        self.pages = {}              # path -> page count (or None if unreadable)
        self._running = False

        tabs = _row()
        self.tab_btns = {}
        for key, label in (("merge", "Merge PDFs into one"), ("split", "Split / extract pages")):
            b = Button(text=label, font_size=sp(12))
            b.bind(on_release=lambda *a, k=key: self.set_mode(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        self.body.add_widget(tabs)

        r = _row()
        add = Button(text="Add PDFs", font_size=sp(13))
        add.bind(on_release=lambda *a: self.choose())
        clr = Button(text="Clear list", font_size=sp(13), size_hint_x=None, width=dp(100))
        clr.bind(on_release=lambda *a: self.clear())
        r.add_widget(add)
        r.add_widget(clr)
        self.body.add_widget(r)

        sv = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=1, spacing=dp(3), size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        sv.add_widget(self.grid)
        self.body.add_widget(sv)

        self.opts = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.opts.bind(minimum_height=self.opts.setter("height"))
        self.body.add_widget(self.opts)
        self.split_sp = Spinner(text="One file per page", values=list(SPLIT_MODES),
                                font_size=sp(12), size_hint_y=None, height=dp(38))
        self.split_sp.bind(text=lambda *a: self._sync_opts())
        self.chunk_sp = Spinner(text="2 pages", values=[f"{n} pages" for n in (2, 3, 5, 10, 20)],
                                font_size=sp(12), size_hint_y=None, height=dp(38))
        self.range_in = TextInput(hint_text="Pages to keep, e.g. 1-3, 5, 8-", multiline=False,
                                  size_hint_y=None, height=dp(38), font_size=sp(14))

        self.run_btn = Button(text="Start", size_hint_y=None, height=dp(46), font_size=sp(15))
        self.run_btn.bind(on_release=lambda *a: self.run())
        self.body.add_widget(self.run_btn)
        self.status = Label(text="", font_size=sp(12), color=theme.MUTED, size_hint_y=None,
                            height=dp(54), halign="center", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.status)
        self.set_mode("merge")
        self.refresh()

    # ----- layout of options -----
    def set_mode(self, mode):
        self.mode = mode
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == mode else OFF
        self._sync_opts()
        self.refresh()

    def _sync_opts(self):
        for w in (self.split_sp, self.chunk_sp, self.range_in):
            if w.parent is not None:
                w.parent.remove_widget(w)
        self.opts.clear_widgets()
        if self.mode == "merge":
            self.run_btn.text = "Merge into one PDF"
            return
        self.opts.add_widget(self.split_sp)
        how = SPLIT_MODES[self.split_sp.text]
        if how == "chunks":
            self.opts.add_widget(self.chunk_sp)
        elif how == "pick":
            self.opts.add_widget(self.range_in)
        self.run_btn.text = ("Extract the pages" if how == "pick" else "Split")

    # ----- the list -----
    def choose(self):
        start = os.path.expanduser("~")
        try:
            from core.android_storage import shared_storage_root
            start = shared_storage_root() or start
        except Exception:
            pass
        multi = self.mode == "merge"
        chooser = FileChooserListView(
            path=start, multiselect=multi,
            filters=[lambda folder, f: os.path.isdir(os.path.join(folder, f)) or core.is_pdf(f)])
        use = Button(text="Add the selected PDFs" if multi else "Use this PDF",
                     size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Select PDFs" + (" (tap several)" if multi else ""), content=lay,
                    size_hint=(0.95, 0.95))

        def _use(*a):
            pop.dismiss()
            self.add_paths([p for p in chooser.selection if os.path.isfile(p)])

        use.bind(on_release=_use)
        pop.open()

    def add_paths(self, paths):
        if self.mode == "split":
            self.paths = []                     # split works on one PDF
            paths = paths[:1]
        for p in paths:
            if core.is_pdf(p) and p not in self.paths:
                self.paths.append(p)
                try:
                    self.pages[p] = core.page_count(p)
                except core.PDFError as e:
                    self.pages[p] = None
                    self.status.text = str(e)
                    self.status.color = theme.DANGER
        self.refresh()

    def clear(self):
        self.paths = []
        self.refresh()

    def move_up(self, i):
        if i > 0:
            self.paths[i - 1], self.paths[i] = self.paths[i], self.paths[i - 1]
            self.refresh()

    def remove(self, i):
        del self.paths[i]
        self.refresh()

    def refresh(self):
        self.grid.clear_widgets()
        if not self.paths:
            self.grid.add_widget(Label(text="No PDFs yet. Tap Add PDFs.", font_size=sp(13),
                                       color=theme.MUTED, size_hint_y=None, height=dp(60)))
            return
        for i, p in enumerate(self.paths):
            n = self.pages.get(p)
            info = "?" if n is None else f"{n} page{'s' if n != 1 else ''}"
            row = _row(34)
            lbl = Label(text=f"{i + 1}. {os.path.basename(p)}  ({info})", font_size=sp(12),
                        halign="left", valign="middle", shorten=True, shorten_from="right")
            lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
            row.add_widget(lbl)
            if self.mode == "merge":
                up = Button(text="Up", size_hint_x=None, width=dp(48), font_size=sp(11))
                up.bind(on_release=lambda *a, k=i: self.move_up(k))
                row.add_widget(up)
            rm = Button(text="X", size_hint_x=None, width=dp(40), font_size=sp(11))
            rm.bind(on_release=lambda *a, k=i: self.remove(k))
            row.add_widget(rm)
            self.grid.add_widget(row)

    # ----- running -----
    def run(self):
        if self._running:
            return
        if not self.paths:
            self.status.text = "Add a PDF first."
            self.status.color = theme.MUTED
            return
        if self.mode == "merge" and len(self.paths) < 2:
            self.status.text = "Add at least two PDFs to merge."
            self.status.color = theme.MUTED
            return
        how = SPLIT_MODES[self.split_sp.text]
        spec = {"how": how, "per": int(self.chunk_sp.text.split()[0]),
                "ranges": self.range_in.text}
        self._running = True
        self.run_btn.disabled = True
        self.status.text = "Working..."
        self.status.color = theme.MUTED
        threading.Thread(target=self._work, args=(list(self.paths), self.mode, spec),
                         daemon=True).start()

    def _work(self, paths, mode, spec):
        out_dir = core.out_dir_for(paths[0])
        try:
            if mode == "merge":
                out, n = core.merge(paths, out_dir)
                msg = f"Merged {len(paths)} PDFs, {n} pages:\n{out}"
            elif spec["how"] == "pick":
                out, n = core.extract(paths[0], spec["ranges"], out_dir)
                msg = f"Extracted {n} pages:\n{out}"
            else:
                per = 1 if spec["how"] == "each" else spec["per"]
                outs = core.split(paths[0], out_dir, per)
                msg = f"Made {len(outs)} PDFs in\n{out_dir}"
            ok = True
        except core.PDFError as e:
            msg, ok = str(e), False
        except Exception as e:
            msg, ok = f"Failed: {e}", False
        Clock.schedule_once(lambda dt: self._finish(msg, ok), 0)

    def _finish(self, msg, ok):
        self._running = False
        self.run_btn.disabled = False
        self.status.text = msg
        self.status.color = theme.SUCCESS if ok else theme.DANGER
