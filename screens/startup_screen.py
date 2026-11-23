# screens/startup_screen.py - Startup Manager: which apps start when you log in.
# Switch an entry off (or back on). Nothing is deleted. Logic: core/startup_core.py.
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from core import startup_core as core
from core import theme
from screens.scaffold import ToolScreen


class StartupScreen(ToolScreen):
    title = "Startup Manager"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.entries = []
        info = Label(text="Apps that start by themselves when you log in. Turn "
                          "off the ones you do not need for a faster start. "
                          "Nothing is deleted: turn it on again any time.",
                     font_size=sp(12), color=theme.MUTED, halign="left",
                     valign="middle", size_hint_y=None, height=dp(48))
        info.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.body.add_widget(info)
        sv = ScrollView(do_scroll_x=False)
        self.grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        sv.add_widget(self.grid)
        self.body.add_widget(sv)
        self.status = Label(text="", font_size=sp(11), size_hint_y=None,
                            height=dp(22), color=theme.SUCCESS)
        self.body.add_widget(self.status)
        refresh = Button(text="Refresh", size_hint_y=None, height=dp(42))
        refresh.bind(on_release=lambda *a: self.refresh())
        self.body.add_widget(refresh)
        self.refresh()

    def on_pre_enter(self, *a):
        self.refresh()

    def refresh(self):
        self.grid.clear_widgets()
        if not core.is_supported():
            self._note(core.why_unsupported())
            return
        try:
            self.entries = core.list_entries()
        except Exception as e:
            self._note(f"Could not read the startup list: {e}")
            return
        if not self.entries:
            self._note("No startup apps found.")
            return
        for e in self.entries:
            self.grid.add_widget(self._row(e))

    def _note(self, text):
        lbl = Label(text=text, font_size=sp(13), color=theme.MUTED,
                    size_hint_y=None, height=dp(80), halign="center", valign="middle")
        lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.grid.add_widget(lbl)

    def _row(self, e):
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        col = BoxLayout(orientation="vertical")
        name = Label(text=e["name"], font_size=sp(14), halign="left", valign="bottom")
        name.bind(size=lambda w, v: setattr(w, "text_size", v))
        cmd = Label(text=f'{e["where"]}: {e["command"]}', font_size=sp(10),
                    color=theme.MUTED, halign="left", valign="top", shorten=True,
                    shorten_from="right")
        cmd.bind(size=lambda w, v: setattr(w, "text_size", v))
        col.add_widget(name)
        col.add_widget(cmd)
        row.add_widget(col)
        on = e["enabled"]
        b = Button(text="On" if on else "Off", size_hint_x=None, width=dp(72),
                   font_size=sp(13),
                   background_color=theme.ACCENT if on else (0.25, 0.25, 0.25, 1))
        b.bind(on_release=lambda *a: self.toggle(e))
        row.add_widget(b)
        return row

    def toggle(self, e):
        ok, err = core.set_enabled(e, not e["enabled"])
        if ok:
            self.status.color = theme.SUCCESS
            self.status.text = f'{e["name"]}: {"off" if e["enabled"] else "on"} at login'
        else:
            self.status.color = theme.DANGER
            self.status.text = err
        self.refresh()
