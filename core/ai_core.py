# core/ai_core.py - the one door from Srboli to an AI model. No UI, no Kivy.
#
# Off by default. Nothing here ever runs by itself: a screen calls chat() only
# when the user presses one of its AI buttons, and a screen only shows such a
# button when enabled(tool) is true (master switch on, that tool ticked, and a
# provider filled in).
#
# Three kinds of provider, all spoken to with plain HTTP (standard library):
#   ollama     a model running on this PC (or another PC on the network)
#   openai     any "OpenAI compatible" service: OpenAI, OpenRouter, LM Studio...
#   anthropic  Anthropic's API
# The API key lives in <data>/config/ai.json on this device only.

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

import app_data
from core.jsonio import read_json, write_json_atomic

PROVIDERS = ["ollama", "openai", "anthropic"]
PROVIDER_LABELS = {"ollama": "Ollama (local model)",
                   "openai": "OpenAI-compatible API",
                   "anthropic": "Anthropic API"}
DEFAULT_URLS = {"ollama": "http://localhost:11434",
                "openai": "https://api.openai.com/v1",
                "anthropic": "https://api.anthropic.com"}

# the screens that have AI buttons: key -> what the button does
TOOLS = {
    "file_sorter": "File Sorter - write a rule from a plain-words description",
    "text_editor": "Text Editor - fix, shorten or rewrite text",
    "learn": "Learn - write a whole course from a topic",
}

DEFAULTS = {
    "enabled": False,
    "provider": "ollama",
    "urls": dict(DEFAULT_URLS),
    "models": {"ollama": "", "openai": "", "anthropic": ""},
    "api_key": "",
    "tools": {k: False for k in TOOLS},
    "timeout": 120,
}
MAX_TEXT = 12000          # characters sent in one request


class AIError(Exception):
    """A problem with a request, worded for the user."""


def _path():
    return os.path.join(app_data.subdir("config"), "ai.json")


def load():
    raw = read_json(_path(), {})
    raw = raw if isinstance(raw, dict) else {}
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg["enabled"] = bool(raw.get("enabled", False))
    if raw.get("provider") in PROVIDERS:
        cfg["provider"] = raw["provider"]
    for key in ("urls", "models"):
        if isinstance(raw.get(key), dict):
            for p in PROVIDERS:
                if isinstance(raw[key].get(p), str):
                    cfg[key][p] = raw[key][p].strip()
    if isinstance(raw.get("api_key"), str):
        cfg["api_key"] = raw["api_key"].strip()
    if isinstance(raw.get("tools"), dict):
        for t in TOOLS:
            cfg["tools"][t] = bool(raw["tools"].get(t, False))
    try:
        cfg["timeout"] = max(10, min(600, int(raw.get("timeout", 120))))
    except (TypeError, ValueError):
        pass
    return cfg


def save(cfg):
    try:
        write_json_atomic(_path(), cfg)
        try:
            os.chmod(_path(), 0o600)        # holds the key: owner only
        except OSError:
            pass
        return True
    except Exception:
        return False


def problem(cfg):
    """Why this setup can't be used yet, or None."""
    p = cfg["provider"]
    url = (cfg["urls"].get(p) or "").strip()
    if not url:
        return "Fill in the address."
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return "The address must start with http:// or https://"
    if not (cfg["models"].get(p) or "").strip():
        return "Fill in the model name."
    if p != "ollama":
        if not cfg["api_key"]:
            return "Paste your API key."
        local = parts.hostname in ("localhost", "127.0.0.1", "::1")
        if parts.scheme != "https" and not local:
            return "With an API key the address has to be https:// (the key would travel unprotected)."
    return None


def enabled(tool=None, cfg=None):
    """True when the AI may be offered: master switch on, the provider filled
    in, and (if a tool is named) that tool ticked."""
    cfg = cfg or load()
    if not cfg["enabled"] or problem(cfg):
        return False
    return True if tool is None else bool(cfg["tools"].get(tool))


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _http(url, body=None, headers=None, timeout=60):
    """GET (body None) or POST JSON; returns the parsed JSON answer."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdr = {"Content-Type": "application/json", "User-Agent": "Srboli"}
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdr,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=_context()) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        if e.code in (401, 403):
            raise AIError("The service refused the key (HTTP %d). Check the API key." % e.code)
        if e.code == 404:
            raise AIError("Not found (HTTP 404). Check the address and the model name. " + detail)
        if e.code == 429:
            raise AIError("Too many requests or no credit left (HTTP 429).")
        raise AIError(f"The service answered HTTP {e.code}. {detail}".strip())
    except urllib.error.URLError as e:
        raise AIError(f"Couldn't reach {urlparse(url).netloc}: {e.reason}")
    except (TimeoutError, OSError) as e:
        raise AIError(f"No answer in time ({e.__class__.__name__}). A big model "
                      f"can be slow: try a smaller one.")
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        raise AIError("The service sent something that isn't JSON. "
                      "Is the address right?")


def _join(base, tail):
    return base.rstrip("/") + "/" + tail.lstrip("/")


def chat(system, user, cfg=None, timeout=None, max_tokens=2048):
    """Ask the configured model; returns its text. Raises AIError."""
    cfg = cfg or load()
    why = problem(cfg)
    if why:
        raise AIError(why)
    p = cfg["provider"]
    url, model = cfg["urls"][p].strip(), cfg["models"][p].strip()
    timeout = timeout or cfg["timeout"]
    if len(user) > MAX_TEXT:
        raise AIError(f"That is too much text for one request "
                      f"({len(user)} characters, the limit is {MAX_TEXT}). "
                      f"Select a smaller part.")
    if p == "ollama":
        out = _http(_join(url, "/api/chat"), {
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "options": {"temperature": 0.2}}, timeout=timeout)
        text = (out.get("message") or {}).get("content")
    elif p == "openai":
        out = _http(_join(url, "/chat/completions"), {
            "model": model, "max_tokens": max_tokens, "temperature": 0.2,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]},
            {"Authorization": "Bearer " + cfg["api_key"]}, timeout)
        try:
            text = out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            text = None
    else:
        out = _http(_join(url, "/v1/messages"), {
            "model": model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}]},
            {"x-api-key": cfg["api_key"],
             "anthropic-version": "2023-06-01"}, timeout)
        try:
            text = "".join(b.get("text", "") for b in out["content"]
                           if b.get("type") == "text")
        except (KeyError, TypeError, AttributeError):
            text = None
    if not isinstance(text, str) or not text.strip():
        raise AIError("The model sent an empty answer.")
    return text.strip()


def test_connection(cfg=None):
    """(ok, message) - for the Settings 'Test' button."""
    cfg = cfg or load()
    why = problem(cfg)
    if why:
        return False, why
    try:
        if cfg["provider"] == "ollama":
            out = _http(_join(cfg["urls"]["ollama"], "/api/tags"),
                        timeout=min(cfg["timeout"], 15))
            names = [m.get("name", "") for m in out.get("models", [])]
            want = cfg["models"]["ollama"].strip()
            if not any(n == want or n.split(":")[0] == want for n in names):
                have = ", ".join(names[:6]) or "none installed"
                return False, (f"Ollama is running, but has no model '{want}'. "
                               f"Installed: {have}. (Get one with: ollama pull {want})")
            return True, f"Ollama is running and has '{want}'."
        reply = chat("Reply with the single word OK.", "Say OK.", cfg,
                     timeout=min(cfg["timeout"], 30), max_tokens=16)
        return True, "Connected. The model answered: " + reply[:40]
    except AIError as e:
        return False, str(e)


# ── helpers for the features ─────────────────────────────────────────────────
def extract_json(text):
    """The first JSON object in a model's answer (models like to wrap it in a
    code fence or add a sentence around it). None if there isn't one."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except ValueError:
                        pass
                    break
        start = text.find("{", start + 1)
    return None


TEXT_MODES = {
    "fix": ("Fix spelling and grammar. Change as little as possible. Keep the "
            "meaning, the tone, the language and every line break."),
    "shorter": "Make the text shorter while keeping every important point.",
    "rewrite": "Rewrite the text so it reads clearly and naturally. Keep the meaning and the language.",
}


def edit_text(mode, text, instruction="", cfg=None):
    """Return the text changed as asked (the caller shows it before using it)."""
    if not text.strip():
        raise AIError("There is no text to work on.")
    task = TEXT_MODES.get(mode) or instruction.strip()
    if not task:
        raise AIError("Say what to do with the text.")
    if mode == "custom" and instruction.strip():
        task = instruction.strip()
    system = ("You edit text for the user. " + task + " Reply with ONLY the "
              "resulting text: no introduction, no explanation, no quotes "
              "around it, no code fence. Keep any Markdown or HTML markup as it is.")
    out = chat(system, text, cfg)
    out = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", out.strip())
    return out


# ── Ollama set-up help (nothing is installed for you: you get the steps) ────
# (minimum RAM in GB, model, what to expect)
MODEL_TIERS = [
    (0, "llama3.2:1b", "tiny and fast, fine for fixing text, weak at rules and courses"),
    (6, "llama3.2:3b", "small; good for fixing text, OK for rules"),
    (12, "qwen2.5:7b", "good all-rounder; rules and short courses work well"),
    (24, "qwen2.5:14b", "strong; needs a good PC, slower without a GPU"),
]


def suggest_model(ram_gb):
    """The biggest tier the machine can comfortably hold (a model wants
    roughly its file size in free RAM, and the rest of the system needs some)."""
    best = MODEL_TIERS[0]
    for tier in MODEL_TIERS:
        if ram_gb >= tier[0]:
            best = tier
    return best[1], best[2]


def install_steps(os_name, model):
    """[(text, command or None)] for putting Ollama on this computer."""
    if os_name.startswith("win"):
        first = ("Download and run the installer from https://ollama.com/download", None)
    elif os_name == "darwin":
        first = ("Install Ollama (or download it from https://ollama.com/download):",
                 "brew install ollama")
    else:
        first = ("Install Ollama (this runs the official install script):",
                 "curl -fsSL https://ollama.com/install.sh | sh")
    return [first,
            ("Download the model (a few GB, once):", f"ollama pull {model}"),
            ("Back here: fill in the address and model, then press Test connection.", None)]


def ollama_state(url=None):
    """(binary_found, server_answers, [installed model names])."""
    import shutil
    url = url or DEFAULT_URLS["ollama"]
    found = shutil.which("ollama") is not None
    try:
        out = _http(_join(url, "/api/tags"), timeout=3)
        return found, True, [m.get("name", "") for m in out.get("models", [])]
    except AIError:
        return found, False, []
