# screens/ai_settings.py - the "AI" block of the Settings screen.
# Master switch (off by default); under it the provider, address, model, key,
# which tools may use the AI, a Test button. While the switch is off the rest
# is greyed out and the tools show no AI buttons at all.

import threading

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from core import ai_core

KEY_ROW_H = dp(36)


def _label(text, size=11, color=(0.7, 0.7, 0.7, 1), height=None):
    lbl = Label(text=text, font_size=sp(size), halign="left", valign="middle",
                color=color, size_hint_y=None, height=height or dp(24))
    lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    return lbl


class AISettings(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(6),
                         **kw)
        self.bind(minimum_height=self.setter("height"))
        self._cfg = ai_core.load()
        self._loading = True

        head = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.master = CheckBox(active=self._cfg["enabled"], size_hint=(None, None),
                               size=(dp(26), dp(26)))
        head.add_widget(self.master)
        head.add_widget(_label("Turn on AI features. Off = no AI buttons "
                               "anywhere, nothing is ever sent.", 12,
                               (1, 1, 1, 1), dp(44)))
        self.add_widget(head)

        self.body = BoxLayout(orientation="vertical", size_hint_y=None,
                              spacing=dp(6))
        self.body.bind(minimum_height=self.body.setter("height"))
        self.add_widget(self.body)
        b = self.body

        row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        row.add_widget(_label("Provider:", 12, (1, 1, 1, 1), dp(38)))
        self.provider = Spinner(
            text=ai_core.PROVIDER_LABELS[self._cfg["provider"]],
            values=[ai_core.PROVIDER_LABELS[p] for p in ai_core.PROVIDERS],
            font_size=sp(12), size_hint_x=0.7)
        row.add_widget(self.provider)
        b.add_widget(row)

        b.add_widget(_label("Address:", 11))
        self.url = TextInput(multiline=False, font_size=sp(12),
                             size_hint_y=None, height=dp(36))
        b.add_widget(self.url)
        b.add_widget(_label("Model name (e.g. llama3.2, gpt-4o-mini, "
                            "claude-haiku-4-5):", 11))
        self.model = TextInput(multiline=False, font_size=sp(12),
                               size_hint_y=None, height=dp(36))
        b.add_widget(self.model)

        self.key_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                 spacing=dp(6))
        self.key_box.bind(minimum_height=self.key_box.setter("height"))
        self.key_box.add_widget(_label("API key (kept on this device only):", 11))
        self.key = TextInput(multiline=False, password=True, font_size=sp(12),
                             size_hint_y=None, height=dp(36))
        self.key_box.add_widget(self.key)
        b.add_widget(self.key_box)

        b.add_widget(_label("Which tools may use the AI:", 12, (1, 1, 1, 1)))
        self.tool_boxes = {}
        for key, text in ai_core.TOOLS.items():
            r = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(8))
            cb = CheckBox(active=self._cfg["tools"].get(key, False),
                          size_hint=(None, None), size=(dp(24), dp(24)))
            self.tool_boxes[key] = cb
            r.add_widget(cb)
            r.add_widget(_label(text, 11, (0.9, 0.9, 0.9, 1), dp(34)))
            b.add_widget(r)

        self.privacy = _label("", 10, (1, 0.8, 0.5, 1), dp(60))
        b.add_widget(self.privacy)

        btns = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.test_btn = Button(text="Test connection", font_size=sp(12))
        self.save_btn = Button(text="Save", font_size=sp(12),
                               background_color=(0.2, 0.55, 0.2, 1))
        btns.add_widget(self.test_btn)
        btns.add_widget(self.save_btn)
        b.add_widget(btns)
        self.status = _label("", 11, (0.8, 0.8, 0.8, 1), dp(40))
        b.add_widget(self.status)

        self.master.bind(active=self._on_master)
        self.provider.bind(text=self._on_provider)
        self.test_btn.bind(on_release=self._test)
        self.save_btn.bind(on_release=lambda *a: self._save(True))
        self._fill()
        self._loading = False
        self._apply_master()

    # ── form <-> config ──────────────────────────────────────────────────
    def _current_provider(self):
        for p, label in ai_core.PROVIDER_LABELS.items():
            if label == self.provider.text:
                return p
        return "ollama"

    def _fill(self):
        p = self._current_provider()
        self.url.text = self._cfg["urls"].get(p, "")
        self.model.text = self._cfg["models"].get(p, "")
        self.key.text = self._cfg["api_key"] if p != "ollama" else ""
        local = p == "ollama"
        self.key_box.opacity = 0 if local else 1
        self.key_box.disabled = local
        self.key_box.height = 0 if local else dp(24 + 36 + 6)
        self.privacy.text = (
            "Your text stays on the computer that runs Ollama. If that is "
            "another PC, anything sent to it crosses your network as plain "
            "http." if local else
            "Text you send is uploaded to this service and handled under its "
            "terms. It may cost money. Never put a key you can't revoke here.")

    def _collect(self):
        """The form as a config dict (not saved)."""
        cfg = ai_core.load()
        cfg.update(self._cfg)
        p = self._current_provider()
        cfg["enabled"] = self.master.active
        cfg["provider"] = p
        cfg["urls"] = dict(self._cfg["urls"])
        cfg["models"] = dict(self._cfg["models"])
        cfg["urls"][p] = self.url.text.strip()
        cfg["models"][p] = self.model.text.strip()
        if p != "ollama":
            cfg["api_key"] = self.key.text.strip()
        cfg["tools"] = {k: cb.active for k, cb in self.tool_boxes.items()}
        return cfg

    def _on_provider(self, *a):
        if self._loading:
            return
        # keep what was typed for the provider we are leaving
        prev = self._cfg["provider"]
        self._cfg["urls"][prev] = self.url.text.strip()
        self._cfg["models"][prev] = self.model.text.strip()
        if prev != "ollama":
            self._cfg["api_key"] = self.key.text.strip()
        self._cfg["provider"] = self._current_provider()
        self._fill()

    def _on_master(self, *a):
        self._apply_master()
        if not self._loading:
            self._save(False)

    def _apply_master(self):
        on = self.master.active
        self.body.disabled = not on
        self.body.opacity = 1 if on else 0.35

    def _save(self, say=True):
        cfg = self._collect()
        ok = ai_core.save(cfg)
        if ok:
            self._cfg = cfg
        if say or not ok:
            why = ai_core.problem(cfg)
            self.status.text = (
                "Couldn't save the settings." if not ok else
                "Saved." + (f" Not usable yet: {why}" if why else
                            " The AI buttons appear in the ticked tools."))
        return ok

    def _test(self, *a):
        cfg = self._collect()
        self.status.text = "Testing..."
        self.test_btn.disabled = True

        def run():
            ok, msg = ai_core.test_connection(cfg)

            def show(dt):
                self.test_btn.disabled = False
                self.status.text = ("OK: " if ok else "Failed: ") + msg
            Clock.schedule_once(show)

        threading.Thread(target=run, daemon=True).start()
