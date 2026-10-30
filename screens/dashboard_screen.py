# screens/dashboard_screen.py - the home screen: search, pinned tools, recent
# tools and collapsible sections, laid out as tiles that fill a wide window.
# What is shown is decided by core/dashboard_core.py; main.py supplies
# open_route(route), which builds and shows a tool.

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import app_data
from core import dashboard_core as dash
from core import theme
from core.toast import toast
from screens.registry import ALIASES, GROUPS, LABELS
from screens.settings_screen import (effective_menu_order, load_settings,
                                     update_dashboard_state)

LONG_PRESS = 0.6
TILE_H = dp(52)
GAP = dp(5)


class ToolButton(Button):
    """A tool tile. A tap opens it; a long press or a right click pins it."""

    def __init__(self, route, on_open, on_pin, **kw):
        super().__init__(**kw)
        self.route, self._on_open, self._on_pin = route, on_open, on_pin
        self._lp = None
        self._long_done = False
        self.bind(on_release=self._released)

    def _released(self, *a):
        if self._long_done:
            self._long_done = False
            return
        self._on_open(self.route)

    def _long(self, dt):
        self._lp = None
        self._long_done = True
        self._on_pin(self.route)

    def _cancel_long(self):
        if self._lp is not None:
            self._lp.cancel()
            self._lp = None

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not getattr(
                touch, "is_mouse_scrolling", False):
            if getattr(touch, "button", "left") == "right":
                self._on_pin(self.route)
                return True
            self._lp = Clock.schedule_once(self._long, LONG_PRESS)
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._lp is not None and not self.collide_point(*touch.pos):
            self._cancel_long()
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        self._cancel_long()
        return super().on_touch_up(touch)


class Dashboard(Screen):
    def __init__(self, open_route, version="?", **kw):
        super().__init__(**kw)
        self._open_route = open_route
        self._version = version
        self._build()
        Window.bind(width=self._on_width)

    def _content_width(self):
        return min(Window.width, theme.MAX_CONTENT_W)

    def _on_width(self, *a):
        Clock.unschedule(self._refit)
        Clock.schedule_once(self._refit, 0.1)

    def _refit(self, dt):
        if hasattr(self, "_grid"):
            self._fill_list()           # no-op unless the column count changed

    def _build(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8),
                         size_hint_x=None)
        root.width = self._content_width()
        self.bind(width=lambda w, v: setattr(root, "width", self._content_width()))

        hdr = BoxLayout(size_hint_y=None, height=dp(70))
        title_col = BoxLayout(orientation="vertical")
        title_col.add_widget(Label(text="[b]Srboli[/b]", markup=True,
                             font_size=sp(30), size_hint_y=None, height=dp(48)))
        title_col.add_widget(Label(text="your pocket swiss-knife",
                             font_size=sp(11), size_hint_y=None, height=dp(18),
                             color=theme.MUTED))
        hdr.add_widget(title_col)
        gear = Button(text="Settings", size_hint=(None, None),
                      width=dp(100), height=dp(40), font_size=sp(12),
                      pos_hint={"center_y": 0.5})
        gear.bind(on_release=lambda *a: setattr(self.manager, "current", "settings"))
        hdr.add_widget(gear)
        root.add_widget(hdr)

        # search: type a few letters and only matching tools are listed;
        # Enter opens the first hit, Ctrl+K (main.py) focuses this box
        self._search = TextInput(hint_text="Search tools...  (Ctrl+K)",
                                 multiline=False, size_hint_y=None,
                                 height=dp(40), font_size=sp(14))
        self._search.bind(text=lambda *a: self._fill_list())
        self._search.bind(on_text_validate=self._open_first_hit)
        root.add_widget(self._search)

        sv = ScrollView(do_scroll_x=False)
        self._grid = GridLayout(cols=1, spacing=GAP, size_hint_y=None,
                                padding=(dp(6), dp(6)))
        self._grid.bind(minimum_height=self._grid.setter("height"))
        sv.add_widget(self._grid)
        root.add_widget(sv)
        self._list_sig = None
        self._fill_list()

        root.add_widget(Label(text=f"Srboli v{self._version}", font_size=sp(9),
                              size_hint_y=None, height=dp(18), color=theme.MUTED))
        anchor = AnchorLayout(anchor_x="center", anchor_y="top")
        anchor.add_widget(root)
        self.add_widget(anchor)
        self._sig = self._signature()

    def focus_search(self):
        self._search.focus = True

    # ── the tool list ────────────────────────────────────────────────────
    def _tool_button(self, route, label, font_size=sp(14), pinned=False):
        text = f"* {label}" if pinned else label
        btn = ToolButton(route, self._goto, self._toggle_pin, text=text,
                         size_hint_y=None, height=TILE_H, font_size=sp(font_size),
                         shorten=True, shorten_from="right")
        btn.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(8), None)))
        return btn

    def _tiles(self, items, cols, font_size=sp(14), pinned=()):
        """The tools as a grid of `cols` tiles per row."""
        cols = max(1, min(cols, len(items)))
        rows = -(-len(items) // cols)
        box = GridLayout(cols=cols, spacing=GAP, size_hint_y=None,
                         height=rows * TILE_H + (rows - 1) * GAP)
        for route, label in items:
            box.add_widget(self._tool_button(route, label, font_size,
                                             route in pinned))
        return box

    def _section_title(self, text):
        lbl = Label(text=f"[b]{text}[/b]", markup=True, font_size=sp(12),
                    halign="left", size_hint_y=None, height=dp(24),
                    color=theme.ACCENT)
        lbl.bind(size=lbl.setter("text_size"))
        return lbl

    def _fill_list(self, force=False):
        menu = effective_menu_order()
        query = self._search.text.strip()
        cfg = load_settings()
        width = self._content_width()
        cols = dash.tile_columns(width, dp(1))
        pinned = dash.visible_recent(cfg["pinned"], menu, shown=dash.PINNED_KEPT)
        recent = dash.visible_recent(
            cfg["recent"], menu, shown=dash.recent_shown(width, dp(1)))
        sig = (tuple(menu), query, tuple(recent), tuple(pinned),
               tuple(cfg["collapsed"]), cols)
        if sig == getattr(self, "_list_sig", None) and not force:
            return                      # nothing changed: no flash on Back
        self._list_sig = sig
        grid = self._grid
        grid.clear_widgets()
        pin_set = {r for r, _l in pinned}

        if query:
            hits = dash.search(menu, query, ALIASES)
            self._hits = hits
            if not hits:
                grid.add_widget(Label(text=f"No tool matches '{query}'.",
                                      size_hint_y=None, height=dp(40),
                                      font_size=sp(13), color=theme.MUTED))
            else:
                grid.add_widget(self._tiles(hits, cols, pinned=pin_set))
            return
        self._hits = []

        if pinned:
            grid.add_widget(self._section_title("Pinned"))
            grid.add_widget(self._tiles(pinned, cols, pinned=pin_set))
        if recent:
            grid.add_widget(self._section_title("Recent"))
            grid.add_widget(self._tiles(recent, len(recent), 12, pin_set))

        for key, title, members in dash.group_menu(menu, GROUPS):
            folded = key in cfg["collapsed"]
            head = Button(text=f"[{'+' if folded else '-'}]  {title}  "
                               f"({len(members)})",
                          size_hint_y=None, height=dp(40), font_size=sp(14),
                          halign="left", background_color=theme.SURFACE)
            head.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(12), None)))
            head.bind(on_release=lambda inst, k=key: self._toggle_section(k))
            grid.add_widget(head)
            if not folded:
                grid.add_widget(self._tiles(members, cols, pinned=pin_set))

    def _open_first_hit(self, *a):
        if getattr(self, "_hits", None):
            self._goto(self._hits[0][0])

    def _toggle_section(self, key):
        update_dashboard_state(collapsed=dash.toggle_collapsed(
            load_settings()["collapsed"], key))
        self._fill_list()

    def _toggle_pin(self, route):
        pinned = dash.toggle_pin(load_settings()["pinned"], route)
        update_dashboard_state(pinned=pinned)
        toast(("Pinned " if route in pinned else "Unpinned ")
              + LABELS.get(route, route))
        self._fill_list()

    def _goto(self, route):
        update_dashboard_state(recent=dash.push_recent(
            load_settings()["recent"], route))
        self._open_route(route)

    def _signature(self):
        return (tuple(effective_menu_order()), app_data.get_data_dir())

    def on_enter(self, *a):
        # Rebuild only when something the dashboard shows has changed
        # (screen order/hidden list from Settings, or the data dir).
        # Rebuilding on every return tore down and recreated every button,
        # which showed up as a visible flash when pressing Back.
        sig = self._signature()
        if sig != getattr(self, "_sig", None):
            self._build()
        else:
            self._search.text = ""      # leave search mode; Recent may have changed
            self._fill_list()

    def on_touch_down(self, touch):
        # Only a tool tile reacts to the right mouse button (it pins); other
        # buttons used to fire on any mouse button.
        if hasattr(touch, "button"):
            if getattr(touch, "is_mouse_scrolling", False):
                return super().on_touch_down(touch)
            if touch.button != "left":
                for w in self.walk():
                    if isinstance(w, ToolButton) and w.collide_point(*touch.pos):
                        return w.on_touch_down(touch)
                return True
        return super().on_touch_down(touch)
