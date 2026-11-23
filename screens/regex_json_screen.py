# screens/regex_json_screen.py - Regex & JSON: test a regular expression live (highlighted
# matches, groups, replace preview) and read / format / check JSON (tree view, path lookup).
# Logic: core/regex_json_core.py.
import threading

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from core import regex_json_core as core
from core import theme
from screens.scaffold import ToolScreen

OFF = (0.25, 0.25, 0.25, 1)
MAX_TEXT = 200_000


def _row(h=38):
    return BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(4))


def _label(text="", size=12, color=None, h=None, **kw):
    lb = Label(text=text, font_size=sp(size), halign="left", valign="top", markup=True,
               **({"color": color} if color else {}), **kw)
    if h:
        lb.size_hint_y = None
        lb.height = dp(h)
    lb.bind(size=lambda w, v: setattr(w, "text_size", (v[0], None if h is None else v[1])))
    return lb


class RegexJsonScreen(ToolScreen):
    title = "Regex & JSON"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tab = "regex"
        self.flags = set()
        self._job = 0
        self._debounce = None
        self.value = None
        self.open_paths = set()

        tabs = _row()
        self.tab_btns = {}
        for key, label in (("regex", "Regex tester"), ("json", "JSON viewer")):
            b = Button(text=label, font_size=sp(13))
            b.bind(on_release=lambda *a, k=key: self.set_tab(k))
            tabs.add_widget(b)
            self.tab_btns[key] = b
        self.body.add_widget(tabs)
        self.holder = BoxLayout()
        self.body.add_widget(self.holder)
        self._build_regex()
        self._build_json()
        self.set_tab("regex")

    def set_tab(self, tab):
        self.tab = tab
        for k, b in self.tab_btns.items():
            b.background_color = theme.ACCENT if k == tab else OFF
        self.holder.clear_widgets()
        self.holder.add_widget(self.regex_panel if tab == "regex" else self.json_panel)

    # =============== regex ===============
    def _build_regex(self):
        p = BoxLayout(orientation="vertical", spacing=dp(4))
        row = _row()
        self.pattern = TextInput(hint_text="Pattern, e.g. (\\d+)-(\\w+)", multiline=False,
                                 font_size=sp(14))
        self.pattern.bind(text=lambda *a: self._schedule())
        row.add_widget(self.pattern)
        self.flag_btns = {}
        for f, name in (("i", "i"), ("m", "m"), ("s", "s")):
            b = Button(text=name, size_hint_x=None, width=dp(38), font_size=sp(13))
            b.bind(on_release=lambda *a, k=f: self.toggle_flag(k))
            row.add_widget(b)
            self.flag_btns[f] = b
        p.add_widget(row)
        self.flag_help = _label("i = ignore case, m = ^ $ per line, s = dot matches newline",
                                10, theme.MUTED, h=16)
        p.add_widget(self.flag_help)
        self.text_in = TextInput(hint_text="Text to test", font_size=sp(13),
                                 size_hint_y=None, height=dp(120))
        self.text_in.bind(text=lambda *a: self._schedule())
        p.add_widget(self.text_in)
        row = _row()
        self.repl_in = TextInput(hint_text="Replace with (use \\1 for groups)", multiline=False,
                                 font_size=sp(13))
        self.repl_in.bind(text=lambda *a: self._schedule())
        row.add_widget(self.repl_in)
        cp = Button(text="Copy result", size_hint_x=None, width=dp(100), font_size=sp(12))
        cp.bind(on_release=lambda *a: self._copy(self._replaced))
        row.add_widget(cp)
        p.add_widget(row)
        self.summary = _label("", 12, theme.MUTED, h=22)
        p.add_widget(self.summary)
        sv = ScrollView(do_scroll_x=False)
        self.out = _label("", 12, size_hint_y=None)
        self.out.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(10)))
        self.out.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        sv.add_widget(self.out)
        p.add_widget(sv)
        self._replaced = ""
        self.regex_panel = p
        self._sync_flags()

    def toggle_flag(self, f):
        self.flags ^= {f}
        self._sync_flags()
        self._schedule()

    def _sync_flags(self):
        for f, b in self.flag_btns.items():
            b.background_color = theme.ACCENT if f in self.flags else OFF

    def _schedule(self):
        if self._debounce is not None:
            self._debounce.cancel()
        self._debounce = Clock.schedule_once(lambda dt: self.run_regex(), 0.25)

    def run_regex(self):
        """Match in a worker thread so a runaway pattern cannot freeze the screen."""
        pat, text = self.pattern.text, self.text_in.text[:MAX_TEXT]
        flags, repl = "".join(sorted(self.flags)), self.repl_in.text
        self._job += 1
        job = self._job
        self.summary.text = "Working..."

        def work():
            res = core.find_matches(pat, flags, text)
            rep = core.replace_all(pat, flags, repl, text) if repl and not res["error"] else None
            Clock.schedule_once(lambda dt: self._show_regex(job, text, res, rep), 0)

        threading.Thread(target=work, daemon=True).start()

    def _show_regex(self, job, text, res, rep):
        if job != self._job:
            return                                     # a newer edit replaced this one
        if res["error"]:
            self.summary.text = "[color=e05555]" + _esc(res["error"]) + "[/color]"
            self.out.text = ""
            return
        if not self.pattern.text:
            self.summary.text = "Type a pattern."
            self.out.text = ""
            return
        n = res["count"]
        self.summary.text = (f"{n} match{'es' if n != 1 else ''}"
                             + (f" (showing the first {len(res['matches'])})" if res["truncated"] else ""))
        parts = [core.highlight_markup(text, res["matches"], _esc)]
        for i, m in enumerate(res["matches"][:50], 1):
            line = f"[b]#{i}[/b] {m['start']}-{m['end']}  '{_esc(m['text'])}'"
            if m["groups"]:
                line += "   groups: " + ", ".join(
                    "None" if g is None else "'" + _esc(g) + "'" for g in m["groups"])
            if m["named"]:
                line += "   named: " + ", ".join(f"{k}={v!r}" for k, v in m["named"].items())
            parts.append(line)
        if rep is not None:
            result, count, err = rep
            self._replaced = result
            parts.append("\n[b]Replace result[/b] " + (_esc(err) if err else f"({count} replaced)")
                         + "\n" + _esc(result))
        else:
            self._replaced = ""
        self.out.text = "\n".join(parts[:1]) + "\n\n" + "\n".join(parts[1:])

    # =============== json ===============
    def _build_json(self):
        p = BoxLayout(orientation="vertical", spacing=dp(4))
        self.json_in = TextInput(hint_text="Paste JSON here", font_size=sp(12),
                                 size_hint_y=None, height=dp(130))
        self.json_in.bind(text=lambda *a: self._json_changed())
        p.add_widget(self.json_in)
        row = _row()
        for text, fn in (("Paste", self.paste_json), ("Format", lambda: self.rewrite("pretty")),
                         ("Minify", lambda: self.rewrite("minify")),
                         ("Sort keys", self.toggle_sort), ("Copy", lambda: self._copy(self.json_in.text))):
            b = Button(text=text, font_size=sp(12))
            b.bind(on_release=lambda *a, f=fn: f())
            row.add_widget(b)
            if text == "Sort keys":
                self.sort_btn = b
        p.add_widget(row)
        self.sort_keys = False
        self.sort_btn.background_color = OFF
        self.json_status = _label("", 12, theme.MUTED, h=22)
        p.add_widget(self.json_status)
        row = _row()
        self.path_in = TextInput(hint_text="Path, e.g. users[0].name", multiline=False,
                                 font_size=sp(13))
        self.path_in.bind(on_text_validate=lambda *a: self.lookup())
        row.add_widget(self.path_in)
        go = Button(text="Look up", size_hint_x=None, width=dp(90), font_size=sp(12))
        go.bind(on_release=lambda *a: self.lookup())
        row.add_widget(go)
        p.add_widget(row)
        self.path_out = _label("", 12, h=44)
        p.add_widget(self.path_out)
        sv = ScrollView(do_scroll_x=False)
        self.tree = GridLayout(cols=1, spacing=dp(1), size_hint_y=None)
        self.tree.bind(minimum_height=self.tree.setter("height"))
        sv.add_widget(self.tree)
        p.add_widget(sv)
        self.json_panel = p

    def paste_json(self):
        try:
            self.json_in.text = Clipboard.paste() or ""
        except Exception as e:
            self.json_status.text = f"Could not paste: {e}"

    def toggle_sort(self):
        self.sort_keys = not self.sort_keys
        self.sort_btn.background_color = theme.ACCENT if self.sort_keys else OFF

    def _json_changed(self):
        self.open_paths = set()
        self.value, err = core.parse(self.json_in.text)
        if self.json_in.text.strip() == "":
            self.json_status.text = ""
        elif err:
            self.json_status.text = "[color=e05555]" + _esc(err) + "[/color]"
        else:
            self.json_status.text = "[color=55c070]Valid JSON[/color]  (" + core.kind(self.value) + ")"
        self._draw_tree()

    def rewrite(self, how):
        if self.value is None and core.parse(self.json_in.text)[1]:
            return
        v, err = core.parse(self.json_in.text)
        if err:
            return
        self.json_in.text = (core.pretty(v, sort_keys=self.sort_keys) if how == "pretty"
                             else core.minify(v))

    def lookup(self):
        if self.value is None:
            self.path_out.text = "Paste valid JSON first."
            return
        found, err = core.get_path(self.value, self.path_in.text)
        if err:
            self.path_out.text = "[color=e05555]" + _esc(err) + "[/color]"
        else:
            self.path_out.text = ("[b]" + core.kind(found) + "[/b]  "
                                  + _esc(core.pretty(found) if core.kind(found) in ("object", "array")
                                         else core.preview(found, 300))[:600])

    def _draw_tree(self):
        self.tree.clear_widgets()
        if self.value is None:
            return
        for depth, label, prev, path, kind, expandable, is_open in core.rows(self.value, self.open_paths):
            mark = ("- " if is_open else "+ ") if expandable else "  "
            b = Button(text=f"{mark}{label}: {prev}", size_hint_y=None, height=dp(30),
                       font_size=sp(12), halign="left", valign="middle", shorten=True,
                       shorten_from="right", background_color=(0.16, 0.18, 0.22, 1))
            b.bind(size=lambda w, v, d=depth: setattr(w, "text_size", (v[0] - dp(12) - d * dp(16), v[1])))
            b.padding = (dp(6) + depth * dp(16), 0)
            b.bind(on_release=lambda *a, p_=path, e=expandable: self.pick_row(p_, e))
            self.tree.add_widget(b)

    def pick_row(self, path, expandable):
        if expandable and path != ():
            self.open_paths ^= {path}
        self.path_in.text = "" if path == () else core.path_text(path)
        self.lookup()
        self._draw_tree()

    def _copy(self, text):
        try:
            Clipboard.copy(text)
        except Exception:
            pass


def _esc(s):
    return s.replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")
