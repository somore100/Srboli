# Themes: presets switch the colour tokens; Settings saves and validates the choice.
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import theme
from screens import settings_screen as ss

assert set(theme.PRESETS) == {"dark", "blue", "light"}
for name, p in theme.PRESETS.items():
    for k in ("BG", "SURFACE", "SURFACE2", "TEXT", "MUTED", "ACCENT", "DANGER", "SUCCESS"):
        assert len(p[k]) == 4, (name, k)
theme.apply("blue"); assert theme.BG == theme.PRESETS["blue"]["BG"] and theme.current == "blue"
theme.apply("light"); assert theme.TEXT[0] < 0.3 and theme.BG[0] > 0.9
theme.apply("nonsense"); assert theme.current == "dark"
assert ss.load_settings()["theme"] == "dark"
d = ss.load_settings(); d["theme"] = "blue"; ss.save_settings(d)
assert ss.load_settings()["theme"] == "blue" and theme.saved_name() == "blue"
d["theme"] = "bogus"; ss.save_settings(d); assert ss.load_settings()["theme"] == "dark"
print("theme OK")
