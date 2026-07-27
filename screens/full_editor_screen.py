# screens/full_editor_screen.py
# Full Editor — Word-like rich text + multi-slide presenter + basic table/spreadsheet
# All in one screen with tabs.
# Uses Kivy TextInput (colored text via markup) + custom slide/table widgets.

import os
import json
import time

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.image import Image as KivyImage
from kivy.graphics import Color, Rectangle, Line
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.clipboard import Clipboard

import app_data


def _home():
    return os.path.expanduser("~")


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT MODEL
# ═══════════════════════════════════════════════════════════════════════════════
class Document:
    """Holds the full editor state — rich text, slides, spreadsheet."""

    def __init__(self):
        self.title      = "Untitled"
        self.path       = None
        # Rich text: list of paragraph dicts
        self.paragraphs = [{"text": "", "color": "#FFFFFF",
                            "size": 15, "align": "left", "bold": False}]
        # Slides: list of slide dicts
        self.slides     = [{"title": "Slide 1", "body": "",
                            "color": "#FFFFFF", "bg": "#1A1A2E",
                            "image": None}]
        self.active_slide = 0
        # Spreadsheet: 2D list of strings
        self.sheet_rows = 20
        self.sheet_cols = 10
        self.sheet      = [["" for _ in range(self.sheet_cols)]
                           for _ in range(self.sheet_rows)]

    def to_dict(self):
        return {
            "title":      self.title,
            "paragraphs": self.paragraphs,
            "slides":     self.slides,
            "sheet":      self.sheet,
        }

    def from_dict(self, d):
        self.title      = d.get("title", "Untitled")
        self.paragraphs = d.get("paragraphs", self.paragraphs)
        self.slides     = d.get("slides",     self.slides)
        self.sheet      = d.get("sheet",      self.sheet)
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# RICH TEXT EDITOR PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class RichTextPanel(BoxLayout):
    """
    Paragraph-based rich text editor.
    Each paragraph has: text, colour, font size, alignment, bold.
    Exported as plain .txt (with colour tags) or HTML.
    """

    def __init__(self, doc: Document, **kw):
        super().__init__(orientation="vertical", spacing=3, **kw)
        self.doc   = doc
        self._rows = []   # list of BoxLayout rows
        self._active_para = 0

        # ── formatting toolbar ──
        bar = BoxLayout(size_hint_y=None, height=dp(36), spacing=4)

        bar.add_widget(Label(text="Size:", size_hint_x=None,
                             width=dp(38), font_size=12))
        self._size_sl = Slider(min=10, max=48, value=15,
                               size_hint_x=None, width=dp(100))
        self._size_sl.bind(value=self._apply_size)
        bar.add_widget(self._size_sl)

        bar.add_widget(Label(text="Color:", size_hint_x=None,
                             width=dp(44), font_size=12))
        self._color_in = TextInput(text="#FFFFFF", multiline=False,
                                   size_hint_x=None, width=dp(80),
                                   font_size=12)
        bar.add_widget(self._color_in)

        self._bold_btn = ToggleButton(text="B", size_hint_x=None,
                                      width=dp(36), font_size=14, bold=True)
        self._bold_btn.bind(on_release=self._apply_bold)
        bar.add_widget(self._bold_btn)

        self._align_sp = Spinner(text="Left",
                                 values=("Left", "Center", "Right"),
                                 size_hint_x=None, width=dp(80), font_size=12)
        self._align_sp.bind(text=self._apply_align)
        bar.add_widget(self._align_sp)

        apply_btn = Button(text="Apply", size_hint_x=None, width=dp(62),
                           font_size=13)
        apply_btn.bind(on_release=self._apply_all)

        add_para = Button(text="+ Para", size_hint_x=None, width=dp(68),
                          font_size=13)
        add_para.bind(on_release=self._add_paragraph)

        ins_img = Button(text=" Image", size_hint_x=None, width=dp(80),
                         font_size=12)
        ins_img.bind(on_release=self._insert_image)

        for w in (apply_btn, add_para, ins_img):
            bar.add_widget(w)
        self.add_widget(bar)

        # ── paragraph list ──
        sv = ScrollView()
        self._para_box = BoxLayout(orientation="vertical", spacing=4,
                                   size_hint_y=None, padding=(4, 4))
        self._para_box.bind(minimum_height=self._para_box.setter("height"))
        sv.add_widget(self._para_box)
        self.add_widget(sv)

        self._refresh()

    def _refresh(self):
        self._para_box.clear_widgets()
        self._rows = []
        for i, para in enumerate(self.doc.paragraphs):
            row = BoxLayout(size_hint_y=None, height=dp(max(40, para["size"]*2+10)),
                            spacing=3)
            # index label
            idx_lbl = Button(text=str(i+1), size_hint_x=None, width=dp(26),
                             font_size=11,
                             background_color=(0.3,0.3,0.3,1))
            idx_lbl.bind(on_release=lambda inst, idx=i: self._select_para(idx))
            row.add_widget(idx_lbl)

            ti = TextInput(
                text=para["text"],
                multiline=True,
                font_size=para["size"],
                foreground_color=self._hex_to_rgba(para.get("color","#FFFFFF")),
                halign=para.get("align","left"),
                background_color=(0.10, 0.10, 0.13, 1),
            )
            # auto-grow
            ti.bind(minimum_height=ti.setter("height"))
            ti.bind(text=lambda inst, val, idx=i: self._update_para_text(idx, val))
            row.add_widget(ti)

            del_btn = Button(text="x", size_hint_x=None, width=dp(28),
                             font_size=12)
            del_btn.bind(on_release=lambda inst, idx=i: self._del_para(idx))
            row.add_widget(del_btn)

            self._rows.append((row, ti))
            self._para_box.add_widget(row)

    def _select_para(self, idx):
        self._active_para = idx
        para = self.doc.paragraphs[idx]
        self._size_sl.value   = para.get("size", 15)
        self._color_in.text   = para.get("color", "#FFFFFF")
        self._bold_btn.state  = "down" if para.get("bold") else "normal"
        self._align_sp.text   = para.get("align", "left").capitalize()

    def _update_para_text(self, idx, val):
        if 0 <= idx < len(self.doc.paragraphs):
            self.doc.paragraphs[idx]["text"] = val

    def _add_paragraph(self, *a):
        self.doc.paragraphs.append({"text": "", "color": "#FFFFFF",
                                    "size": 15, "align": "left",
                                    "bold": False})
        self._refresh()

    def _del_para(self, idx):
        if len(self.doc.paragraphs) > 1:
            del self.doc.paragraphs[idx]
            self._refresh()

    def _apply_all(self, *a):
        idx = self._active_para
        if 0 <= idx < len(self.doc.paragraphs):
            self.doc.paragraphs[idx]["size"]  = int(self._size_sl.value)
            self.doc.paragraphs[idx]["color"] = self._color_in.text.strip()
            self.doc.paragraphs[idx]["bold"]  = self._bold_btn.state == "down"
            self.doc.paragraphs[idx]["align"] = self._align_sp.text.lower()
            self._refresh()

    def _apply_size(self, *a):  pass
    def _apply_bold(self, *a):  pass
    def _apply_align(self, *a): pass

    def _insert_image(self, *a):
        chooser = FileChooserIconView(
            path=_home(),
            filters=["*.png","*.jpg","*.jpeg","*.bmp","*.webp"],
        )
        btn = Button(text="Insert", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Insert Image", content=layout,
                      size_hint=(0.92, 0.92))

        def _do(*a):
            if chooser.selection:
                path = chooser.selection[0]
                # add as special paragraph
                self.doc.paragraphs.append({
                    "text": f"[IMAGE:{path}]",
                    "color": "#FFFFFF", "size": 15,
                    "align": "center", "bold": False,
                    "image": path,
                })
                self._refresh()
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def export_html(self, path):
        lines = ["<!DOCTYPE html><html><body "
                 "style='background:#111;font-family:sans-serif;padding:24px'>"]
        for p in self.doc.paragraphs:
            if p.get("image"):
                lines.append(f'<img src="{p["image"]}" '
                             f'style="max-width:100%;display:block;margin:8px auto">')
                continue
            sz    = p.get("size", 15)
            col   = p.get("color","#FFFFFF")
            bold  = "font-weight:bold;" if p.get("bold") else ""
            align = p.get("align","left")
            txt   = p["text"].replace("\n","<br>")
            lines.append(f'<p style="font-size:{sz}px;color:{col};'
                         f'text-align:{align};{bold}">{txt}</p>')
        lines.append("</body></html>")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    @staticmethod
    def _hex_to_rgba(hex_str):
        h = hex_str.lstrip("#")
        if len(h) == 6:
            r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return (r/255, g/255, b/255, 1)
        return (1, 1, 1, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDES PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class SlidesPanel(BoxLayout):
    def __init__(self, doc: Document, **kw):
        super().__init__(orientation="horizontal", spacing=4, **kw)
        self.doc = doc
        self._active = 0

        # ── slide list (left) ──
        left = BoxLayout(orientation="vertical", size_hint_x=0.22, spacing=3)
        left.add_widget(Label(text="Slides", size_hint_y=None,
                              height=dp(24), font_size=13))
        sv = ScrollView()
        self._slide_list = GridLayout(cols=1, spacing=3, size_hint_y=None)
        self._slide_list.bind(minimum_height=self._slide_list.setter("height"))
        sv.add_widget(self._slide_list)
        left.add_widget(sv)

        add_btn = Button(text="+ Slide", size_hint_y=None, height=dp(36),
                         font_size=12)
        add_btn.bind(on_release=self._add_slide)
        del_btn = Button(text="Del Delete", size_hint_y=None, height=dp(36),
                         font_size=12)
        del_btn.bind(on_release=self._del_slide)
        left.add_widget(add_btn)
        left.add_widget(del_btn)
        self.add_widget(left)

        # ── slide editor (right) ──
        right = BoxLayout(orientation="vertical", spacing=4)

        # slide toolbar
        stool = BoxLayout(size_hint_y=None, height=dp(36), spacing=5)
        stool.add_widget(Label(text="Title:", size_hint_x=None,
                               width=dp(40), font_size=13))
        self._title_in = TextInput(multiline=False, font_size=14,
                                   size_hint_x=0.45)
        self._title_in.bind(text=lambda inst, v: self._upd_slide("title", v))

        stool.add_widget(self._title_in)
        stool.add_widget(Label(text="BG:", size_hint_x=None,
                               width=dp(32), font_size=12))
        self._bg_in = TextInput(text="#1A1A2E", multiline=False,
                                size_hint_x=None, width=dp(80), font_size=12)
        self._bg_in.bind(text=lambda inst, v: self._upd_slide("bg", v))
        stool.add_widget(self._bg_in)

        stool.add_widget(Label(text="Text col:", size_hint_x=None,
                               width=dp(68), font_size=12))
        self._fcol_in = TextInput(text="#FFFFFF", multiline=False,
                                  size_hint_x=None, width=dp(80), font_size=12)
        self._fcol_in.bind(text=lambda inst, v: self._upd_slide("color", v))
        stool.add_widget(self._fcol_in)

        img_btn = Button(text=" Image", size_hint_x=None, width=dp(84),
                         font_size=12)
        img_btn.bind(on_release=self._add_image)
        stool.add_widget(img_btn)
        right.add_widget(stool)

        # body textarea
        self._body_in = TextInput(
            multiline=True, font_size=15,
            background_color=(0.08, 0.08, 0.12, 1),
            foreground_color=(1, 1, 1, 1),
        )
        self._body_in.bind(text=lambda inst, v: self._upd_slide("body", v))
        right.add_widget(self._body_in)

        # preview bar
        prev_row = BoxLayout(size_hint_y=None, height=dp(34), spacing=5)
        prev_btn = Button(text="<", size_hint_x=None, width=dp(44))
        next_btn = Button(text=">", size_hint_x=None, width=dp(44))
        self._slide_idx_lbl = Label(text="1/1", size_hint_x=None,
                                    width=dp(50), font_size=12)
        present_btn = Button(text="> Present", font_size=13)
        prev_btn.bind(on_release=lambda *a: self._nav(-1))
        next_btn.bind(on_release=lambda *a: self._nav(1))
        present_btn.bind(on_release=self._present)
        for w in (prev_btn, self._slide_idx_lbl, next_btn, present_btn):
            prev_row.add_widget(w)
        right.add_widget(prev_row)
        self.add_widget(right)

        self._refresh_list()
        self._load_slide(0)

    def _refresh_list(self):
        self._slide_list.clear_widgets()
        for i, s in enumerate(self.doc.slides):
            btn = Button(text=s["title"][:18], size_hint_y=None,
                         height=dp(34), font_size=12,
                         background_color=(0.25,0.35,0.5,1)
                         if i == self._active else (0.18,0.18,0.22,1))
            btn.bind(on_release=lambda inst, idx=i: self._load_slide(idx))
            self._slide_list.add_widget(btn)

    def _load_slide(self, idx):
        if not self.doc.slides:
            return
        idx = max(0, min(idx, len(self.doc.slides)-1))
        self._active = idx
        s = self.doc.slides[idx]
        self._title_in.text = s.get("title","")
        self._body_in.text  = s.get("body","")
        self._bg_in.text    = s.get("bg","#1A1A2E")
        self._fcol_in.text  = s.get("color","#FFFFFF")
        self._slide_idx_lbl.text = f"{idx+1}/{len(self.doc.slides)}"
        self._refresh_list()

    def _upd_slide(self, key, val):
        if self.doc.slides and 0 <= self._active < len(self.doc.slides):
            self.doc.slides[self._active][key] = val

    def _add_slide(self, *a):
        n = len(self.doc.slides)+1
        self.doc.slides.append({"title": f"Slide {n}", "body": "",
                                "color": "#FFFFFF", "bg": "#1A1A2E",
                                "image": None})
        self._load_slide(len(self.doc.slides)-1)

    def _del_slide(self, *a):
        if len(self.doc.slides) > 1:
            del self.doc.slides[self._active]
            self._load_slide(max(0, self._active-1))

    def _add_image(self, *a):
        chooser = FileChooserIconView(path=_home(),
            filters=["*.png","*.jpg","*.jpeg","*.webp"])
        btn = Button(text="Insert", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical")
        layout.add_widget(chooser)
        layout.add_widget(btn)
        popup = Popup(title="Slide Image", content=layout,
                      size_hint=(0.92, 0.92))

        def _do(*a):
            if chooser.selection:
                self._upd_slide("image", chooser.selection[0])
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _nav(self, delta):
        self._load_slide(self._active + delta)

    def _present(self, *a):
        """Show slides full-screen one by one in a Popup."""
        slides = self.doc.slides
        if not slides:
            return
        state = {"idx": self._active}

        def _build(idx):
            s     = slides[idx]
            bg    = s.get("bg","#1A1A2E")
            col   = s.get("color","#FFFFFF")
            title = s.get("title","")
            body  = s.get("body","")
            img   = s.get("image")

            layout = BoxLayout(orientation="vertical", padding=16, spacing=8)
            with layout.canvas.before:
                try:
                    h = bg.lstrip("#")
                    r,g,b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
                    Color(r, g, b, 1)
                except Exception:
                    Color(0.1, 0.1, 0.14, 1)
                layout._bg = Rectangle(pos=layout.pos, size=layout.size)
            layout.bind(pos=lambda inst,v: setattr(inst._bg,"pos",v),
                        size=lambda inst,v: setattr(inst._bg,"size",v))

            try:
                fc = col.lstrip("#")
                fr,fg,fb = int(fc[0:2],16)/255, int(fc[2:4],16)/255, int(fc[4:6],16)/255
                fcol = (fr, fg, fb, 1)
            except Exception:
                fcol = (1,1,1,1)

            layout.add_widget(Label(text=title, font_size=28, bold=True,
                                    size_hint_y=None, height=dp(48),
                                    color=fcol))
            if img and os.path.exists(img):
                layout.add_widget(KivyImage(source=img, size_hint_y=0.45,
                                            allow_stretch=True))
            layout.add_widget(Label(text=body, font_size=18, color=fcol,
                                    halign="left", valign="top"))

            nav = BoxLayout(size_hint_y=None, height=dp(44), spacing=8)
            pb = Button(text="< Prev", disabled=(idx==0))
            nb = Button(text="Next >", disabled=(idx==len(slides)-1))
            xb = Button(text="x Exit", size_hint_x=None, width=dp(90))
            lbl= Label(text=f"{idx+1}/{len(slides)}", size_hint_x=None,
                       width=dp(60), font_size=13)
            nav.add_widget(pb); nav.add_widget(lbl)
            nav.add_widget(nb); nav.add_widget(xb)
            layout.add_widget(nav)

            pp = Popup(title="", content=layout, size_hint=(0.96, 0.96),
                       separator_height=0)

            pb.bind(on_release=lambda *a: (pp.dismiss(), _show(idx-1)))
            nb.bind(on_release=lambda *a: (pp.dismiss(), _show(idx+1)))
            xb.bind(on_release=lambda *a: pp.dismiss())
            return pp

        def _show(idx):
            idx = max(0, min(idx, len(slides)-1))
            _build(idx).open()

        _show(state["idx"])


# ═══════════════════════════════════════════════════════════════════════════════
# SPREADSHEET PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class SpreadsheetPanel(BoxLayout):
    """
    Basic spreadsheet: editable grid, SUM/AVG/COUNT formulas,
    column/row headers, cell selection highlight.
    """

    def __init__(self, doc: Document, **kw):
        super().__init__(orientation="vertical", spacing=3, **kw)
        self.doc       = doc
        self._sel      = (0, 0)   # (row, col)
        self._cell_inputs = {}    # (r,c) -> TextInput

        # ── formula bar ──
        fbar = BoxLayout(size_hint_y=None, height=dp(36), spacing=6)
        fbar.add_widget(Label(text="Cell:", size_hint_x=None,
                              width=dp(40), font_size=13))
        self._cell_ref = Label(text="A1", size_hint_x=None,
                               width=dp(50), font_size=13,
                               color=(0.4, 0.8, 1, 1))
        fbar.add_widget(self._cell_ref)
        fbar.add_widget(Label(text="Formula:", size_hint_x=None,
                              width=dp(68), font_size=12))
        self._formula_in = TextInput(multiline=False, font_size=13,
                                     hint_text="=SUM(A1:A5)")
        self._formula_in.bind(on_text_validate=self._apply_formula)
        fbar.add_widget(self._formula_in)
        apply_f = Button(text=">", size_hint_x=None, width=dp(36), font_size=14)
        apply_f.bind(on_release=self._apply_formula)
        fbar.add_widget(apply_f)
        self.add_widget(fbar)

        # ── grid ──
        sv = ScrollView()
        rows = self.doc.sheet_rows
        cols = self.doc.sheet_cols
        grid = GridLayout(cols=cols+1, spacing=1, size_hint=(None, None))
        grid.bind(minimum_size=grid.setter("size"))

        col_letters = [chr(65+c) for c in range(cols)]

        # header row
        grid.add_widget(Label(text="", size_hint=(None,None),
                              size=(dp(30), dp(26)), font_size=10))
        for c in range(cols):
            grid.add_widget(Label(text=col_letters[c],
                                  size_hint=(None,None),
                                  size=(dp(90), dp(26)),
                                  font_size=11, bold=True,
                                  color=(0.6,0.8,1,1)))

        # data rows
        for r in range(rows):
            grid.add_widget(Label(text=str(r+1),
                                  size_hint=(None,None),
                                  size=(dp(30), dp(28)),
                                  font_size=10,
                                  color=(0.6,0.7,0.8,1)))
            for c in range(cols):
                val = self.doc.sheet[r][c] if (r < len(self.doc.sheet) and
                      c < len(self.doc.sheet[r])) else ""
                ti = TextInput(
                    text=val, multiline=False, font_size=12,
                    size_hint=(None,None), size=(dp(90), dp(28)),
                    background_color=(0.12,0.12,0.15,1),
                    foreground_color=(0.92,0.92,0.88,1),
                    cursor_color=(0.4,0.8,1,1),
                )
                ti.bind(focus=lambda inst, foc, row=r, col=c:
                        self._on_focus(inst, foc, row, col))
                ti.bind(text=lambda inst, val, row=r, col=c:
                        self._cell_changed(row, col, val))
                self._cell_inputs[(r,c)] = ti
                grid.add_widget(ti)

        sv.add_widget(grid)
        self.add_widget(sv)

    def _on_focus(self, inst, focused, row, col):
        if focused:
            self._sel = (row, col)
            letter = chr(65 + col)
            self._cell_ref.text = f"{letter}{row+1}"
            self._formula_in.text = inst.text

    def _cell_changed(self, r, c, val):
        while len(self.doc.sheet) <= r:
            self.doc.sheet.append([""] * self.doc.sheet_cols)
        while len(self.doc.sheet[r]) <= c:
            self.doc.sheet[r].append("")
        self.doc.sheet[r][c] = val

    def _apply_formula(self, *a):
        expr  = self._formula_in.text.strip()
        r, c  = self._sel
        if not expr.startswith("="):
            # plain value
            self._set_cell(r, c, expr)
            return
        try:
            result = self._eval_formula(expr[1:])
            self._set_cell(r, c, str(result))
        except Exception as e:
            self._set_cell(r, c, f"#ERR:{e}")

    def _set_cell(self, r, c, val):
        self._cell_changed(r, c, val)
        if (r,c) in self._cell_inputs:
            self._cell_inputs[(r,c)].text = val

    def _eval_formula(self, expr):
        import re
        expr_up = expr.upper()

        def _range_vals(ref):
            """Parse A1:B3 style range, return flat list of floats."""
            m = re.match(r"([A-Z])(\d+):([A-Z])(\d+)", ref.upper())
            if not m:
                return []
            c1 = ord(m.group(1))-65; r1 = int(m.group(2))-1
            c2 = ord(m.group(3))-65; r2 = int(m.group(4))-1
            vals = []
            for rr in range(r1, r2+1):
                for cc in range(c1, c2+1):
                    try:
                        v = self.doc.sheet[rr][cc]
                        vals.append(float(v))
                    except Exception:
                        pass
            return vals

        # SUM
        m = re.match(r"SUM\((.+)\)", expr_up)
        if m:
            return sum(_range_vals(m.group(1)))

        # AVG / AVERAGE
        m = re.match(r"(?:AVG|AVERAGE)\((.+)\)", expr_up)
        if m:
            v = _range_vals(m.group(1))
            return sum(v)/len(v) if v else 0

        # COUNT
        m = re.match(r"COUNT\((.+)\)", expr_up)
        if m:
            return len(_range_vals(m.group(1)))

        # MAX / MIN
        m = re.match(r"(MAX|MIN)\((.+)\)", expr_up)
        if m:
            v = _range_vals(m.group(2))
            return max(v) if m.group(1)=="MAX" else min(v)

        # simple arithmetic
        safe = re.sub(r"[^0-9+\-*/().\s]", "", expr)
        return eval(safe)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SCREEN
# ═══════════════════════════════════════════════════════════════════════════════
class FullEditorScreen(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.doc  = Document()
        self._dirty = False

        root = BoxLayout(orientation="vertical", padding=4, spacing=4)

        # ── file bar ──
        fbar = BoxLayout(size_hint_y=None, height=dp(40), spacing=5)
        self._doc_title = TextInput(text="Untitled", multiline=False,
                                    font_size=14, size_hint_x=0.35,
                                    hint_text="Document title")
        self._doc_title.bind(text=lambda inst,v: setattr(self.doc,"title",v))
        fbar.add_widget(self._doc_title)

        for lbl, cb in [("New", self._new), ("Open", self._open),
                         ("Save", self._save), ("Save As", self._save_as),
                         ("Export HTML", self._export_html)]:
            b = Button(text=lbl, font_size=12,
                       size_hint_x=None,
                       width=dp(90) if "Export" in lbl else dp(70))
            b.bind(on_release=cb)
            fbar.add_widget(b)

        self._status = Label(text="", font_size=11, halign="left")
        self._status.bind(size=self._status.setter("text_size"))
        fbar.add_widget(self._status)
        root.add_widget(fbar)

        # ── tabs ──
        self.tabs = TabbedPanel(do_default_tab=False, tab_height=dp(40))

        # Document tab
        doc_tab = TabbedPanelItem(text=" Document")
        self._rich = RichTextPanel(self.doc)
        doc_tab.add_widget(self._rich)
        self.tabs.add_widget(doc_tab)

        # Slides tab
        slides_tab = TabbedPanelItem(text=" Slides")
        self._slides = SlidesPanel(self.doc)
        slides_tab.add_widget(self._slides)
        self.tabs.add_widget(slides_tab)

        # Spreadsheet tab
        sheet_tab = TabbedPanelItem(text=" Sheet")
        self._sheet = SpreadsheetPanel(self.doc)
        sheet_tab.add_widget(self._sheet)
        self.tabs.add_widget(sheet_tab)

        root.add_widget(self.tabs)

        back = Button(text="< Back", size_hint_y=None, height=dp(44))
        back.bind(on_release=self._go_back)
        root.add_widget(back)

        self.add_widget(root)

    # ── file ops ──────────────────────────────────────────────────────────
    def _new(self, *a):
        self.doc = Document()
        self._doc_title.text = "Untitled"
        self._rebuild_panels()
        self._status.text = "New document"

    def _rebuild_panels(self):
        # replace panel content with fresh doc reference
        self._rich._refresh()
        self._slides._refresh_list()
        self._slides._load_slide(0)

    def _open(self, *a):
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
                try:
                    with open(chooser.selection[0], encoding="utf-8") as f:
                        self.doc.from_dict(json.load(f))
                    self.doc.path = chooser.selection[0]
                    self._doc_title.text = self.doc.title
                    self._rebuild_panels()
                    self._status.text = f"Opened: {self.doc.title}"
                except Exception as e:
                    self._popup("Error", str(e))
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _save(self, *a):
        if self.doc.path:
            self._write(self.doc.path)
        else:
            self._save_as()

    def _save_as(self, *a):
        docs_dir = app_data.subdir("full_editor")
        name_in  = TextInput(
            text=f"{self.doc.title}.srdoc",
            multiline=False, size_hint_y=None, height=dp(36), font_size=13)
        chooser  = FileChooserIconView(path=docs_dir)
        btn = Button(text="Save", size_hint_y=None, height=dp(44))
        layout = BoxLayout(orientation="vertical", spacing=4)
        layout.add_widget(chooser)
        layout.add_widget(name_in)
        layout.add_widget(btn)
        popup = Popup(title="Save As", content=layout, size_hint=(0.92,0.92))

        def _do(*a):
            path = os.path.join(chooser.path, name_in.text.strip())
            if not path.endswith(".srdoc"):
                path += ".srdoc"
            self.doc.path = path
            self._write(path)
            popup.dismiss()

        btn.bind(on_release=_do)
        popup.open()

    def _write(self, path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.doc.to_dict(), f, indent=2, ensure_ascii=False)
            self._status.text = f"Saved: {os.path.basename(path)}"
        except Exception as e:
            self._popup("Save error", str(e))

    def _export_html(self, *a):
        docs_dir = app_data.subdir("full_editor")
        path = os.path.join(docs_dir, f"{self.doc.title}.html")
        try:
            self._rich.export_html(path)
            self._status.text = f"Exported HTML: {path}"
            self._popup("Exported", path)
        except Exception as e:
            self._popup("Export error", str(e))

    def _go_back(self, *a):
        if self.manager:
            self.manager.current = "dashboard"

    def _popup(self, title, msg):
        Popup(title=title, content=Label(text=str(msg)),
              size_hint=(0.72, 0.38)).open()
