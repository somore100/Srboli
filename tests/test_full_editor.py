# tests/test_full_editor.py - needs a display (xvfb-run -a python3 tests/test_full_editor.py)
import os, sys, tempfile, json
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
import screens.full_editor_screen as fe
from core import outline_core as O
from core import slides_core as S
from core import table_core as T

# ── model ──
d = fe.Document()
d.from_dict({"title": "T", "slides": [{"title": "S"}], "sheet": [["1", None, 3]]})
assert d.title == "T"
# hand-written slides from older files are kept as sections
assert [n["title"] for n in d.outline][-2:] == ["Slides (imported)", "S"]
assert d.outline and not d.dirty
assert len(d.tables) == 1 and d.tables[0]["name"] == "Sheet 1"      # old "sheet" grid
assert d.tables[0]["cells"][0][2]["t"] == "3"
d.from_dict({})                                                 # nothing leaks over
assert d.title == "Untitled" and len(d.outline) == 1
assert d.slide_mode == "separate" and d.title_slide and d.title_style == {}
try:
    d.from_dict([1, 2]); assert False
except ValueError:
    pass

# version 1 files (flat paragraphs) become one section
d.from_dict({"paragraphs": [{"text": "old", "color": "#FF0000"}]})
assert len(d.outline) == 1 and "old" in d.outline[0]["body"]
assert "[color=#FF0000]" in d.outline[0]["body"]
assert d.to_dict()["version"] == 4 and "paragraphs" not in d.to_dict() and "sheet" not in d.to_dict()

# ── HTML export escapes and includes all three parts ──
d = fe.Document()
d.title = "<b>x</b>"
d.outline[0]["body"] = "<script>alert(1)</script>"
d.outline.append(O.blank_node("Hello & bye", 0))
d.tables = [T.blank_table("Plan", 2, 2)]
d.tables[0]["cells"][0][0].update(t="42", bg="#112233")
d.outline[0]["body"] += "\n\n[[table:Plan]]"
d.tables.append(T.blank_table("Loose", 1, 1)); d.tables[1]["cells"][0][0]["t"] = "free"
out = os.path.join(tempfile.mkdtemp(), "o.html")
fe.export_html(d, out)
h = open(out, encoding="utf-8").read()
assert "<script>" not in h and "&lt;script&gt;" in h
assert "Hello &amp; bye" in h and ">42</td>" in h and "background:#112233" in h
# the placed table shows in its section AND on that section's slide; the loose one
# (never placed) is listed once at the end
assert h.count("<table") == 3 and "<h3>Loose</h3>" in h and "<h3>Hello &amp; bye</h3>" in h

# ── screen: one shared document, dirty tracking, New/Open reload panels ──
scr = fe.FullEditorScreen()
doc = scr.doc
assert scr._outline.doc is doc and scr._slides.doc is doc and scr._tables.doc is doc
assert not doc.dirty
tp = scr._tables
tp._add_table()                                  # no tables by default
assert doc.dirty and len(doc.tables) == 1 and (0, 0) in tp._cells
tp._cell_changed(0, 0, "5")
assert doc.dirty and scr._status.text.startswith("*")
path = os.path.join(tempfile.mkdtemp(), "a.srdoc")
assert scr._write(path) and not doc.dirty
scr._outline._add_item()
assert doc.dirty and len(doc.outline) == 2
scr._do_new()
assert scr.doc is doc and not doc.dirty and len(doc.outline) == 1
assert doc.tables == [] and tp._cells == {}
doc.from_dict(json.load(open(path)))
scr._reload_panels()
assert tp._cells[(0, 0)].text == "5" and not doc.dirty
# showing a slide must not count as an edit
scr._slides._select(0)
assert not doc.dirty
# ── outline panel: tree edits, title/body edits, selection ──
op = scr._outline
doc.reset(); scr._reload_panels()
op._add_sub()                                  # Section 1 > Section 2
assert [n["depth"] for n in doc.outline] == [0, 1] and doc.active_node == 1
assert doc.dirty
op._editor.ed.text = "# hi\n**bold**"          # user types in the body
assert doc.outline[1]["body"] == "# hi\n**bold**"
op._title_in.text = "Goals"
assert doc.outline[1]["title"] == "Goals"
row = op._title_btns[1].text            # title, then a dim preview of the body
assert row.startswith("Goals") and "hi" in row
op._select(0)
assert op._title_in.text == "Section 1" and op._editor.text == ""
assert doc.outline[1]["body"] == "# hi\n**bold**"   # switching sections keeps text
op._toggle(0)                                  # collapse -> child hidden
assert list(op._title_btns) == [0]
op._select(0); op._add_item(); op._select(2); op._indent()
assert [n["depth"] for n in doc.outline] == [0, 1, 1]
op._body_changed("x")
assert scr._write(path) and not doc.dirty
doc.from_dict(json.load(open(path))); scr._reload_panels()
assert [n["title"] for n in doc.outline][1] == "Goals" and not doc.dirty
# ── slides panel: derived from the outline ──
doc.reset(); scr._reload_panels()
sp = scr._slides
doc.outline[0]["title"] = "Intro"
op._select(0); op._add_sub(); doc.outline[1]["title"] = "Next"
sp._refresh()
assert [x["title"] for x in sp._slides] == ["Untitled", "Intro", "Next"]   # title slide first
sp._select(1)
sp._pick_color("#112233")                        # "Bg" is the default target
assert doc.outline[0]["slide"]["bg"] == "#112233" and sp._slides[1]["bg"] == "#112233"
assert doc.dirty
sp._bg_btn.state = "normal"; sp._fg_btn.state = "down"
sp._pick_color("#FFEEDD")
assert sp._slides[1]["fg"] == "#FFEEDD"
sp._skip_tg.state = "down"                       # skip this section's slide
assert sp._slides[1]["skip"] and [x["title"] for x in S.visible(sp._slides)] == ["Untitled", "Next"]
sp._reset_colors()
assert "bg" not in doc.outline[0]["slide"] and sp._slides[1]["skip"]
sp._select(0)
assert sp._skip_tg.disabled                      # the title slide has its own toggle
sp._select(2); sp._edit_section()
assert doc.active_node == 1                      # jumped to that section in the Document tab
sp._mode_sp.text = S.MODES["bullets"]
assert doc.slide_mode == "bullets"
assert [x["title"] for x in sp._slides] == ["Untitled", "Intro"] and "- Next" in sp._slides[1]["body"]
sp._title_tg.state = "normal"
assert not doc.title_slide and [x["title"] for x in sp._slides] == ["Intro"]
sp._present()                                    # doesn't crash
assert scr._write(path)
saved = json.load(open(path))
assert saved["version"] == 4 and "slides" not in saved and saved["slide_opts"]["mode"] == "bullets"
doc.from_dict(saved); scr._reload_panels()
assert doc.slide_mode == "bullets" and not doc.title_slide and doc.outline[0]["slide"] == {"skip": True}
assert not doc.dirty

# ── tables panel ──
doc.reset(); scr._reload_panels()
assert doc.tables == []                          # empty state, nothing crashes
tp._structure("add_row"); tp._apply_formula(); tp._clear_colors()
tp._add_table(); tp._add_table()
assert [t["name"] for t in doc.tables] == ["Table 1", "Table 2"] and doc.active_table == 1
tp._pick_table(None, "Table 1")
assert doc.active_table == 0
t0 = doc.tables[0]
tp._sel = (1, 2)
tp._structure("add_row")                         # new row below the selected one
assert T.size(t0) == (9, 6) and tp._sel == (2, 2) and len(tp._cells) == 9 * 6
tp._structure("del_row"); tp._structure("add_col"); tp._structure("del_col")
assert T.size(t0) == (8, 6)
# colours: fill the whole row, then text colour on one cell, then clear
tp._sel = (0, 1)
tp._scope_sp.text = "Row"
tp._apply_color("#3DDC84")
assert all(c["bg"] == "#3DDC84" for c in t0["cells"][0]) and t0["cells"][1][0]["bg"] == ""
assert tuple(tp._cells[(0, 3)].background_color[:3]) != tp.DEFAULT_BG[:3]
tp._scope_sp.text = "Cell"; tp._fill_btn.state = "normal"; tp._text_btn.state = "down"
tp._apply_color("#112233")
assert t0["cells"][0][1]["fg"] == "#112233" and t0["cells"][0][2]["fg"] == ""
tp._strip._wheel_picked("#abcdef")              # wheel pick: applied + remembered
assert t0["cells"][0][1]["fg"] == "#ABCDEF"
from screens.md_editor import RECENT_COLORS
assert RECENT_COLORS[0] == "#ABCDEF"
tp._clear_colors()
assert t0["cells"][0][1]["fg"] == "" and t0["cells"][0][1]["bg"] == ""
# formulas
t0["cells"][3][0]["t"] = "4"; t0["cells"][4][0]["t"] = "6"
tp._sel = (5, 0); tp._formula_in.text = "=SUM(A1:A5)"; tp._apply_formula()
assert t0["cells"][5][0]["t"] == "10" and tp._cells[(5, 0)].text == "10"
tp._formula_in.text = "=A4*2+1"; tp._apply_formula()
assert t0["cells"][5][0]["t"] == "9"
tp._formula_in.text = "=9**9**9"; tp._apply_formula()
assert t0["cells"][5][0]["t"] == "#ERR"
# placing a table into a section, then renaming it
doc.outline[0]["body"] = "see\n\n[[table:Table 1]]\n"
tp._name_in.text = "Timetable"; tp._rename()
assert doc.tables[0]["name"] == "Timetable" and "[[table:Timetable]]" in doc.outline[0]["body"]
tp._name_in.text = "Table 2"; tp._rename()      # name taken -> made unique
assert doc.tables[0]["name"] == "Table 2 2"
assert len({t["name"] for t in doc.tables}) == 2
# save + reload keeps colours and text
tp._sel = (0, 0); tp._scope_sp.text = "Cell"; tp._text_btn.state = "normal"; tp._fill_btn.state = "down"; tp._apply_color("#FF0000")
assert scr._write(path)
saved = json.load(open(path))
assert saved["version"] == 4 and "sheet" not in saved and "slides" not in saved and saved["tables"][0]["cells"][0][0]["bg"] == "#FF0000"
doc.from_dict(saved); scr._reload_panels()
assert tp._cells[(0, 0)].background_color[0] == 1.0 and not doc.dirty
# deleting an empty table needs no confirmation
tp._pick_table(None, doc.tables[1]["name"]); n = len(doc.tables)
tp._del_table()
assert len(doc.tables) == n - 1
# the outline panel's insert-table button and preview don't crash
scr._outline._insert_table(); scr._outline._preview_all()
print("full editor OK")
