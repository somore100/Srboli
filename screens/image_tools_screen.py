# screens/image_tools_screen.py - Image Tools: shrink / compress / convert many pictures at
# once, or combine them into one image. Originals are never changed; results go to a
# "srboli_images" folder next to the first picture. Logic: core/image_tools_core.py.
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
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

from core import image_tools_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)
SIDES = {"Keep size": 0, "3840 px": 3840, "2560 px": 2560, "1920 px": 1920,
         "1280 px": 1280, "1024 px": 1024, "800 px": 800, "640 px": 640}
SIZES = {"800 px": 800, "1200 px": 1200, "1600 px": 1600, "2400 px": 2400, "3200 px": 3200}
GAPS = {"No gap": 0, "Small gap": 12, "Big gap": 40}
LAYOUT_NAMES = {"Stack (top to bottom)": "vertical", "Side by side": "horizontal",
                "Grid": "grid"}


def _put(row, *widgets):
    """Add widgets to a row, taking them out of their old row first."""
    for w in widgets:
        if w.parent is not None:
            w.parent.remove_widget(w)
        row.add_widget(w)
    return row


def _row(h=40):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))


class ImageToolsScreen(ToolScreen):
    title = "Image Tools"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mode = "each"
        self.paths = []
        self._running = False

        tabs = _row()
        self.tab_btns = {}
        for key, label in (("each", "Each file (shrink, compress, convert)"),
                           ("combine", "Combine into one image")):
            b = Button(text=label, font_size=sp(12))
            b.bind(on_release=lambda *a, k=key: self.set_mode(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        self.body.add_widget(tabs)

        r = _row()
        add = Button(text="Add pictures", font_size=sp(13))
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

        # options (shown depending on the mode)
        self.opts = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.opts.bind(minimum_height=self.opts.setter("height"))
        self.body.add_widget(self.opts)
        self.side_sp = Spinner(text="Keep size", values=list(SIDES), font_size=sp(12))
        self.fmt_sp = Spinner(text="Keep format", values=["Keep format", "JPG", "PNG", "WEBP"],
                              font_size=sp(12))
        self.layout_sp = Spinner(text="Stack (top to bottom)", values=list(LAYOUT_NAMES),
                                 font_size=sp(12))
        self.cols_sp = Spinner(text="2 columns", values=[f"{n} columns" for n in (2, 3, 4, 5)],
                               font_size=sp(12))
        self.gap_sp = Spinner(text="No gap", values=list(GAPS), font_size=sp(12))
        self.size_sp = Spinner(text="1600 px", values=list(SIZES), font_size=sp(12))
        self.cfmt_sp = Spinner(text="JPG", values=["JPG", "PNG"], font_size=sp(12))
        self.q_label = Label(text="", font_size=sp(12), size_hint_x=None, width=dp(110))
        self.q_slider = Slider(min=10, max=100, step=1, value=85)
        self.q_slider.bind(value=lambda *a: self._sync_q())

        self.run_btn = Button(text="Start", size_hint_y=None, height=dp(46), font_size=sp(15))
        self.run_btn.bind(on_release=lambda *a: self.run())
        self.body.add_widget(self.run_btn)
        self.status = Label(text="", font_size=sp(12), color=theme.MUTED, size_hint_y=None,
                            height=dp(54), halign="center", valign="middle")
        self.status.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(self.status)
        self._sync_q()
        self.set_mode("each")
        self.refresh()

    # ----- layout of options -----
    def set_mode(self, mode):
        self.mode = mode
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == mode else OFF
        self.opts.clear_widgets()
        if mode == "each":
            self.opts.add_widget(_put(_row(), self.side_sp, self.fmt_sp))
            self.run_btn.text = "Shrink / compress / convert"
        else:
            self.opts.add_widget(_put(_row(), self.layout_sp, self.cols_sp))
            self.opts.add_widget(_put(_row(), self.gap_sp, self.size_sp, self.cfmt_sp))
            self.run_btn.text = "Combine into one image"
        self.opts.add_widget(_put(_row(34), self.q_label, self.q_slider))

    def _sync_q(self):
        self.q_label.text = f"Quality {int(self.q_slider.value)}"

    # ----- the list -----
    def choose(self):
        start = os.path.expanduser("~")
        try:
            from core.android_storage import shared_storage_root
            start = shared_storage_root() or start
        except Exception:
            pass
        pics = os.path.join(start, "Pictures")
        chooser = FileChooserListView(path=pics if os.path.isdir(pics) else start,
                                      multiselect=True,
                                      filters=[lambda folder, f: os.path.isdir(os.path.join(folder, f))
                                               or core.is_image(f)])
        use = Button(text="Add the selected pictures", size_hint_y=None, height=dp(44))
        lay = BoxLayout(orientation="vertical")
        lay.add_widget(chooser)
        lay.add_widget(use)
        pop = Popup(title="Select pictures (tap several)", content=lay, size_hint=(0.95, 0.95))

        def _use(*a):
            pop.dismiss()
            self.add_paths([p for p in chooser.selection if os.path.isfile(p)])

        use.bind(on_release=_use)
        pop.open()

    def add_paths(self, paths):
        for p in paths:
            if core.is_image(p) and p not in self.paths:
                self.paths.append(p)
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
            self.grid.add_widget(Label(text="No pictures yet. Tap Add pictures.",
                                       font_size=sp(13), color=theme.MUTED,
                                       size_hint_y=None, height=dp(60)))
            return
        for i, p in enumerate(self.paths):
            row = _row(34)
            lbl = Label(text=f"{i + 1}. {os.path.basename(p)}", font_size=sp(12),
                        halign="left", valign="middle", shorten=True, shorten_from="right")
            lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
            up = Button(text="Up", size_hint_x=None, width=dp(48), font_size=sp(11))
            up.bind(on_release=lambda *a, n=i: self.move_up(n))
            rm = Button(text="X", size_hint_x=None, width=dp(40), font_size=sp(11))
            rm.bind(on_release=lambda *a, n=i: self.remove(n))
            for w in (lbl, up, rm):
                row.add_widget(w)
            self.grid.add_widget(row)

    # ----- running -----
    def settings(self):
        fmt = self.fmt_sp.text
        return {"max_side": SIDES[self.side_sp.text],
                "fmt": "keep" if fmt == "Keep format" else fmt,
                "quality": int(self.q_slider.value),
                "layout": LAYOUT_NAMES[self.layout_sp.text],
                "cols": int(self.cols_sp.text.split()[0]),
                "gap": GAPS[self.gap_sp.text], "size": SIZES[self.size_sp.text],
                "cfmt": self.cfmt_sp.text}

    def run(self):
        if self._running:
            return
        if not self.paths:
            self.status.text = "Add some pictures first."
            return
        if self.mode == "combine" and len(self.paths) < 2:
            self.status.text = "Add at least two pictures to combine."
            return
        self._running = True
        self.run_btn.disabled = True
        self.status.text = "Working..."
        self.status.color = theme.MUTED
        paths, s, mode = list(self.paths), self.settings(), self.mode
        threading.Thread(target=self._work, args=(paths, s, mode), daemon=True).start()

    def _work(self, paths, s, mode):
        out_dir = core.out_dir_for(paths[0])
        try:
            if mode == "combine":
                out, size = core.combine_files(paths, out_dir, s["layout"], s["cols"],
                                               s["gap"], (255, 255, 255), s["size"],
                                               s["cfmt"], s["quality"])
                msg, ok = f"Combined {len(paths)} pictures ({core.human(size)}):\n{out}", True
            else:
                before = after = done = 0
                errors = []
                for p in paths:
                    try:
                        _o, b, a = core.process_file(p, out_dir, s["max_side"], s["fmt"],
                                                     s["quality"])
                        before += b
                        after += a
                        done += 1
                    except Exception as e:
                        errors.append(f"{os.path.basename(p)}: {e}")
                    Clock.schedule_once(
                        lambda dt, d=done: setattr(self.status, "text",
                                                   f"Working... {d}/{len(paths)}"), 0)
                msg = (f"{done} of {len(paths)} done: {core.human(before)} -> "
                       f"{core.human(after)}\nSaved in {out_dir}")
                ok = not errors
                if errors:
                    msg += "\nProblems: " + "; ".join(errors[:2])
        except Exception as e:
            msg, ok = f"Failed: {e}", False
        Clock.schedule_once(lambda dt: self._finish(msg, ok), 0)

    def _finish(self, msg, ok):
        self._running = False
        self.run_btn.disabled = False
        self.status.text = msg
        self.status.color = theme.SUCCESS if ok else theme.DANGER
