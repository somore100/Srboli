# tests/test_file_inspector_screen.py - xvfb-run -a python3 tests/test_file_inspector_screen.py
import hashlib, os, sys, tempfile, time
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from screens.file_inspector_screen import FileInspectorScreen

def pump(cond, secs=5):
    t = time.time()
    while not cond() and time.time() - t < secs:
        Clock.tick(); time.sleep(0.01)
    return cond()

d = tempfile.mkdtemp()
p = os.path.join(d, "pic.jpg")
data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"x" * 5000
open(p, "wb").write(data)
s = FileInspectorScreen()
s.inspect(os.path.join(d, "nope")); assert "doesn't exist" in s.status.text and s.info is None
s.inspect(p)
assert "PNG image" in s.output.text and "WARNING" in s.output.text, s.output.text
assert s.path_in.text == p
s.show_tab("hash"); assert "Press Calculate" in s.output.text
s.calculate(); assert pump(lambda: bool(s.digests)), "hashes never finished"
assert hashlib.sha256(data).hexdigest() in s.output.text and not s.calc_btn.disabled
s.expected.text = hashlib.sha256(data).hexdigest(); assert "MATCH" in s.status.text
s.expected.text = "0" * 64; assert "DIFFERENT" in s.status.text
s.show_tab("preview"); s.set_mode("hex"); assert s.output.text.startswith("00000000  89 50 4e 47")
s.set_mode("text"); assert "isn't text" in s.status.text and s.output.text == ""
s.show_tab("info"); assert "Permissions" in s.output.text
# a folder
s.inspect(d); assert "Folder" in s.output.text
s.show_tab("hash"); s.calculate(); assert "Choose a file" in s.status.text or "for files" in s.status.text
s.show_tab("preview"); assert "files" in s.output.text.lower()
# choosing another file while a checksum would be running discards the old result
q = os.path.join(d, "q.txt"); open(q, "w").write("hello\n")
s.inspect(q); s.show_tab("info"); assert "Plain text" in s.output.text and "1 lines" in s.output.text
print("file inspector screen: all ok")
