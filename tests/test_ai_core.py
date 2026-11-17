# tests/test_ai_core.py - no display needed. A tiny local HTTP server plays
# Ollama / an OpenAI-style API / Anthropic, so the real request code runs.
import os, sys, json, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import app_data
app_data.set_data_dir(tempfile.mkdtemp(), move_old=False)
from core import ai_core, ai_rules

seen = []
ANSWER = {"text": "hello"}
CODE = {"n": 200}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        seen.append(("GET", self.path, dict(self.headers)))
        self._send({"models": [{"name": "llama3.2:latest"}]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append(("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if CODE["n"] != 200:
            return self._send({"error": "x"}, CODE["n"])
        t = ANSWER["text"]
        if self.path.endswith("/api/chat"):
            self._send({"message": {"content": t}})
        elif self.path.endswith("/chat/completions"):
            self._send({"choices": [{"message": {"content": t}}]})
        elif self.path.endswith("/v1/messages"):
            self._send({"content": [{"type": "text", "text": t}]})
        else:
            self._send({}, 404)

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_port}"

# off by default, nothing usable
cfg = ai_core.load()
assert cfg["enabled"] is False and not ai_core.enabled("file_sorter")
assert ai_core.problem(cfg)                       # no model yet

def mk(provider, model="m", key="K"):
    c = ai_core.load()
    c["enabled"] = True; c["provider"] = provider
    c["urls"][provider] = URL; c["models"][provider] = model
    c["api_key"] = key; c["tools"] = {k: True for k in ai_core.TOOLS}
    return c

# save / load round trip, key file private
c = mk("ollama", "llama3.2")
assert ai_core.save(c)
back = ai_core.load()
assert back["enabled"] and back["models"]["ollama"] == "llama3.2"
assert ai_core.enabled("file_sorter") and ai_core.enabled()
back["tools"]["file_sorter"] = False
assert not ai_core.enabled("file_sorter", back) and ai_core.enabled("text_editor", back)
back["enabled"] = False
assert not ai_core.enabled("text_editor", back)   # master switch wins
assert oct(os.stat(ai_core._path()).st_mode & 0o777) == "0o600"

# all three providers
ANSWER["text"] = "pong"
for p, path in (("ollama", "/api/chat"), ("openai", "/chat/completions"),
                ("anthropic", "/v1/messages")):
    seen.clear()
    assert ai_core.chat("sys", "ping", mk(p)) == "pong", p
    req = seen[-1]
    assert req[1].endswith(path) and req[0] == "POST"
    if p == "openai": assert req[2]["authorization"] == "Bearer K"
    if p == "anthropic":
        assert req[2]["x-api-key"] == "K" and req[3]["system"] == "sys"
    if p == "ollama": assert "authorization" not in req[2] and req[3]["stream"] is False

# errors are worded, never raw tracebacks
for code, word in ((401, "key"), (404, "model"), (429, "credit")):
    CODE["n"] = code
    try: ai_core.chat("s", "u", mk("openai")); assert False
    except ai_core.AIError as e: assert word in str(e), (code, str(e))
CODE["n"] = 200
dead = mk("ollama", "x"); dead["urls"]["ollama"] = "http://127.0.0.1:1"
try: ai_core.chat("s", "u", dead); assert False
except ai_core.AIError as e: assert "reach" in str(e)
try: ai_core.chat("s", "x" * (ai_core.MAX_TEXT + 1), mk("ollama")); assert False
except ai_core.AIError as e: assert "too much" in str(e)
ANSWER["text"] = "  "
try: ai_core.chat("s", "u", mk("ollama")); assert False
except ai_core.AIError as e: assert "empty" in str(e)

# a key never goes over plain http to a non-local address
bad = mk("openai"); bad["urls"]["openai"] = "http://example.com/v1"
assert "https" in ai_core.problem(bad)
assert ai_core.problem(mk("openai")) is None      # localhost is fine

# test_connection
ok, msg = ai_core.test_connection(mk("ollama", "llama3.2"))
assert ok, msg
ok, msg = ai_core.test_connection(mk("ollama", "nope"))
assert not ok and "llama3.2" in msg and "pull" in msg
ANSWER["text"] = "OK"
ok, msg = ai_core.test_connection(mk("anthropic"))
assert ok and "OK" in msg
assert not ai_core.test_connection(json.loads(json.dumps(ai_core.DEFAULTS)))[0]

# extract_json
assert ai_core.extract_json('Sure!\n```json\n{"a": {"b": "}"}}\n```') == {"a": {"b": "}"}}
assert ai_core.extract_json("no json") is None
assert ai_core.extract_json('x {bad} {"ok": 1}') == {"ok": 1}

# edit_text
ANSWER["text"] = "```\nFixed text.\n```"
assert ai_core.edit_text("fix", "fixd txt", cfg=mk("ollama")) == "Fixed text."
try: ai_core.edit_text("fix", "  ", cfg=mk("ollama")); assert False
except ai_core.AIError: pass
try: ai_core.edit_text("custom", "abc", "", cfg=mk("ollama")); assert False
except ai_core.AIError: pass
ai_core.edit_text("custom", "abc", "translate to German", cfg=mk("ollama"))
assert "translate to German" in seen[-1][3]["messages"][0]["content"]

# ── rule writer ──
good = {"logic": "AND", "conditions": [
    {"field": "name", "op": "contains", "value": "roblox"},
    {"field": "file_type", "op": "is", "value": "video"}],
    "action": {"type": "move", "dest": "/home/videos/roblox"}}
rule, note = ai_rules.clean_rule(good)
assert rule["conditions"][1]["value"] == "Video" and rule["action"]["dest"] == "/home/videos/roblox", rule
# junk is dropped, not passed on
rule, note = ai_rules.clean_rule({"conditions": [
    {"field": "colour", "op": "is", "value": "red"},
    {"field": "name", "op": "contains", "value": ""},
    {"field": "extension", "op": "is_one_of", "value": ".JPG, png"}],
    "action": {"type": "move", "dest": "/x"}})
assert rule["conditions"] == [{"field": "extension", "op": "is_one_of", "value": "jpg,png"}], rule
assert "dropped" in note
assert ai_rules.clean_rule({"conditions": [], "action": {"type": "move", "dest": "/x"}})[0] is None
assert ai_rules.clean_rule({"conditions": good["conditions"], "action": {"type": "move"}})[0] is None
assert ai_rules.clean_rule({"conditions": good["conditions"], "action": {"type": "format_disk"}})[0] is None
assert "can't be done" in ai_rules.clean_rule({"error": "too vague"})[1]
dup = {"conditions": [good["conditions"][0], dict(good["conditions"][0])], "action": good["action"]}
assert ai_rules.clean_rule(dup)[0] is None
# a delete rule never auto-deletes
rule, note = ai_rules.clean_rule({"conditions": [good["conditions"][0]],
                                  "action": {"type": "delete", "auto_delete": True}})
assert rule["action"]["auto_delete"] is False and "ask" in note
# end to end through the fake server
ANSWER["text"] = "Here you go:\n```json\n" + json.dumps(good) + "\n```"
rule, note = ai_rules.rule_from_words("roblox videos to the roblox folder", mk("ollama"))
assert rule and rule["action"]["type"] == "move"
sysmsg = seen[-1][3]["messages"][0]["content"]
assert "file_type" in sysmsg and "is_one_of" in sysmsg
ANSWER["text"] = "I cannot help"
rule, note = ai_rules.rule_from_words("x", mk("ollama"))
assert rule is None and "didn't answer" in note
print("ai core ok")
