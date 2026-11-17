# tests/test_ai_screens.py - needs a display (kivy).
# AI is off by default and invisible; the Settings block saves; turning it on
# (provider + tool ticked) shows the File Sorter and Text Editor buttons; the
# editor only changes the text when "Use it" is pressed.
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config
Config.set("graphics", "width", "1000"); Config.set("graphics", "height", "800")
from kivy.clock import Clock
from core import ai_core
from screens.ai_settings import AISettings
import screens.file_sorter_screen as fsx
import screens.text_editor_screen as tex

# off by default: buttons exist but take no room and can't be touched
fs = fsx.FileSorterScreen(name="fs"); fs.on_pre_enter()
assert fs._ai_btn.height == 0 and fs._ai_btn.disabled and fs._ai_btn.opacity == 0
te = tex.TextEditorScreen(name="te"); te.on_pre_enter()
assert te._ai_row.height == 0 and te._ai_row.disabled

# settings block: greyed while off, saves, test refuses an unfinished form
s = AISettings()
assert not s.master.active and s.body.disabled and s.body.opacity < 1
s.master.active = True
assert not s.body.disabled
assert not ai_core.enabled()                     # on, but no model yet -> still off
s.model.text = "llama3.2"
s.tool_boxes["file_sorter"].active = True
s._save(True)
assert "Saved" in s.status.text
cfg = ai_core.load()
assert cfg["enabled"] and cfg["models"]["ollama"] == "llama3.2"
assert ai_core.enabled("file_sorter") and not ai_core.enabled("text_editor")

# provider switch keeps each provider's own fields, shows the key box
s.provider.text = ai_core.PROVIDER_LABELS["openai"]
assert s.key_box.height > 0 and s.model.text == ""
s.model.text = "gpt-x"; s.key.text = "sk-1"
s.provider.text = ai_core.PROVIDER_LABELS["ollama"]
assert s.model.text == "llama3.2" and s.key_box.height == 0
assert s._collect()["models"]["openai"] == "gpt-x"

# now the buttons appear where ticked
fs.on_pre_enter(); te.on_pre_enter()
assert fs._ai_btn.height > 0 and not fs._ai_btn.disabled
assert te._ai_row.height == 0                    # text editor not ticked
cfg["tools"]["text_editor"] = True; ai_core.save(cfg)
te.on_pre_enter()
assert te._ai_row.height > 0 and not te._ai_row.disabled

# AI rule opens in the editor and adds nothing until saved
before = len(fs._rules)
fs._open_ai_rule({"logic": "AND", "conditions": [
    {"field": "name", "op": "contains", "value": "roblox"}],
    "action": {"type": "move", "dest": "/home/videos/roblox"}}, "")
assert len(fs._rules) == before

# text editor: review popup applies only on Use it, and not if text moved on
te._ed.text = "hello wrold"
te._ai_review("hello wrold", "hello world", 0, 11)
assert te._ed.text == "hello wrold"
from kivy.uix.popup import Popup
from kivy.core.window import Window
pops = [w for w in Window.children if isinstance(w, Popup)]
use = pops[0].content.children[0].children[-1]   # row -> first button
assert use.text == "Use it"
te._ed.text = "changed meanwhile"
use.dispatch("on_release")
assert te._ed.text == "changed meanwhile"
te._ed.text = "hello wrold"
te._ai_review("hello wrold", "hello world", 0, 11)
pops = [w for w in Window.children if isinstance(w, Popup)]
pops[0].content.children[0].children[-1].dispatch("on_release")
assert te._ed.text == "hello world", te._ed.text

# Learn: the AI button only exists when the learn tool is ticked
import screens.learn_screen as lsx
ls = lsx.LearnScreen(name="l"); ls._show_home()
def texts(w):
    out = []
    for c in w.walk():
        if getattr(c, "text", None): out.append(c.text)
    return out
assert not any("with AI" in t for t in texts(ls))
cfg = ai_core.load(); cfg["tools"]["learn"] = True; ai_core.save(cfg)
ls._show_home()
assert any("Write a course with AI" in t for t in texts(ls))
ls._ai_course()
# the Ollama guide opens and offers a model
s3 = AISettings()
s3._guide()
from kivy.uix.popup import Popup
from kivy.core.window import Window as W
guide = [w for w in W.children if isinstance(w, Popup) and w.title == "Set up Ollama"]
assert guide and any("Use " in t for t in texts(guide[0]))
print("ai screens ok")
