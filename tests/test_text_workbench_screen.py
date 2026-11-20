# tests/test_text_workbench_screen.py - xvfb-run -a python3 tests/test_text_workbench_screen.py
import os, sys, tempfile
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from screens.text_workbench_screen import TextWorkbenchScreen

s = TextWorkbenchScreen()
s.input.text = "b\na\nb\n"
s.line_op.text = "Sort A-Z"; s.run_lines()
assert s.output.text == "a\nb\nb", s.output.text
s.use_result(); assert s.input.text == "a\nb\nb" and s.output.text == ""
s.line_op.text = "Remove duplicate lines"; s.run_lines(); assert s.output.text == "a\nb"
s.line_op.text = "Keep lines containing..."; s.line_arg.text = ""; s.run_lines()
assert s.output.text == "" and "option box" in s.status.text
s.show_tab("extract"); s.input.text = "x@y.io z"; s._guard(s._do_extract)
assert s.output.text == "x@y.io"
s.show_tab("regex"); s.rx_pat.text = "("; assert "isn't valid" in s.status.text
s.rx_pat.text = r"(\w)@"; assert "1 match" in s.output.text
s.rx_rep.text = r"<\1>"; s._guard(s._do_rx_replace); assert s.output.text == "<x>y.io z"
s.show_tab("diff"); assert not s.input_b.disabled and s.input_b.opacity == 1
s.input.text = "a\nb"; s.input_b.text = "a\nc"; s._guard(s._do_diff)
assert "- b" in s.output.text and "+ c" in s.output.text
s.show_tab("stats"); assert "Words: 2" in s.output.text
s.show_tab("lines"); assert s.input_b.disabled and s.input_b.height == 0
p = os.path.join(tempfile.mkdtemp(), "t.txt"); open(p, "w").write("hello file")
s._load(p); assert s.input.text == "hello file"
open(p, "wb").write(b"\x00\x01bin"); s.input.text = ""; s._load(p)
assert s.input.text == "" and "binary" in s.status.text
s.clear(); assert s.input.text == s.output.text == ""
s.set_text("shared words"); assert s.input.text == "shared words" and "Shared" in s.status.text
print("text workbench screen: all ok")
