# screens/full_editor_screen.py
# Full Editor — outline document (nested sections, Markdown bodies) +
# multi-slide presenter + coloured tables, all in one screen with tabs.

import os
import re
import json
import time
import html as _html
from pathlib import Path

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.image import Image as KivyImage
from kivy.graphics import Color, Rectangle, Line
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard

import app_data
from core import outline_core as O
from core import slides_core as S
from core import table_core as T
from screens.md_editor import ColorStrip, MarkdownEditor, hex_rgba
from screens.dialogs import confirm_popup
from screens.md_parse import kivy_escape

try:
    from screens.md_view import MarkdownView
except Exception:
    MarkdownView = None


def _home():
    # Android: "~" resolves to "/" (read-only, empty). Start in shared storage.
    try:
        from core.android_storage import shared_storage_root
        return shared_storage_root()
    except Exception:
        return os.path.expanduser("~")


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT MODEL
# ═══════════════════════════════════════════════════════════════════════════════
_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class Document:
    """Holds the full editor state — outline, slide options, tables.

    There is exactly ONE Document per editor screen. The panels keep a
    reference to it, so New / Open must change it in place (reset /
    from_dict) and never swap in a new object.
    """

    def __init__(self):
        self.on_change = None      # called after every touch()
        self.reset()

    def reset(self):
        self.title      = "Untitled"
        self.path       = None
        self.dirty      = False
        self.outline    = [O.blank_node("Section 1")]
        self.active_node = 0
        self.slide_mode = "separate"   # see core/slides_core.py
        self.title_slide = True
        self.title_style = {}          # bg / fg of the title slide
        self.tables     = []
        self.active_table = 0

    def rename_table(self, i, new_name):
        """Rename table i (names stay unique) and fix the [[table:..]] lines
        in section bodies that placed it. Returns the name actually used."""
        old = self.tables[i]["name"]
        new = T.unique_name(self.tables, new_name, skip=i)
        if new != old:
            self.tables[i]["name"] = new
            for n in self.outline:
                n["body"] = n["body"].replace(O.table_placeholder(old),
                                              O.table_placeholder(new))
            self.touch()
        return new

    def build_slides(self):
        """The slides derived from the outline (skipped ones are flagged)."""
        return S.build_slides(self.title, self.outline, self.tables,
                              self.slide_mode, self.title_slide, self.title_style)

    def style_for(self, node):
        """The override dict of a slide's look: a node index, or None for the
        title slide. Created on demand; edit it, then touch()."""
        if node is None:
            return self.title_style
        return self.outline[node].setdefault("slide", {})

    def touch(self):
        """Record an edit (unsaved changes)."""
        self.dirty = True
        if self.on_change:
            self.on_change()

    def to_dict(self):
        return {
            "version":    4,
            "title":      self.title,
            "outline":    self.outline,
            "slide_opts": {"mode": self.slide_mode,
                           "title_slide": self.title_slide,
                           "title_style": self.title_style},
            "tables":     self.tables,
        }

    def from_dict(self, d):
        """Replace the content with `d`. Missing or malformed parts fall
        back to blank defaults, never to the previously open document."""
        self.reset()
        if not isinstance(d, dict):
            raise ValueError("not a Srboli document")
        self.title = str(d.get("title") or "Untitled")

        if "outline" in d:
            self.outline = O.normalize(d["outline"])
        else:
            # version 1 files: a flat list of paragraphs -> one section
            body = O.paragraphs_to_markdown(d.get("paragraphs"))
            if body:
                self.outline = [dict(O.blank_node("Text"), body=body)]

        opts = d.get("slide_opts") if isinstance(d.get("slide_opts"), dict) else {}
        if opts.get("mode") in S.MODES:
            self.slide_mode = opts["mode"]
        self.title_slide = bool(opts.get("title_slide", True))
        self.title_style = S.clean_style(opts.get("title_style"))
        for n in self.outline:
            if "slide" in n:
                n["slide"] = S.clean_style(n["slide"])
        if "slide_opts" not in d:
            # older files held hand-written slides: keep them as sections
            self.outline += S.import_slides(d.get("slides"))

        if "tables" in d:
            self.tables = T.normalize(d["tables"])
        else:
            # version 1-2 files had one plain grid called "sheet"
            old = T.from_sheet(d.get("sheet"))
            self.tables = [old] if old else []
        self.dirty = False
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# HTML EXPORT  (document + slides + tables)
# ═══════════════════════════════════════════════════════════════════════════════
def _css_color(value, default):
    value = str(value or "").strip()
    return value if _HEX_RE.match(value) else default


def _img_src(path):
    try:
        return _html.escape(Path(path).resolve().as_uri(), quote=True)
    except Exception:
        return ""


def export_html(doc, path):
    """Write the whole document as one HTML page: outline, slides, tables."""
    esc = _html.escape
    out = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
           f"<title>{esc(doc.title)}</title></head>"
           "<body style='background:#111;font-family:sans-serif;"
           "padding:24px;color:#fff'>"]

    out.append(O.to_html(doc.title, doc.outline, doc.tables))

    slides = S.visible(doc.build_slides())
    if slides:
        out.append("<h2>Slides</h2>")
        for sl in slides:
            out.append(f'<div style="background:{sl["bg"]};color:{sl["fg"]};'
                       'padding:24px;margin:12px 0;border-radius:8px">'
                       f'<h3>{esc(sl["title"])}</h3>')
            if sl["image"]:
                src = _img_src(sl["image"])
                if src:
                    out.append(f'<img src="{src}" style="max-width:60%">')
            out.append(O.markdown_to_html(sl["body"], 4))
            out.extend(T.to_html(t) for t in sl["tables"])
            out.append("</div>")

    # tables placed into a section were already written in place above
    placed = O.referenced_tables(doc.outline)
    loose = [t for t in doc.tables if t["name"] not in placed]
    if loose:
        out.append("<h2>Tables</h2>")
        for t in loose:
            out.append(f"<h3>{esc(t['name'])}</h3>{T.to_html(t)}")

    out.append("</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


# ═══════════════════════════════════════════════════════════════════════════════
# OUTLINE PANEL  (nested sections, each with a Markdown body)
# ═══════════════════════════════════════════════════════════════════════════════
class OutlinePanel(BoxLayout):
    """Tree of sections on the left, the selected section's title and
    Markdown body on the right. Tree edits live in core/outline_core.py."""

    SEL_BG = (0.25, 0.35, 0.5, 1)
    ROW_BG = (0.18, 0.18, 0.22, 1)

    def __init__(self, doc: Document, **kw):
        super().__init__(orientation="horizontal", spacing=dp(4), **kw)
        self.doc = doc
        self._loading = False       # True while the fields are filled from a node
        self._title_btns = {}       # outline index -> its tree button

        # ── tree (left) ──
        left = BoxLayout(orientation="vertical", size_hint_x=0.36, spacing=dp(3))
        left.add_widget(Label(text="Outline", size_hint_y=None,
                              height=dp(24), font_size=13))
        sv = ScrollView()
        self._tree = GridLayout(cols=1, spacing=dp(2), size_hint_y=None)
        self._tree.bind(minimum_height=self._tree.setter("height"))
        sv.add_widget(self._tree)
        left.add_widget(sv)
        for specs in ([("+ Item", self._add_item), ("+ Sub", self._add_sub),
                       ("Del", self._delete)],
                      [("Up", lambda *a: self._move(-1)),
                       ("Down", lambda *a: self._move(1)),
                       ("In", self._indent), ("Out", self._outdent)]):
            row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(2))
            for text, cb in specs:
                b = Button(text=text, font_size=11)
                b.bind(on_release=cb)
                row.add_widget(b)
            left.add_widget(row)
        self.add_widget(left)

        # ── section editor (right) ──
        right = BoxLayout(orientation="vertical", spacing=dp(3))
        self._title_in = TextInput(multiline=False, font_size=15,
                                   size_hint_y=None, height=dp(36),
                                   hint_text="Section title")
        self._title_in.bind(text=self._title_changed)
        right.add_widget(self._title_in)
        self._editor = MarkdownEditor(on_edit=self._body_changed)
        right.add_widget(self._editor)
        bottom = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(3))
        ins_btn = Button(text="Insert table", font_size=12)
        ins_btn.bind(on_release=self._insert_table)
        all_btn = Button(text="Preview whole document", font_size=12)
        all_btn.bind(on_release=self._preview_all)
        bottom.add_widget(ins_btn)
        bottom.add_widget(all_btn)
        right.add_widget(bottom)
        self.add_widget(right)

        self._refresh()

    # ── view ──────────────────────────────────────────────────────────────
    @property
    def _active(self):
        return self.doc.active_node

    def _refresh(self):
        """Rebuild the tree and load the active section (after Open / New)."""
        ol = self.doc.outline
        self.doc.active_node = max(0, min(self.doc.active_node, len(ol) - 1))
        self._show(self._active)
        self._load_node()

    def _show(self, i):
        """Make node i the active one, expanding any collapsed parents."""
        ol = self.doc.outline
        self.doc.active_node = i
        j = O.parent_index(ol, i)
        while j is not None:
            ol[j]["collapsed"] = False
            j = O.parent_index(ol, j)
        self._rebuild_tree()

    def _rebuild_tree(self):
        ol = self.doc.outline
        self._tree.clear_widgets()
        self._title_btns = {}
        for i in O.visible_indices(ol):
            n = ol[i]
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(2))
            row.add_widget(Widget(size_hint_x=None, width=dp(10) * n["depth"]))
            if O.has_children(ol, i):
                tg = Button(text="+" if n["collapsed"] else "-",
                            size_hint_x=None, width=dp(26), font_size=13)
                tg.bind(on_release=lambda inst, idx=i: self._toggle(idx))
            else:
                tg = Widget(size_hint_x=None, width=dp(26))
            row.add_widget(tg)
            tb = Button(text=self._row_text(n), markup=True, font_size=12,
                        halign="left", valign="middle", max_lines=2,
                        shorten=True, shorten_from="right",
                        background_color=self.SEL_BG if i == self._active
                        else self.ROW_BG)
            tb.bind(size=lambda b, v: setattr(b, "text_size", (v[0] - dp(8), v[1])))
            tb.bind(on_release=lambda inst, idx=i: self._select(idx))
            row.add_widget(tb)
            self._title_btns[i] = tb
            self._tree.add_widget(row)

    @staticmethod
    def _row_text(n):
        """Tree row: the title, and under it a dim line of what's inside."""
        head = kivy_escape(n["title"] or "(untitled)")
        hint = O.snippet(n["body"])
        if not hint:
            return head
        return f"{head}\n[size=10][color=9aa0a6]{kivy_escape(hint)}[/color][/size]"

    def _load_node(self):
        n = self.doc.outline[self._active]
        self._loading = True
        try:
            self._title_in.text = n["title"]
            self._editor.set_text(n["body"])
        finally:
            self._loading = False

    def _select(self, i):
        self._show(i)
        self._load_node()

    def _toggle(self, i):
        ol = self.doc.outline
        ol[i]["collapsed"] = not ol[i]["collapsed"]
        if ol[i]["collapsed"] and i < self._active < O.subtree_end(ol, i):
            self._select(i)
        else:
            self._rebuild_tree()

    # ── edits ─────────────────────────────────────────────────────────────
    def _title_changed(self, inst, val):
        if self._loading:
            return
        n = self.doc.outline[self._active]
        if n["title"] != val:
            n["title"] = val
            self.doc.touch()
            self._update_row(self._active)

    def _body_changed(self, val):
        n = self.doc.outline[self._active]
        if n["body"] != val:
            n["body"] = val
            self.doc.touch()
            self._update_row(self._active)

    def _update_row(self, i):
        btn = self._title_btns.get(i)
        if btn is not None:
            btn.text = self._row_text(self.doc.outline[i])

    def _after_edit(self, i):
        self.doc.touch()
        self._select(i)

    def _add_item(self, *a):
        ol = self.doc.outline
        self._after_edit(O.add_sibling(ol, self._active,
                                       f"Section {len(ol) + 1}"))

    def _add_sub(self, *a):
        ol = self.doc.outline
        self._after_edit(O.add_child(ol, self._active,
                                     f"Section {len(ol) + 1}"))

    def _delete(self, *a):
        ol = self.doc.outline
        i = self._active
        if len(ol) == 1:
            return
        if not O.has_children(ol, i):
            self._after_edit(O.delete_subtree(ol, i))
            return
        count = O.subtree_end(ol, i) - i
        confirm_popup("Delete section",
                      f"Delete this section and its {count - 1} sub-section(s)?",
                      lambda: self._after_edit(
                          O.delete_subtree(self.doc.outline, i)))

    def _move(self, step):
        new = O.move(self.doc.outline, self._active, step)
        if new != self._active:
            self._after_edit(new)

    def _indent(self, *a):
        if O.indent(self.doc.outline, self._active):
            self._after_edit(self._active)

    def _outdent(self, *a):
        if O.outdent(self.doc.outline, self._active):
            self._after_edit(self._active)

    def _insert_table(self, *a):
        """Put a [[table:Name]] line at the cursor in this section's body."""
        names = [t["name"] for t in self.doc.tables]
        box = BoxLayout(orientation="vertical", spacing=dp(4), padding=dp(6))
        pop = Popup(title="Insert table", content=box, size_hint=(0.7, 0.6))
        if not names:
            box.add_widget(Label(text="No tables yet - add one in the Tables tab."))

        def put(name):
            pop.dismiss()
            self._editor.ed.insert_text(f"\n{O.table_placeholder(name)}\n")
        for name in names:
            b = Button(text=name, size_hint_y=None, height=dp(40))
            b.bind(on_release=lambda inst, n=name: put(n))
            box.add_widget(b)
        pop.open()

    def _preview_all(self, *a):
        if MarkdownView is None:
            return
        view = MarkdownView(base_font=15)
        pop = Popup(title=self.doc.title or "Preview", content=view,
                    size_hint=(0.95, 0.95))
        pop.open()
        view.set_markdown(O.to_markdown(self.doc.title, self.doc.outline,
                                       self.doc.tables),
                          width_hint=pop.width)


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDES  (derived from the outline - see core/slides_core.py)
# ═══════════════════════════════════════════════════════════════════════════════
class _CellLabel(Label):
    """A table cell for the slide view: a Label with a solid background."""

    def __init__(self, bg=None, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*(bg or (1, 1, 1, 0.08)))
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, v: setattr(w._rect, "pos", v),
                  size=lambda w, v: setattr(w._rect, "size", v))


class SlideView(BoxLayout):
    """One slide drawn on its background: title, image, text, coloured tables.
    `scale` shrinks the whole thing for the preview in the Slides tab."""

    def __init__(self, slide, scale=1.0, **kw):
        super().__init__(orientation="vertical", padding=dp(16) * scale,
                         spacing=dp(8) * scale, **kw)
        fg = hex_rgba(slide["fg"])
        with self.canvas.before:
            Color(*hex_rgba(slide["bg"]))
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda w, v: setattr(w._bg, "pos", v),
                  size=lambda w, v: setattr(w._bg, "size", v))

        title = Label(text=slide["title"], font_size=28 * scale, bold=True,
                      size_hint_y=None, height=dp(48) * scale, color=fg)
        self.add_widget(title)
        img = slide.get("image")
        if img and os.path.exists(img):
            self.add_widget(KivyImage(source=img, size_hint_y=None,
                                      height=dp(150) * scale, fit_mode="contain"))
        sv = ScrollView()
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        spacing=dp(8) * scale)
        box.bind(minimum_height=box.setter("height"))
        if slide["body"].strip():
            lbl = Label(text=S.body_markup(slide["body"], int(18 * scale)),
                        markup=True, font_size=18 * scale, color=fg,
                        halign="left", valign="top", size_hint_y=None)
            lbl.bind(width=lambda w, v: setattr(w, "text_size", (v, None)),
                     texture_size=lambda w, ts: setattr(w, "height", ts[1]))
            box.add_widget(lbl)
        for t in slide["tables"]:
            box.add_widget(self._table(t, fg, scale))
        sv.add_widget(box)
        self.add_widget(sv)

    @staticmethod
    def _table(t, fg, scale):
        rows, cols = T.size(t)
        h = dp(30) * scale
        grid = GridLayout(cols=cols, spacing=dp(1), size_hint_y=None,
                          height=rows * h + (rows - 1) * dp(1))
        for row in t["cells"]:
            for c in row:
                grid.add_widget(_CellLabel(
                    bg=hex_rgba(c["bg"]) if c["bg"] else None,
                    text=c["t"], font_size=14 * scale,
                    color=hex_rgba(c["fg"]) if c["fg"] else fg))
        return grid


class SlidesPanel(BoxLayout):
    """List of the slides the outline produces, a preview of the selected one,
    and the few things you can set per slide (colours, image, skip). The text
    itself is edited in the Document tab ("Edit section")."""

    SEL_BG = (0.25, 0.35, 0.5, 1)
    ROW_BG = (0.18, 0.18, 0.22, 1)
    SKIP_BG = (0.12, 0.12, 0.14, 1)

    def __init__(self, doc: Document, **kw):
        super().__init__(orientation="horizontal", spacing=dp(4), **kw)
        self.doc = doc
        self.on_edit_node = None      # called with an outline index
        self._active = 0
        self._slides = []
        self._loading = False         # True while the option widgets are refilled

        # ── slide list (left) ──
        left = BoxLayout(orientation="vertical", size_hint_x=0.28, spacing=dp(3))
        left.add_widget(Label(text="Slides", size_hint_y=None, height=dp(24),
                              font_size=13))
        sv = ScrollView()
        self._list = GridLayout(cols=1, spacing=dp(3), size_hint_y=None)
        self._list.bind(minimum_height=self._list.setter("height"))
        sv.add_widget(self._list)
        left.add_widget(sv)
        self.add_widget(left)

        # ── options, preview and per-slide controls (right) ──
        right = BoxLayout(orientation="vertical", spacing=dp(3))

        def row():
            return BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(3))

        r1 = row()
        self._mode_sp = Spinner(text=S.MODES["separate"],
                                values=tuple(S.MODES.values()), font_size=12)
        self._mode_sp.bind(text=self._mode_changed)
        r1.add_widget(self._mode_sp)
        self._title_tg = ToggleButton(text="Title slide", state="down",
                                      font_size=12, size_hint_x=None,
                                      width=dp(92))
        self._title_tg.bind(state=self._title_toggled)
        r1.add_widget(self._title_tg)
        right.add_widget(r1)

        self._preview = BoxLayout()
        right.add_widget(self._preview)

        r2 = row()
        r2.add_widget(Label(text="Colour:", font_size=12, size_hint_x=None,
                            width=dp(52)))
        self._bg_btn = ToggleButton(text="Bg", group="slide_target",
                                    state="down", allow_no_selection=False,
                                    font_size=12)
        self._fg_btn = ToggleButton(text="Text", group="slide_target",
                                    allow_no_selection=False, font_size=12)
        r2.add_widget(self._bg_btn)
        r2.add_widget(self._fg_btn)
        reset = Button(text="Reset", font_size=12)
        reset.bind(on_release=self._reset_colors)
        r2.add_widget(reset)
        right.add_widget(r2)
        right.add_widget(ColorStrip(self._pick_color))   # its own row: tappable swatches

        r3 = row()
        for text, cb in (("Image...", self._pick_image),
                         ("No image", self._clear_image)):
            b = Button(text=text, font_size=12)
            b.bind(on_release=cb)
            r3.add_widget(b)
        self._skip_tg = ToggleButton(text="Skip", font_size=12)
        self._skip_tg.bind(state=self._skip_toggled)
        r3.add_widget(self._skip_tg)
        edit = Button(text="Edit section", font_size=12)
        edit.bind(on_release=self._edit_section)
        r3.add_widget(edit)
        right.add_widget(r3)

        r4 = row()
        for text, cb, w in (("<", lambda *a: self._nav(-1), dp(44)),
                            (">", lambda *a: self._nav(1), dp(44))):
            b = Button(text=text, size_hint_x=None, width=w)
            b.bind(on_release=cb)
            r4.add_widget(b)
        self._idx_lbl = Label(text="0/0", font_size=12)
        r4.add_widget(self._idx_lbl)
        present = Button(text="> Present", font_size=13)
        present.bind(on_release=self._present)
        r4.add_widget(present)
        right.add_widget(r4)
        self.add_widget(right)

        self._refresh()

    # ── view ──────────────────────────────────────────────────────────────
    @property
    def _slide(self):
        return self._slides[self._active] if self._slides else None

    def _refresh(self):
        """Rebuild from the outline (on opening the tab, after Open / New)."""
        self._slides = self.doc.build_slides()
        self._active = max(0, min(self._active, len(self._slides) - 1))
        self._loading = True
        try:
            self._mode_sp.text = S.MODES[self.doc.slide_mode]
            self._title_tg.state = "down" if self.doc.title_slide else "normal"
        finally:
            self._loading = False
        self._rebuild_list()
        self._show()

    def _rebuild_list(self):
        self._list.clear_widgets()
        for i, sl in enumerate(self._slides):
            text = sl["title"] or "(untitled)"
            if sl["skip"]:
                text = f"(skip) {text}"
            b = Button(text=text, size_hint_y=None, height=dp(34), font_size=12,
                       halign="left", shorten=True, shorten_from="right",
                       background_color=self.SEL_BG if i == self._active
                       else self.SKIP_BG if sl["skip"] else self.ROW_BG)
            b.bind(size=lambda w, v: setattr(w, "text_size", (v[0] - dp(8), v[1])))
            b.bind(on_release=lambda inst, idx=i: self._select(idx))
            self._list.add_widget(b)

    def _show(self):
        self._preview.clear_widgets()
        sl = self._slide
        self._idx_lbl.text = f"{self._active + 1}/{len(self._slides)}" if sl else "0/0"
        if sl is None:
            return
        self._preview.add_widget(SlideView(sl, scale=0.6))
        self._loading = True
        try:
            self._skip_tg.state = "down" if sl["skip"] else "normal"
        finally:
            self._loading = False
        self._skip_tg.disabled = sl["node"] is None    # the title slide has its own toggle

    def _select(self, i):
        self._active = i
        self._rebuild_list()
        self._show()

    def _nav(self, delta):
        if self._slides:
            self._select(max(0, min(self._active + delta, len(self._slides) - 1)))

    def _changed(self):
        """A style or option changed: mark edited, rebuild keeping the selection."""
        self.doc.touch()
        self._refresh()

    # ── options ───────────────────────────────────────────────────────────
    def _mode_changed(self, sp, text):
        if self._loading:
            return
        for key, label in S.MODES.items():
            if label == text and key != self.doc.slide_mode:
                self.doc.slide_mode = key
                self._active = 0
                self._changed()

    def _title_toggled(self, tg, state):
        if self._loading:
            return
        self.doc.title_slide = state == "down"
        self._active = 0
        self._changed()

    # ── per-slide look ────────────────────────────────────────────────────
    def _pick_color(self, hex_str):
        sl = self._slide
        if sl is None:
            return
        self.doc.style_for(sl["node"])["bg" if self._bg_btn.state == "down"
                                       else "fg"] = hex_str
        self._changed()

    def _reset_colors(self, *a):
        sl = self._slide
        if sl is None:
            return
        style = self.doc.style_for(sl["node"])
        style.pop("bg", None)
        style.pop("fg", None)
        self._changed()

    def _clear_image(self, *a):
        sl = self._slide
        if sl is not None and self.doc.style_for(sl["node"]).pop("image", None):
            self._changed()

    def _skip_toggled(self, tg, state):
        sl = self._slide
        if self._loading or sl is None or sl["node"] is None:
            return
        style = self.doc.style_for(sl["node"])
        if state == "down":
            style["skip"] = True
        else:
            style.pop("skip", None)
        self._changed()

    def _pick_image(self, *a):
        sl = self._slide
        if sl is None:
            return
        chooser = FileChooserIconView(
            path=_home(), filters=["*.png", "*.jpg", "*.jpeg", "*.webp"])
        btn = Button(text="Use image", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Slide image", content=layout, size_hint=(0.92, 0.92))

        def _do(*x):
            if chooser.selection:
                self.doc.style_for(sl["node"])["image"] = chooser.selection[0]
                self._changed()
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _edit_section(self, *a):
        sl = self._slide
        if sl is not None and sl["node"] is not None and self.on_edit_node:
            self.on_edit_node(sl["node"])

    # ── presenting ────────────────────────────────────────────────────────
    def _present(self, *a):
        """Show the non-skipped slides full-screen, one popup per slide."""
        slides = S.visible(self.doc.build_slides())
        if not slides:
            return
        cur = self._slide
        start = next((i for i, s in enumerate(slides)
                      if cur is not None and s["node"] == cur["node"]), 0)

        def build(idx):
            layout = BoxLayout(orientation="vertical")
            layout.add_widget(SlideView(slides[idx]))
            nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8),
                            padding=(dp(8), 0))
            pb = Button(text="< Prev", disabled=(idx == 0))
            nb = Button(text="Next >", disabled=(idx == len(slides) - 1))
            xb = Button(text="x Exit", size_hint_x=None, width=dp(90))
            lbl = Label(text=f"{idx + 1}/{len(slides)}", size_hint_x=None,
                        width=dp(60), font_size=13)
            for w in (pb, lbl, nb, xb):
                nav.add_widget(w)
            layout.add_widget(nav)
            pp = Popup(title="", content=layout, size_hint=(0.96, 0.96),
                       separator_height=0)
            pb.bind(on_release=lambda *x: (pp.dismiss(), show(idx - 1)))
            nb.bind(on_release=lambda *x: (pp.dismiss(), show(idx + 1)))
            xb.bind(on_release=lambda *x: pp.dismiss())
            return pp

        def show(idx):
            build(max(0, min(idx, len(slides) - 1))).open()

        show(start)


# ═══════════════════════════════════════════════════════════════════════════════
# TABLES PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class TablesPanel(BoxLayout):
    """Named tables: editable grid, fill / text colours per cell, row or
    column, add and remove rows and columns, and the SUM / AVG / COUNT /
    MAX / MIN formulas. The data and rules live in core/table_core.py."""

    CELL_W = dp(90)
    CELL_H = dp(32)
    DEFAULT_BG = (0.12, 0.12, 0.15, 1)
    DEFAULT_FG = (0.92, 0.92, 0.88, 1)
    SCOPES = {"Cell": "cell", "Row": "row", "Column": "col", "All": "all"}

    def __init__(self, doc: Document, **kw):
        super().__init__(orientation="vertical", spacing=dp(3), **kw)
        self.doc = doc
        self.on_renamed = None        # called after a rename edited section bodies
        self._sel = (0, 0)            # (row, col) of the selected cell
        self._cells = {}              # (r, c) -> TextInput
        self._loading = False         # True while the table picker is refilled

        def row():
            return BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(3))

        def btn(text, cb, **kw):
            b = Button(text=text, font_size=12, **kw)
            b.bind(on_release=cb)
            return b

        # ── row 1: which table ──
        r1 = row()
        self._table_sp = Spinner(text="", values=(), font_size=12,
                                 size_hint_x=0.3)
        self._table_sp.bind(text=self._pick_table)
        r1.add_widget(self._table_sp)
        self._name_in = TextInput(multiline=False, font_size=13,
                                  hint_text="Table name")
        self._name_in.bind(on_text_validate=self._rename,
                           focus=lambda i, f: None if f else self._rename())
        r1.add_widget(self._name_in)
        r1.add_widget(btn("+ Table", self._add_table, size_hint_x=None,
                          width=dp(72)))
        r1.add_widget(btn("Del Table", self._del_table, size_hint_x=None,
                          width=dp(76)))
        self.add_widget(r1)

        # ── row 2: rows / columns, and what a colour applies to ──
        r2 = row()
        r2.add_widget(btn("+ Row", lambda *a: self._structure("add_row")))
        r2.add_widget(btn("- Row", lambda *a: self._structure("del_row")))
        r2.add_widget(btn("+ Col", lambda *a: self._structure("add_col")))
        r2.add_widget(btn("- Col", lambda *a: self._structure("del_col")))
        r2.add_widget(Label(text="Apply to:", font_size=12, size_hint_x=None,
                            width=dp(62)))
        self._scope_sp = Spinner(text="Cell", values=tuple(self.SCOPES),
                                 font_size=12, size_hint_x=None, width=dp(80))
        r2.add_widget(self._scope_sp)
        self.add_widget(r2)

        # ── row 3: what the colour applies to; row 4: the colours ──
        r3 = row()
        self._fill_btn = ToggleButton(text="Fill", group="tbl_target",
                                      state="down", allow_no_selection=False,
                                      font_size=12)
        self._text_btn = ToggleButton(text="Text", group="tbl_target",
                                      allow_no_selection=False, font_size=12)
        r3.add_widget(self._fill_btn)
        r3.add_widget(self._text_btn)
        r3.add_widget(btn("Clear", self._clear_colors))
        self.add_widget(r3)
        self._strip = ColorStrip(self._apply_color)
        self.add_widget(self._strip)

        # ── formula bar ──
        fbar = row()
        fbar.add_widget(Label(text="Cell:", size_hint_x=None, width=dp(40),
                              font_size=13))
        self._cell_ref = Label(text="A1", size_hint_x=None, width=dp(50),
                               font_size=13, color=(0.4, 0.8, 1, 1))
        fbar.add_widget(self._cell_ref)
        fbar.add_widget(Label(text="Formula:", size_hint_x=None, width=dp(68),
                              font_size=12))
        self._formula_in = TextInput(multiline=False, font_size=13,
                                     hint_text="=SUM(A1:A5)  or  =A1*2+B3")
        self._formula_in.bind(on_text_validate=self._apply_formula)
        fbar.add_widget(self._formula_in)
        fbar.add_widget(btn(">", self._apply_formula, size_hint_x=None,
                            width=dp(36)))
        self.add_widget(fbar)

        # ── grid ──
        self._sv = ScrollView()
        self._empty = Label(text="No tables yet.\nPress + Table to make one.",
                            font_size=14, halign="center")
        self.add_widget(self._sv)

        self._refresh()

    # ── view ──────────────────────────────────────────────────────────────
    @property
    def _table(self):
        ts = self.doc.tables
        return ts[self.doc.active_table] if ts else None

    def _bg(self, cell):
        return hex_rgba(cell["bg"]) if cell["bg"] else self.DEFAULT_BG

    def _fg(self, cell):
        return hex_rgba(cell["fg"]) if cell["fg"] else self.DEFAULT_FG

    def _refresh(self):
        """Reload everything from the document (after Open / New / edits)."""
        d = self.doc
        d.active_table = max(0, min(d.active_table, len(d.tables) - 1))
        self._sync_names()
        t = self._table
        if t is not None:
            rows, cols = T.size(t)
            self._sel = (min(self._sel[0], rows - 1), min(self._sel[1], cols - 1))
        else:
            self._sel = (0, 0)
        self._rebuild_grid()
        self._show_selection()

    def _sync_names(self):
        """Refill the table picker and the name box from the document."""
        d = self.doc
        names = [t["name"] for t in d.tables]
        self._loading = True
        try:
            self._table_sp.values = names
            self._table_sp.text = names[d.active_table] if names else ""
            self._name_in.text = names[d.active_table] if names else ""
        finally:
            self._loading = False

    def _rebuild_grid(self):
        self._sv.clear_widgets()
        self._cells = {}
        t = self._table
        if t is None:
            self._sv.add_widget(self._empty)
            return
        rows, cols = T.size(t)
        grid = GridLayout(cols=cols + 1, spacing=dp(1), size_hint=(None, None))
        grid.bind(minimum_size=grid.setter("size"))
        grid.add_widget(Label(text="", size_hint=(None, None),
                              size=(dp(30), dp(26)), font_size=10))
        for c in range(cols):
            grid.add_widget(Label(text=T.col_letter(c), size_hint=(None, None),
                                  size=(self.CELL_W, dp(26)), font_size=11,
                                  bold=True, color=(0.6, 0.8, 1, 1)))
        for r in range(rows):
            grid.add_widget(Label(text=str(r + 1), size_hint=(None, None),
                                  size=(dp(30), self.CELL_H), font_size=10,
                                  color=(0.6, 0.7, 0.8, 1)))
            for c in range(cols):
                cell = t["cells"][r][c]
                ti = TextInput(
                    text=cell["t"], multiline=False, font_size=12,
                    size_hint=(None, None), size=(self.CELL_W, self.CELL_H),
                    background_normal="", background_active="",
                    background_color=self._bg(cell),
                    foreground_color=self._fg(cell),
                    cursor_color=(0.4, 0.8, 1, 1))
                ti.bind(focus=lambda inst, foc, row=r, col=c:
                        self._on_focus(foc, row, col))
                ti.bind(text=lambda inst, val, row=r, col=c:
                        self._cell_changed(row, col, val))
                self._cells[(r, c)] = ti
                grid.add_widget(ti)
        self._sv.add_widget(grid)

    def _show_selection(self):
        t = self._table
        r, c = self._sel
        self._cell_ref.text = f"{T.col_letter(c)}{r + 1}"
        self._formula_in.text = t["cells"][r][c]["t"] if t is not None else ""

    def _on_focus(self, focused, row, col):
        if focused:
            self._sel = (row, col)
            self._show_selection()

    def _note(self, msg):
        Popup(title="Tables", content=Label(text=msg),
              size_hint=(0.7, 0.3)).open()

    # ── which table ───────────────────────────────────────────────────────
    def _pick_table(self, spinner, text):
        if self._loading:
            return
        names = [t["name"] for t in self.doc.tables]
        if text in names:
            self.doc.active_table = names.index(text)
            self._sel = (0, 0)
            self._refresh()

    def _add_table(self, *a):
        ts = self.doc.tables
        ts.append(T.blank_table(T.unique_name(ts, f"Table {len(ts) + 1}")))
        self.doc.active_table = len(ts) - 1
        self._sel = (0, 0)
        self.doc.touch()
        self._refresh()

    def _del_table(self, *a):
        t = self._table
        if t is None:
            return
        used = any(c["t"] or c["bg"] or c["fg"] for row in t["cells"] for c in row)

        def do():
            del self.doc.tables[self.doc.active_table]
            self._sel = (0, 0)
            self.doc.touch()
            self._refresh()
            if self.on_renamed:
                self.on_renamed()
        if used:
            confirm_popup("Delete table", f"Delete table '{t['name']}' and its "
                          "contents?", do)
        else:
            do()

    def _rename(self, *a):
        if self._loading or self._table is None:
            return
        old = self._table["name"]
        new = self.doc.rename_table(self.doc.active_table, self._name_in.text)
        self._sync_names()           # no grid rebuild: the user may be mid-edit
        if new != old and self.on_renamed:
            self.on_renamed()

    # ── cells ─────────────────────────────────────────────────────────────
    def _cell_changed(self, r, c, val):
        t = self._table
        if t is not None and t["cells"][r][c]["t"] != val:
            t["cells"][r][c]["t"] = val
            self.doc.touch()

    def _set_cell(self, r, c, val):
        self._cells[(r, c)].text = val
        self._cell_changed(r, c, val)

    def _apply_formula(self, *a):
        t = self._table
        if t is None:
            return
        expr = self._formula_in.text.strip()
        r, c = self._sel
        if not expr.startswith("="):
            self._set_cell(r, c, expr)
            return
        try:
            self._set_cell(r, c, T.format_number(T.eval_formula(t, expr[1:])))
        except Exception:
            self._set_cell(r, c, "#ERR")

    # ── rows and columns ──────────────────────────────────────────────────
    def _structure(self, action):
        t = self._table
        if t is None:
            return
        r, c = self._sel
        if action == "add_row":
            ok, sel = T.add_row(t, r), (r + 1, c)
        elif action == "del_row":
            ok, sel = T.delete_row(t, r), (r, c)
        elif action == "add_col":
            ok, sel = T.add_col(t, c), (r, c + 1)
        else:
            ok, sel = T.delete_col(t, c), (r, c)
        if not ok:
            self._note("Can't do that: a table keeps at least one row and "
                       f"column, and has at most {T.MAX_ROWS} rows and "
                       f"{T.MAX_COLS} columns.")
            return
        rows, cols = T.size(t)
        self._sel = (min(sel[0], rows - 1), min(sel[1], cols - 1))
        self.doc.touch()
        self._refresh()

    # ── colours ───────────────────────────────────────────────────────────
    def _target(self):
        return "bg" if self._fill_btn.state == "down" else "fg"

    def _repaint(self, cells):
        t = self._table
        for i, j in cells:
            ti = self._cells.get((i, j))
            if ti is not None:
                ti.background_color = self._bg(t["cells"][i][j])
                ti.foreground_color = self._fg(t["cells"][i][j])

    def _apply_color(self, hex_str):
        t = self._table
        if t is None:
            return
        r, c = self._sel
        changed = T.set_color(t, r, c, self._target(), hex_str,
                              self.SCOPES[self._scope_sp.text])
        if changed:
            self._repaint(changed)
            self.doc.touch()

    def _clear_colors(self, *a):
        t = self._table
        if t is None:
            return
        r, c = self._sel
        scope = self.SCOPES[self._scope_sp.text]
        changed = set(T.set_color(t, r, c, "bg", "", scope)
                      + T.set_color(t, r, c, "fg", "", scope))
        if changed:
            self._repaint(changed)
            self.doc.touch()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SCREEN
# ═══════════════════════════════════════════════════════════════════════════════
class FullEditorScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.doc  = Document()
        self.doc.on_change = self._on_doc_change

        root = BoxLayout(orientation="vertical", padding=dp(4), spacing=dp(4))

        # ── file bar: title and status on one row, the buttons share the next ──
        top = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
        self._doc_title = TextInput(text="Untitled", multiline=False,
                                    font_size=14, size_hint_x=0.7,
                                    hint_text="Document title")
        self._doc_title.bind(text=self._title_changed)
        top.add_widget(self._doc_title)
        self._status = Label(text="", font_size=11, halign="left", size_hint_x=0.3)
        self._status.bind(size=self._status.setter("text_size"))
        top.add_widget(self._status)
        root.add_widget(top)

        fbar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
        for lbl, cb in [("New", self._new), ("Open", self._open),
                         ("Save", self._save), ("Save As", self._save_as),
                         ("Export HTML", self._export_html)]:
            b = Button(text=lbl, font_size=12)
            b.bind(on_release=cb)
            fbar.add_widget(b)
        root.add_widget(fbar)

        # ── tabs ──
        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(40))

        # Document tab
        doc_tab = TabbedPanelItem(text=" Document")
        self._doc_tab = doc_tab
        self._outline = OutlinePanel(self.doc)
        doc_tab.add_widget(self._outline)
        self.tabs.add_widget(doc_tab)

        # Slides tab
        slides_tab = TabbedPanelItem(text=" Slides")
        self._slides_tab = slides_tab
        self._slides = SlidesPanel(self.doc)
        self._slides.on_edit_node = self._edit_section
        slides_tab.add_widget(self._slides)
        self.tabs.add_widget(slides_tab)

        # Tables tab
        tables_tab = TabbedPanelItem(text=" Tables")
        self._tables = TablesPanel(self.doc)
        self._tables.on_renamed = self._outline._load_node   # bodies were edited
        tables_tab.add_widget(self._tables)
        self.tabs.add_widget(tables_tab)

        self.tabs.bind(current_tab=self._tab_changed)
        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    def _tab_changed(self, tabs, tab):
        if tab is self._slides_tab:          # the outline may have changed
            self._slides._refresh()

    def _edit_section(self, idx):
        """Slides tab -> Document tab with that section selected."""
        self.tabs.switch_to(self._doc_tab)
        self._outline._select(idx)

    # ── change tracking ───────────────────────────────────────────────────
    def _title_changed(self, inst, val):
        if self.doc.title != val:
            self.doc.title = val
            self.doc.touch()

    def _on_doc_change(self):
        name = os.path.basename(self.doc.path) if self.doc.path else "unsaved"
        self._status.text = f"*{name}"

    def _confirm_discard(self, proceed):
        """Ask what to do with unsaved changes, then run proceed()."""
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        box.add_widget(Label(text="This document has unsaved changes."))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        save_b = Button(text="Save")
        disc_b = Button(text="Discard")
        canc_b = Button(text="Cancel")
        for w in (save_b, disc_b, canc_b):
            row.add_widget(w)
        box.add_widget(row)
        pop = Popup(title="Unsaved changes", content=box,
                    size_hint=(0.8, 0.36), auto_dismiss=False)
        save_b.bind(on_release=lambda *a: (pop.dismiss(),
                                           self._save(then=proceed)))
        disc_b.bind(on_release=lambda *a: (pop.dismiss(), proceed()))
        canc_b.bind(on_release=lambda *a: pop.dismiss())
        pop.open()

    def _guard(self, proceed):
        if self.doc.dirty:
            self._confirm_discard(proceed)
        else:
            proceed()

    # ── file ops ──────────────────────────────────────────────────────────
    def _new(self, *a):
        self._guard(self._do_new)

    def _do_new(self):
        self.doc.reset()
        self._reload_panels()
        self._status.text = "New document"

    def _reload_panels(self):
        """Point every panel at the (changed in place) document."""
        self._doc_title.text = self.doc.title
        self._outline._refresh()
        self._slides._active = 0
        self._slides._refresh()
        self._tables._refresh()
        self.doc.dirty = False      # widget refreshes above fire change events

    def _open(self, *a):
        self._guard(self._open_dialog)

    def _open_dialog(self):
        docs_dir = app_data.subdir("full_editor")
        chooser  = FileChooserIconView(path=docs_dir, filters=["*.srdoc"])
        btn = Button(text="Open", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Open document", content=layout,
                      size_hint=(0.92, 0.92))

        def _do(*a):
            if chooser.selection:
                path = chooser.selection[0]
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    self.doc.from_dict(data)
                    self.doc.path = path
                    self._reload_panels()
                    self._status.text = f"Opened: {self.doc.title}"
                except Exception as e:
                    self._popup("Error", str(e))
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _save(self, *a, then=None):
        if self.doc.path:
            if self._write(self.doc.path) and then:
                then()
        else:
            self._save_as(then=then)

    def _save_as(self, *a, then=None):
        docs_dir = app_data.subdir("full_editor")
        name_in  = TextInput(
            text=f"{self.doc.title}.srdoc",
            multiline=False, size_hint_y=None, height=dp(36), font_size=13)
        chooser  = FileChooserIconView(path=docs_dir)
        btn = Button(text="Save", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=dp(4))
        layout.add_widget(chooser)
        layout.add_widget(name_in)
        layout.add_widget(btn)
        popup = Popup(title="Save As", content=layout, size_hint=(0.92,0.92))

        def _do(*a):
            fname = os.path.basename(name_in.text.strip()) or f"{self.doc.title}.srdoc"
            path = os.path.join(chooser.path, fname)
            if not path.endswith(".srdoc"):
                path += ".srdoc"
            popup.dismiss()
            if self._write(path):
                self.doc.path = path
                if then:
                    then()

        btn.bind(on_release=_do)
        popup.open()

    def _write(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.doc.to_dict(), f, indent=2, ensure_ascii=False)
            self.doc.dirty = False
            self._status.text = f"Saved: {os.path.basename(path)}"
            return True
        except Exception as e:
            self._popup("Save error", str(e))
            return False

    def _export_html(self, *a):
        docs_dir = app_data.subdir("full_editor")
        safe = re.sub(r'[\\/:*?"<>|]+', "_", self.doc.title).strip() or "Untitled"
        path = os.path.join(docs_dir, f"{safe}.html")
        try:
            export_html(self.doc, path)
            self._status.text = f"Exported HTML: {path}"
            self._popup("Exported", path)
        except Exception as e:
            self._popup("Export error", str(e))

    def _go_back(self, *a):
        self._guard(lambda: setattr(self.manager, "current", "dashboard")
                    if self.manager else None)

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=str(msg)),
              size_hint=(0.72, 0.38)).open()
