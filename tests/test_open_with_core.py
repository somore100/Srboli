import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core import open_with_core as c
assert c.plan({"kind": "text", "text": "hi"}) == ("text_workbench", "set_text")
assert c.plan({"kind": "file", "name": "a.txt", "mime": "text/plain"}, 100) == ("text_editor", "open_path")
assert c.plan({"kind": "file", "name": "notes.md", "mime": ""}, 100)[0] == "text_editor"
assert c.plan({"kind": "file", "name": "big.txt", "mime": "text/plain"}, 5_000_000)[0] == "file_inspector"
assert c.plan({"kind": "file", "name": "x.mp3", "mime": "audio/mpeg"}, 10) == ("music", "play")
assert c.plan({"kind": "file", "name": "x.bin", "mime": ""}, 10) == ("file_inspector", "inspect")
ch = c.choices({"kind": "file", "name": "song.mp3", "mime": ""}, 10)
assert [x[0] for x in ch] == ["music", "file_inspector"] and ch[0][2] == "Play in Music Player"
assert [x[0] for x in c.choices({"kind": "file", "name": "n.txt", "mime": "text/plain"}, 10)] == ["text_editor", "file_inspector"]
assert [x[0] for x in c.choices({"kind": "text", "text": "hi"})] == ["text_workbench"]
assert c.safe_name("../../etc/pas:swd") == "pas_swd" or c.safe_name("../../etc/pas:swd") == "passwd" or "/" not in c.safe_name("../../etc/pas:swd")
assert c.safe_name("") == "shared_file" and c.safe_name("..") == "shared_file"
d = tempfile.mkdtemp(); open(os.path.join(d, "a.txt"), "w").close()
assert os.path.basename(c.unique_path(d, "a.txt")) == "a (2).txt"
assert os.path.dirname(c.unique_path(d, "../x.txt")) == d
print("open-with core OK")
