# screens/scaffold.py - the common frame of a tool screen: a top bar (Back to
# the dashboard, the title, optional action buttons on the right) and a content
# area with theme padding that never stretches wider than theme.MAX_CONTENT_W.
#
#   class MyScreen(ToolScreen):
#       title = "My tool"
#       def __init__(self, **kw):
#           super().__init__(**kw)
#           self.body.add_widget(...)          # the tool's own widgets
#
# Pass actions=[Button(...), ...] to put buttons in the top bar. A screen that
# is converted drops its own title label and its own Back button.

from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from core import theme


class ToolScreen(Screen):
    title = "Tool"

    def __init__(self, actions=(), **kw):
        super().__init__(**kw)
        outer = BoxLayout(orientation="vertical", padding=theme.PAD["l"],
                          spacing=theme.PAD["s"])

        bar = BoxLayout(size_hint_y=None, height=dp(44), spacing=theme.PAD["s"])
        back = Button(text="< Back", size_hint_x=None, width=dp(84),
                      font_size=sp(13))
        back.bind(on_release=self.go_back)
        bar.add_widget(back)
        self.title_label = Label(text=f"[b]{self.title}[/b]", markup=True,
                                 font_size=theme.FONT["title"], halign="left",
                                 valign="middle")
        self.title_label.bind(size=lambda w, v: setattr(w, "text_size", v))
        bar.add_widget(self.title_label)
        for a in actions:
            bar.add_widget(a)
        outer.add_widget(bar)

        # content: centred, at most MAX_CONTENT_W wide
        holder = AnchorLayout(anchor_x="center", anchor_y="top")
        self.body = BoxLayout(orientation="vertical", spacing=theme.PAD["s"],
                              size_hint_x=None)
        holder.bind(width=lambda w, v: setattr(
            self.body, "width", min(v, theme.MAX_CONTENT_W)))
        holder.add_widget(self.body)
        outer.add_widget(holder)
        self.add_widget(outer)

    def go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"
