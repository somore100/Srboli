# screens/feedback_popup.py - the "Leave Feedback" window (Kivy front end for
# feedback_kit). Sending and the hardware lookup run in threads, so the UI
# never freezes; system information is collected only after the box is
# ticked, shown on screen exactly as it will be sent, and left out otherwise.
import threading

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from core import theme
from core.tickbox import TickBox
from feedback_kit import (REPORT_TYPES, Report, collect_system_info,
                          format_system_info, send_report, validate)
from core.feedback import make_config


def _label(text, **kw):
    kw.setdefault("font_size", sp(12))
    kw.setdefault("color", theme.MUTED)
    lbl = Label(text=text, halign="left", valign="middle", size_hint_y=None,
                height=dp(22), **kw)
    lbl.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None)))
    return lbl


class FeedbackPopup(Popup):
    def __init__(self, cfg=None, **kw):
        self.cfg = cfg or make_config()
        self._sys = {}                  # filled only while the box is ticked
        self._sending = False
        self._closed = False
        w = min(Window.width * 0.94, dp(620))
        super().__init__(title="Leave Feedback", size_hint=(None, None),
                         size=(w, Window.height * 0.92), **kw)

        body = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        sv = ScrollView(do_scroll_x=False)
        form = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        form.bind(minimum_height=form.setter("height"))

        form.add_widget(_label("Report type"))
        self.type_sp = Spinner(text=REPORT_TYPES[0][0],
                               values=[t[0] for t in REPORT_TYPES],
                               size_hint_y=None, height=dp(40), font_size=sp(13))
        form.add_widget(self.type_sp)

        form.add_widget(_label("Application"))
        form.add_widget(Label(text=f"{self.cfg.app_name}  v{self.cfg.app_version}",
                              size_hint_y=None, height=dp(26), font_size=sp(13),
                              halign="left", color=theme.TEXT,
                              text_size=(w - dp(40), None)))

        form.add_widget(_label("Your name (optional)"))
        self.name_in = TextInput(multiline=False, size_hint_y=None, height=dp(38),
                                 font_size=sp(13), write_tab=False)
        form.add_widget(self.name_in)

        form.add_widget(_label("Title"))
        self.title_in = TextInput(multiline=False, size_hint_y=None, height=dp(38),
                                  font_size=sp(13), write_tab=False,
                                  hint_text="e.g. Application crashes on startup")
        form.add_widget(self.title_in)

        form.add_widget(_label("Description"))
        self.desc_in = TextInput(size_hint_y=None, height=dp(110), font_size=sp(13),
                                 hint_text="What happened, or what would you like to see?")
        form.add_widget(self.desc_in)

        self.sys_box = TickBox("Include my computer specifications", active=False,
                               size_hint_x=1, size_hint_y=None, height=dp(42))
        self.sys_box.bind(active=self._on_sys_toggle)
        form.add_widget(self.sys_box)

        self.sys_lbl = Label(text="", font_size=sp(11), color=theme.MUTED,
                             halign="left", valign="top", size_hint_y=None, height=0)
        self.sys_lbl.bind(width=lambda w_, v: setattr(w_, "text_size", (v, None)))
        self.sys_lbl.bind(texture_size=lambda w_, v: setattr(w_, "height", v[1] if w_.text else 0))
        form.add_widget(self.sys_lbl)

        sv.add_widget(form)
        body.add_widget(sv)

        self.status = Label(text="", font_size=sp(12), size_hint_y=None, height=dp(34),
                            halign="left", valign="middle", color=theme.DANGER)
        self.status.bind(size=lambda w_, v: setattr(w_, "text_size", (v[0], None)))
        body.add_widget(self.status)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.send_btn = Button(text="Send", background_color=theme.ACCENT)
        cancel = Button(text="Cancel")
        self.send_btn.bind(on_release=self._send)
        cancel.bind(on_release=lambda *a: self.dismiss())
        row.add_widget(self.send_btn)
        row.add_widget(cancel)
        body.add_widget(row)
        self.content = body
        self.bind(on_dismiss=lambda *a: setattr(self, "_closed", True))

    # ── system information (opt-in) ───────────────────────────────────────
    def _on_sys_toggle(self, box, active):
        if not active:
            self._sys = {}
            self.sys_lbl.text = ""
            return
        self.sys_lbl.text = "Looking up your computer specifications..."

        def work():
            info = collect_system_info(self.cfg.app_version)
            Clock.schedule_once(lambda dt: self._show_sys(info), 0)
        threading.Thread(target=work, daemon=True).start()

    def _show_sys(self, info):
        if self._closed or not self.sys_box.active:
            return                      # unticked while we were looking it up
        self._sys = info
        self.sys_lbl.text = ("This will be sent with your report:\n"
                             + "\n".join(format_system_info(info)))

    # ── sending ───────────────────────────────────────────────────────────
    def _report(self):
        names = [t[0] for t in REPORT_TYPES]
        return Report(type_index=names.index(self.type_sp.text),
                      name=self.name_in.text, title=self.title_in.text,
                      description=self.desc_in.text,
                      system=dict(self._sys) if self.sys_box.active else {})

    def _send(self, *a):
        if self._sending:
            return
        if self.sys_box.active and not self._sys:
            self._set_status("Still looking up your specifications - one moment.")
            return
        report = self._report()
        problems = validate(report)
        if problems:
            self._set_status("\n".join(problems))
            return
        self._sending = True
        self.send_btn.disabled = True
        self.send_btn.text = "Sending..."
        self._set_status("", theme.MUTED)

        def work():
            try:
                res = send_report(self.cfg, report)
                ok, msg = res.ok, res.message
            except Exception as e:      # never leave the button stuck
                ok, msg = False, f"Could not send: {e}"
            Clock.schedule_once(lambda dt: self._done(ok, msg), 0)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, ok, msg):
        self._sending = False
        self.send_btn.disabled = False
        self.send_btn.text = "Send"
        if ok:
            self.dismiss()
            from screens.dialogs import message_popup
            message_popup("Feedback", msg)
        elif not self._closed:
            self._set_status(msg)

    def _set_status(self, text, color=None):
        self.status.color = color or theme.DANGER
        self.status.text = text


def open_feedback(*a):
    FeedbackPopup().open()
