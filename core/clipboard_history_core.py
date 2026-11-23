# core/clipboard_history_core.py - the list behind Clipboard History. Pure Python.
#
# Newest first, no duplicates (copying the same text again moves it to the top),
# pinned entries never fall off the end. The list is kept in memory only unless
# the user turns on "Keep after closing" (a clipboard often holds passwords).
import os

import app_data
from core.jsonio import read_json, write_json_atomic

MAX_ITEMS = 100
MAX_LEN = 20000          # a huge paste is not worth keeping


class History:
    def __init__(self, max_items=MAX_ITEMS):
        self.max_items = max_items
        self.items = []            # [{"text": str, "pinned": bool}]

    def add(self, text):
        """Record a copied text. Returns True if the list changed."""
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_LEN:
            return False
        if self.items and self.items[0]["text"] == text:
            return False
        pinned = False
        for i, it in enumerate(self.items):
            if it["text"] == text:
                pinned = it["pinned"]
                del self.items[i]
                break
        self.items.insert(0, {"text": text, "pinned": pinned})
        self._trim()
        return True

    def _trim(self):
        while len(self.items) > self.max_items:
            for i in range(len(self.items) - 1, -1, -1):
                if not self.items[i]["pinned"]:
                    del self.items[i]
                    break
            else:
                break

    def toggle_pin(self, index):
        self.items[index]["pinned"] = not self.items[index]["pinned"]

    def remove(self, index):
        del self.items[index]

    def clear(self, keep_pinned=True):
        self.items = [i for i in self.items if keep_pinned and i["pinned"]]

    def search(self, query):
        """(index, item) pairs whose text contains `query` (case-insensitive)."""
        q = (query or "").lower()
        return [(i, it) for i, it in enumerate(self.items) if q in it["text"].lower()]

    def pinned_first(self):
        order = sorted(range(len(self.items)), key=lambda i: not self.items[i]["pinned"])
        return [(i, self.items[i]) for i in order]


def preview(text, n=90):
    one = " ".join(text.split())
    return one if len(one) <= n else one[:n - 1] + "..."


def _path():
    return os.path.join(app_data.subdir("config"), "clipboard_history.json")


def load_state():
    """{"keep": bool, "items": [...]}; items only present when keep is on."""
    d = read_json(_path(), {})
    return {"keep": bool(d.get("keep", False)),
            "items": [i for i in d.get("items", [])
                      if isinstance(i, dict) and isinstance(i.get("text"), str)]}


def save_state(keep, items):
    try:
        write_json_atomic(_path(), {"keep": bool(keep), "items": items if keep else []})
    except Exception:
        pass
