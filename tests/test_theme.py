# Themes: presets switch the colour tokens; Settings saves and validates the choice.
# needs kivy and a display (CI skips it: tests/test_scripts.py looks for the word "kivy")
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import theme
from screens import settings_screen as ss

assert set(theme.PRESETS) == {"dark", "blue", "light", "custom"}
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

# the reorganised Settings screen builds and its controls still work
scr = ss.SettingsScreen(name="settings")
assert set(scr._theme_btns) == {"dark", "blue", "light", "custom"}
assert set(scr._pick_btns) == {("transition", "fade"), ("transition", "none"),
                               ("loading_style", "text"), ("loading_style", "logo"),
                               ("loading_style", "none")}
scr._set_theme("blue"); assert ss.load_settings()["theme"] == "blue"
scr._set_pick("loading_style", "logo"); assert ss.load_settings()["loading_style"] == "logo"
scr._toggle_rounded(None, False); assert ss.load_settings()["rounded"] is False
scr._reset_all(); assert ss.load_settings()["theme"] == "dark" and ss.load_settings()["rounded"] is True

# ---- custom colours -------------------------------------------------------------------
assert theme.parse_hex("#ff8000") == (1.0, 128 / 255, 0.0, 1) and theme.parse_hex("0f0")[1] == 1.0
assert theme.parse_hex("zzz") is None and theme.parse_hex("#12345") is None and theme.parse_hex(None) is None
assert theme.to_hex((1, 0.5, 0, 1)) == "#ff8000" and theme.to_hex(theme.parse_hex("#1a2b3c")) == "#1a2b3c"
assert theme.clean_custom({"BG": "#ABC", "TEXT": "nope", "junk": "#fff"}) == {"BG": "#aabbcc"}
assert theme.clean_custom("x") == {} and theme.clean_custom(None) == {}
assert theme.contrast((0, 0, 0, 1), (1, 1, 1, 1)) > 20 and theme.contrast((1, 1, 1, 1), (1, 1, 1, 1)) == 1
theme.set_custom({"BG": "#102030", "ACCENT": "#ff0000"})
c = theme.PRESETS["custom"]
assert theme.to_hex(c["BG"]) == "#102030" and c["ACCENT"][0] == 1 and c["TEXT"] == theme.PRESETS["dark"]["TEXT"]
assert c["MUTED"] != theme.PRESETS["dark"]["MUTED"] and len(c["MUTED"]) == 4
theme.apply("custom"); assert theme.BG == c["BG"] and theme.current == "custom"
d = ss.load_settings(); d["custom_colors"] = {"BG": "#010203", "TEXT": "nope"}; d["theme"] = "custom"; ss.save_settings(d)
d = ss.load_settings()
assert d["theme"] == "custom" and d["custom_colors"] == {"BG": "#010203"} and theme.saved_custom() == {"BG": "#010203"}
theme.apply("dark")

# ---- Settings screen: custom colour fields --------------------------------------------
scr = ss.SettingsScreen(name="settings")
assert set(scr._custom_in) == {"BG", "SURFACE", "SURFACE2", "TEXT", "ACCENT"}
scr._custom_in["BG"].text = "#223344"
assert "Looks fine" in scr._custom_msg.text, scr._custom_msg.text
scr._custom_in["ACCENT"].text = "red"
assert "Accent" in scr._custom_msg.text and scr._use_custom() is False
scr._custom_in["ACCENT"].text = "#00ff88"
scr._custom_in["TEXT"].text = "#223344"
assert "hard to read" in scr._custom_msg.text
scr._custom_in["TEXT"].text = "#eeeeee"
assert scr._use_custom() is True
d = ss.load_settings()
assert d["theme"] == "custom" and d["custom_colors"]["ACCENT"] == "#00ff88" and d["custom_colors"]["BG"] == "#223344"
assert tuple(scr._theme_btns["custom"].background_color) == theme.ACCENT

# ---- rounded inputs and popups follow the Rounded setting -------------------------------
theme.apply_shape(True)
assert theme.POPUP_IMG == theme.ROUND_PNG and theme.BTN_IMG == theme.ROUND_PNG
theme.apply_shape(False)
assert "modalview" in theme.POPUP_IMG and theme.BTN_IMG == "" and theme.POPUP_BORDER == (16, 16, 16, 16)
theme.apply_shape(True)
print("settings screen OK")
