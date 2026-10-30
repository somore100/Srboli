# tests/test_feedback_core.py - feedback_kit + Srboli's config. Pure; nothing is sent.
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import feedback_kit as fk
from core.feedback import make_config, SUPPORT_EMAIL
from core.version import VERSION, APP_NAME

cfg = make_config()
assert (cfg.app_name, cfg.app_version, cfg.to_email) == (APP_NAME, VERSION, "support.somore100@gmail.com")
assert cfg.endpoint.startswith("https://script.google.com/macros/s/"), cfg.endpoint
for bad in ("password", "api_key", "apikey", "secret"):
    assert bad not in open(os.path.join(os.path.dirname(__file__), "..", "feedback.json")).read().lower()

r = fk.Report(type_index=0, name="", title="  ", description="")
assert len(fk.validate(r)) == 2
r = fk.Report(type_index=0, title="Hi", description="short")
assert len(fk.validate(r)) == 2
r = fk.Report(type_index=0, name="Sam", title="UI is not working", description="The Settings screen shows nothing.")
assert fk.validate(r) == []
assert fk.build_subject(cfg, r) == "[Srboli] [BUG] UI is not working"
body = fk.build_body(cfg, r)
assert "Version:  " + VERSION in body and "From:     Sam" in body and "(not included)" in body
assert fk.build_subject(cfg, fk.Report(type_index=1, title="Custom themes")) == "[Srboli] [FEATURE] Custom themes"

info = fk.collect_system_info(VERSION)
for k in ("OS", "Architecture", "CPU", "GPU", "RAM", "App version"):
    assert k in info, k
import getpass, socket
flat = " ".join(map(str, info.values()))
assert getpass.getuser() not in flat or len(getpass.getuser()) < 4
assert socket.gethostname() not in flat
r.system = info
assert "== SYSTEM (sent because the user ticked the box) ==" in fk.build_body(cfg, r)

# the relay path posts JSON with the structured subject/body; no network used
seen = {}
class Resp:
    status = 200
    def read(self, n): return b'{"ok":true}'
    def __enter__(self): return self
    def __exit__(self, *a): pass
def fake(req, timeout=0):
    seen["url"], seen["data"] = req.full_url, json.loads(req.data)
    return Resp()
real = urllib.request.urlopen
urllib.request.urlopen = fake
try:
    res = fk.send_report(cfg, r)
finally:
    urllib.request.urlopen = real
assert res.ok and res.method == "relay" and seen["url"] == cfg.endpoint
assert seen["data"]["subject"].startswith("[Srboli] [BUG]") and seen["data"]["to"] == SUPPORT_EMAIL
print("feedback core OK")
