# Themes: presets switch the colour tokens; Settings saves and validates the choice.
# needs kivy and a display (CI skips it: tests/test_scripts.py looks for the word "kivy")
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

# rounded buttons + mini player helpers
theme.apply_shape(True); assert theme.rounded and theme.BTN_RADIUS > 0 and theme.BTN_IMG.endswith("round.png")
theme.apply_shape(False); assert not theme.rounded and theme.BTN_IMG == "" and theme.BTN_RADIUS == 0
assert ss.load_settings()["rounded"] is True
from core.mini_player import fmt_time, clamp
assert fmt_time(11) == "00:11" and fmt_time(171) == "02:51" and fmt_time(None) == "00:00"
assert clamp(2) == 1 and clamp(-1) == 0
from core import open_with_core as owc
assert owc.is_audio({"kind": "file", "name": "a.MP3"}) and owc.is_audio({"kind": "file", "name": "x", "mime": "audio/ogg"})
assert not owc.is_audio({"kind": "file", "name": "a.txt"}) and not owc.is_audio({"kind": "text", "text": "x"})
print("shape/mini OK")
