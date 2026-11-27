# needs kivy and a display (CI skips it: tests/test_scripts.py looks for the word "kivy")
# Loading screen styles, screen-change setting, open_screen behaviour.
import os, sys, tempfile, time
os.environ["KIVY_NO_ARGS"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kivy.base import EventLoop
EventLoop.ensure_window()
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen, ScreenManager, NoTransition
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import theme; theme.install()
import core.navigation as nav
from screens import settings_screen as ss

assert ss.load_settings()["transition"] == "fade" and ss.load_settings()["loading_style"] == "none"
d = ss.load_settings(); d["transition"] = "bogus"; d["loading_style"] = "none"; ss.save_settings(d)
assert ss.load_settings()["transition"] == "fade" and ss.load_settings()["loading_style"] == "none"
assert os.path.isfile(os.path.join(os.path.dirname(nav.__file__), "..", "loading.png"))

for style in ("logo", "text"):
    scr = nav._loading_screen(style)
    assert scr.name == nav.LOADING and scr.children

def run(style):
    nav.LOADING_STYLE = style
    sm = ScreenManager(transition=NoTransition())
    sm.add_widget(Screen(name="home")); sm.current = "home"
    seen = []
    nav.open_screen(sm, "tool", lambda r: (seen.append(sm.current), sm.add_widget(Screen(name=r)) or True)[1], delay=0.01)
    t = time.time() + 1
    while time.time() < t and sm.current != "tool":
        Clock.tick(); time.sleep(0.01)
    return sm.current, seen

assert run("logo") == ("tool", [nav.LOADING])
assert run("text") == ("tool", [nav.LOADING])
assert run("none") == ("tool", ["home"])          # never shows the loading screen
print("loading OK")
