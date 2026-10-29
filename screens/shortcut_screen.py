# screens/shortcut_screen.py - Linux shortcut creator: fill in a form, get a
# .desktop launcher in the application menu (and optionally on the Desktop).
# The file format and the install/remove rules live in core/desktop_entry.py.

import os
import shlex

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from core import desktop_entry as D
from core.tickbox import TickBox
from screens.dialogs import confirm_popup, message_popup


def _home():
    return os.path.expanduser("~")


def _srboli_command():
    """The command that starts this very app, and its logo if there is one."""
    from core.daemon_ipc import ui_launch_cmd, _app_root
    logo = os.path.join(_app_root(), "logo.png")
    return ui_launch_cmd(), (logo if os.path.isfile(logo) else "")


class ShortcutScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._editing = None          # file name of the launcher being edited
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        root.add_widget(Label(text="[b]Linux shortcut creator[/b]", markup=True,
                              size_hint_y=None, height=dp(32), font_size=18))

        if not D.is_supported():
            root.add_widget(Label(
                text="Shortcuts (.desktop launchers) are a Linux desktop feature,\n"
                     "so this tool only works on Linux."))
            root.add_widget(self._back_button())
            self.add_widget(root)
            return

        sv = ScrollView()
        form = BoxLayout(orientation="vertical", spacing=dp(6),
                         size_hint_y=None, padding=(0, 0, dp(6), 0))
        form.bind(minimum_height=form.setter("height"))

        def field(label, hint="", extra=None):
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
            row.add_widget(Label(text=label, size_hint_x=None, width=dp(86),
                                 font_size=13, halign="right"))
            ti = TextInput(multiline=False, font_size=14, hint_text=hint)
            row.add_widget(ti)
            for text, cb in extra or ():
                b = Button(text=text, font_size=12, size_hint_x=None,
                           width=dp(76))
                b.bind(on_release=cb)
                row.add_widget(b)
            form.add_widget(row)
            return ti

        self._name = field("Name", "What it is called in the menu")
        self._cmd = field("Command", "e.g. firefox  or  python3 /path/script.py",
                          [("This app", self._fill_this_app),
                           ("Browse", self._browse_command)])
        self._comment = field("Comment", "Optional tooltip")
        self._icon = field("Icon", "Image path or an icon name (optional)",
                           [("Browse", self._browse_icon)])
        self._path = field("Run in", "Working folder (optional)")

        form.add_widget(Label(text="Categories (where it shows in the menu)",
                              size_hint_y=None, height=dp(24), font_size=12,
                              halign="left"))
        grid = GridLayout(cols=4, spacing=dp(3), size_hint_y=None,
                          height=dp(36) * ((len(D.CATEGORIES) + 3) // 4))
        self._cats = {}
        for cat in D.CATEGORIES:
            tb = ToggleButton(text=cat, font_size=11,
                              state="down" if cat == "Utility" else "normal")
            self._cats[cat] = tb
            grid.add_widget(tb)
        form.add_widget(grid)

        opts = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self._terminal = TickBox("Run in a terminal", width=dp(150))
        self._on_desktop = TickBox("Also put on the Desktop", width=dp(190))
        opts.add_widget(self._terminal)
        opts.add_widget(self._on_desktop)
        form.add_widget(opts)

        acts = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        for text, cb in (("Preview", self._preview), ("Create shortcut", self._create),
                         ("New", self._clear)):
            b = Button(text=text, font_size=13)
            b.bind(on_release=cb)
            acts.add_widget(b)
        form.add_widget(acts)

        self._status = Label(text="", font_size=12, size_hint_y=None,
                             height=dp(60), halign="left", valign="top")
        self._status.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
        form.add_widget(self._status)
        sv.add_widget(form)
        root.add_widget(sv)

        bottom = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        mine = Button(text="My shortcuts", font_size=13)
        mine.bind(on_release=self._show_mine)
        bottom.add_widget(mine)
        bottom.add_widget(self._back_button())
        root.add_widget(bottom)
        self.add_widget(root)

    def _back_button(self):
        b = Button(text="< Back", size_hint_y=None, height=dp(44))
        b.bind(on_release=lambda *a: setattr(self.manager, "current", "dashboard"))
        return b

    # ── form <-> entry ────────────────────────────────────────────────────
    def _argv(self):
        """The command box parsed like a terminal would (quotes work)."""
        return shlex.split(self._cmd.text)

    def _fields(self):
        argv = self._argv()
        cats = [c for c, tb in self._cats.items() if tb.state == "down"]
        return dict(name=self._name.text, argv=argv, comment=self._comment.text,
                    icon=self._icon.text, terminal=self._terminal.active,
                    categories=cats, path=self._path.text)

    def _load(self, entry, filename):
        self._editing = filename
        self._name.text = entry["name"]
        self._cmd.text = " ".join(shlex.quote(a) for a in entry["argv"])
        self._comment.text = entry["comment"]
        self._icon.text = entry["icon"]
        self._path.text = entry["path"]
        self._terminal.active = entry["terminal"]
        for cat, tb in self._cats.items():
            tb.state = "down" if cat in entry["categories"] else "normal"
        self._status.text = f"Editing {filename}. Create shortcut saves over it."

    def _clear(self, *a):
        self._editing = None
        for ti in (self._name, self._cmd, self._comment, self._icon, self._path):
            ti.text = ""
        self._terminal.active = self._on_desktop.active = False
        for cat, tb in self._cats.items():
            tb.state = "down" if cat == "Utility" else "normal"
        self._status.text = ""

    # ── helpers that fill fields ──────────────────────────────────────────
    def _fill_this_app(self, *a):
        cmd, logo = _srboli_command()
        self._cmd.text = " ".join(shlex.quote(c) for c in cmd)
        if not self._name.text.strip():
            self._name.text = "Srboli"
        if not self._icon.text.strip() and logo:
            self._icon.text = logo
        if not self._comment.text.strip():
            self._comment.text = "Pocket swiss-army-knife of small tools"

    def _choose_file(self, title, button, filters, on_pick):
        chooser = FileChooserIconView(path=_home(), filters=filters)
        btn = Button(text=button, size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title=title, content=layout, size_hint=(0.92, 0.92))

        def _do(*a):
            if chooser.selection:
                on_pick(chooser.selection[0])
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _browse_command(self, *a):
        self._choose_file("Choose a program or script", "Use this file", [],
                          lambda p: setattr(self._cmd, "text", shlex.quote(p)))

    def _browse_icon(self, *a):
        self._choose_file("Choose an icon", "Use this image",
                          ["*.png", "*.svg", "*.jpg", "*.jpeg", "*.ico", "*.xpm"],
                          lambda p: setattr(self._icon, "text", p))

    # ── preview / create ──────────────────────────────────────────────────
    def _entry_text(self):
        """(file text, problems) or (None, message) if the form is unusable."""
        try:
            f = self._fields()
        except ValueError:
            return None, "The command has an unclosed quote."
        errors, warnings = D.validate(f["name"], f["argv"], f["icon"], f["path"])
        if errors:
            return None, " ".join(errors)
        return D.build_entry(f["name"], f["argv"], f["comment"], f["icon"],
                             f["terminal"], f["categories"], f["path"]), warnings

    def _preview(self, *a):
        text, problems = self._entry_text()
        if text is None:
            message_popup("Can't preview yet", problems)
            return
        box = TextInput(text=text, readonly=True, font_name="RobotoMono-Regular",
                        font_size=12)
        Popup(title="This is the file that will be written", content=box,
              size_hint=(0.92, 0.7)).open()

    def _create(self, *a):
        text, problems = self._entry_text()
        if text is None:
            self._status.text = problems
            return
        filename = self._editing or D.filename_for(self._name.text)

        def write():
            paths, err = D.install(text, filename, self._on_desktop.active)
            if err:
                self._status.text = f"Problem: {err}"
                return
            self._editing = filename
            note = ("  Note: " + " ".join(problems)) if problems else ""
            self._status.text = ("Created: " + ", ".join(paths)
                                 + "\nIt can take a few seconds to appear in the "
                                   "menu." + note)

        if D.exists(filename) and self._editing != filename:
            confirm_popup("Replace shortcut",
                          f"{filename} already exists. Replace it?", write,
                          yes_text="Replace")
        else:
            write()

    # ── existing shortcuts ────────────────────────────────────────────────
    def _show_mine(self, *a):
        items = D.list_created()
        box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(6))
        pop = Popup(title="Shortcuts made with Srboli", content=box,
                    size_hint=(0.92, 0.8))
        if not items:
            box.add_widget(Label(text="None yet."))
        sv = ScrollView()
        col = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        col.bind(minimum_height=col.setter("height"))
        for path, entry in items:
            fn = os.path.basename(path)
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
            row.add_widget(Label(text=entry["name"] or fn, halign="left",
                                 shorten=True, shorten_from="right"))
            edit = Button(text="Edit", size_hint_x=None, width=dp(64))
            dele = Button(text="Delete", size_hint_x=None, width=dp(74))
            edit.bind(on_release=lambda inst, e=entry, f=fn: (pop.dismiss(),
                                                              self._load(e, f)))
            dele.bind(on_release=lambda inst, f=fn, n=entry["name"]:
                      (pop.dismiss(), self._delete(f, n)))
            row.add_widget(edit)
            row.add_widget(dele)
            col.add_widget(row)
        sv.add_widget(col)
        box.add_widget(sv)
        close = Button(text="Close", size_hint_y=None, height=dp(44))
        close.bind(on_release=lambda *a: pop.dismiss())
        box.add_widget(close)
        pop.open()

    def _delete(self, filename, name):
        def do():
            ok, err = D.delete(filename)
            self._status.text = (f"Deleted {name or filename}." if ok
                                 else f"Couldn't delete: {err}")
            if ok and self._editing == filename:
                self._editing = None
        confirm_popup("Delete shortcut",
                      f"Delete the shortcut '{name or filename}'?", do)
