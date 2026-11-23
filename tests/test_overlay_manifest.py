"""The overlay player's manifest and Java sources are wired up (no kivy needed)."""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def rd(p):
    return open(os.path.join(ROOT, p), encoding="utf-8").read()

x = rd("intent_filters.xml")
main_part = x.split("</activity>")[0]
assert "audio/*" not in main_part.split("<action android:name=\"android.intent.action.SEND\"")[0]
assert "MiniPlayerActivity" in x and "PlayerService" in x
assert x.count("<activity") == 1 and x.count("</activity>") == 1
spec = rd("buildozer.spec")
assert "android.add_src = java" in spec and "FOREGROUND_SERVICE_MEDIA_PLAYBACK" in spec
for f in ("PlayerService", "MiniPlayerActivity"):
    assert os.path.exists(os.path.join(ROOT, "java/org/somore100/srboli", f + ".java"))
print("overlay manifest OK")
