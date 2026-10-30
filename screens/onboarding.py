# screens/onboarding.py - first launch: pick which tools the Dashboard shows.
# It reuses Settings' hide list, so the choice can be changed there any time;
# hidden tools stay reachable through the Quick Switcher.

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from screens.registry import GROUPS, LABELS
from screens.settings_screen import (load_settings, save_settings,
                                     update_dashboard_state)


def open_onboarding(on_done=None):
    cfg = load_settings()
    checks = {}
    grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
    grid.bind(minimum_height=grid.setter("height"))
    listed = set()
    for _key, title, routes in GROUPS:
        grid.add_widget(Label(text=f"[b]{title}[/b]", markup=True,
                              size_hint_y=None, height=dp(26),
                              font_size=sp(12), halign="left"))
        for route in routes:
            if route not in LABELS:
                continue
            listed.add(route)
            row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
            cb = CheckBox(active=route not in cfg["hidden"],
                          size_hint=(None, None), size=(dp(28), dp(28)),
                          pos_hint={"center_y": 0.5})
            checks[route] = cb
            row.add_widget(cb)
            row.add_widget(Label(text=LABELS[route], font_size=sp(13),
                                 halign="left", valign="middle"))
            row.children[0].bind(size=lambda w, v: setattr(w, "text_size", v))
            grid.add_widget(row)

    sv = ScrollView(do_scroll_x=False)
    sv.add_widget(grid)
    intro = Label(text="Welcome! Choose the tools you want on your Dashboard. "
                       "You can change this later in Settings.",
                  size_hint_y=None, height=dp(48), font_size=sp(12),
                  halign="center")
    intro.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
    done = Button(text="Done", size_hint_y=None, height=dp(44))
    box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
    for w in (intro, sv, done):
        box.add_widget(w)
    pop = Popup(title="Pick your tools", content=box, size_hint=(0.92, 0.92),
                auto_dismiss=False)

    def finish(*_):
        cfg["hidden"] = [r for r, cb in checks.items() if not cb.active]
        save_settings(cfg)
        update_dashboard_state(onboarded=True)
        pop.dismiss()
        if on_done:
            on_done()

    done.bind(on_release=finish)
    pop.open()
    return pop
