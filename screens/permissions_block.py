# screens/permissions_block.py - Settings > Permissions (Android only).
# Shows what Srboli may do on the phone, which tools use it, and a button to
# grant it. Nothing is requested at install; tools also ask in context.

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from core import android_storage as store
from core import permissions

GOOD = (0.4, 0.85, 0.4, 1)
WARN = (0.95, 0.75, 0.3, 1)


class PermissionsBlock(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(6), **kw)
        self.bind(minimum_height=self.setter("height"))
        self.refresh()

    def refresh(self):
        self.clear_widgets()
        head = Label(text="Permissions", font_size=sp(15), size_hint_y=None, height=dp(26))
        self.add_widget(head)
        note = Label(text="Srboli asks for nothing when installed. Each tool asks the first "
                          "time you open it. You can allow or check them here. Srboli only "
                          "touches the folders you pick.", font_size=sp(11),
                     halign="left", valign="top", size_hint_y=None, height=dp(52),
                     color=(0.7, 0.7, 0.7, 1))
        note.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
        self.add_widget(note)
        for kind, title, granted, used in permissions.rows(
                store.has_full_storage_access(), store.has_notification_permission()):
            row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(6))
            state = "Allowed" if granted else "Not allowed"
            txt = Label(text=f"[b]{title}[/b]\n{state}  -  used by: {used}",
                        markup=True, font_size=sp(11), halign="left", valign="middle",
                        color=GOOD if granted else WARN)
            txt.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
            row.add_widget(txt)
            if not granted:
                b = Button(text="Allow", size_hint_x=None, width=dp(84), font_size=sp(12))
                b.bind(on_release=lambda *a, k=kind: self._allow(k))
                row.add_widget(b)
            self.add_widget(row)

    def _allow(self, kind):
        if kind == "storage":
            store.request_basic_permissions()
            store.request_full_storage_access()
        else:
            store.request_notification_permission()
