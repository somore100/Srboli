# screens/manage_tools_screen.py - remove tools for good, or bring them back.
# (Settings only hides a tool from the Dashboard; a removed tool is also not
# built at start-up and can't be opened by a shortcut.)
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from core import dashboard_core as dash
from core import tool_removal
from core import theme
from screens.registry import GROUPS, LABELS, default_route_order
from screens.settings_screen import load_settings, update_dashboard_state


class ManageToolsScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        root.add_widget(Label(text="[b]Remove or restore tools[/b]", markup=True,
                              font_size=sp(20), size_hint_y=None, height=dp(36)))
        info = Label(text="A removed tool disappears from the Dashboard, search "
                          "and shortcuts and is not loaded at start-up. Nothing "
                          "is deleted: restore it here any time.",
                     font_size=sp(11), color=theme.MUTED, halign="left",
                     valign="middle", size_hint_y=None, height=dp(50))
        info.bind(size=lambda w, v: setattr(w, "text_size", v))
        root.add_widget(info)
        sv = ScrollView(do_scroll_x=False)
        self._grid = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self._grid.bind(minimum_height=self._grid.setter("height"))
        sv.add_widget(self._grid)
        root.add_widget(sv)
        self._status = Label(text="", font_size=sp(11), size_hint_y=None,
                             height=dp(22), color=theme.SUCCESS)
        root.add_widget(self._status)
        back = Button(text="Back", size_hint_y=None, height=dp(42))
        back.bind(on_release=lambda *a: setattr(self.manager, "current", "settings"))
        root.add_widget(back)
        self.add_widget(root)
        self._refresh()

    def on_pre_enter(self, *a):
        self._refresh()

    def _row(self, route, text, action_text, action):
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        lbl = Label(text=text, font_size=sp(13), halign="left", valign="middle")
        lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        row.add_widget(lbl)
        b = Button(text=action_text, size_hint_x=None, width=dp(100),
                   font_size=sp(12))
        b.bind(on_release=lambda *a: action(route))
        row.add_widget(b)
        return row

    def _head(self, text):
        lbl = Label(text=f"[b]{text}[/b]", markup=True, font_size=sp(12),
                    halign="left", size_hint_y=None, height=dp(26),
                    color=theme.ACCENT)
        lbl.bind(size=lambda w, v: setattr(w, "text_size", v))
        return lbl

    def _refresh(self):
        cfg = load_settings()
        gone = cfg["removed"]
        self._grid.clear_widgets()
        if gone:
            self._grid.add_widget(self._head(f"Removed ({len(gone)})"))
            for r in gone:
                self._grid.add_widget(self._row(r, LABELS.get(r, r), "Restore",
                                                self._restore))
        menu = [(r, LABELS.get(r, r)) for r in cfg["order"]
                if r not in gone and r not in tool_removal.PROTECTED]
        for _key, title, members in dash.group_menu(menu, GROUPS):
            self._grid.add_widget(self._head(title))
            for r, label in members:
                self._grid.add_widget(self._row(r, label, "Remove", self._ask))

    def _ask(self, route):
        name = LABELS.get(route, route)
        lay = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        lay.add_widget(Label(text=f"Remove {name}?\nYou can restore it here later.",
                             font_size=sp(13)))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        pop = Popup(title="Remove tool", content=lay, size_hint=(0.85, None),
                    height=dp(190))
        no = Button(text="Cancel")
        no.bind(on_release=lambda *a: pop.dismiss())
        yes = Button(text="Remove", background_color=theme.DANGER)
        yes.bind(on_release=lambda *a: (pop.dismiss(), self._remove(route)))
        row.add_widget(no)
        row.add_widget(yes)
        lay.add_widget(row)
        pop.open()

    def _remove(self, route):
        cfg = load_settings()
        update_dashboard_state(removed=tool_removal.remove(
            cfg["removed"], route, set(default_route_order())))
        self._status.text = f"Removed: {LABELS.get(route, route)}"
        self._refresh()

    def _restore(self, route):
        cfg = load_settings()
        update_dashboard_state(removed=tool_removal.restore(cfg["removed"], route))
        self._status.text = f"Restored: {LABELS.get(route, route)}"
        self._refresh()
