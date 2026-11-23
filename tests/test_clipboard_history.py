# tests/test_clipboard_history.py - xvfb-run -a python3 tests/test_clipboard_history.py  (kivy screens.)
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.clipboard_history_core import History, preview

h = History(max_items=3)
assert h.add("a") and h.add("b") and not h.add("b") and not h.add("  ") and not h.add(None)
assert [i["text"] for i in h.items] == ["b", "a"]
h.add("a")                                   # duplicate moves to top
assert [i["text"] for i in h.items] == ["a", "b"]
h.toggle_pin(1)                              # pin "b"
h.add("c"); h.add("d"); h.add("e")           # over the limit: pinned b survives
texts = [i["text"] for i in h.items]
assert "b" in texts and len(texts) == 3, texts
assert h.pinned_first()[0][1]["text"] == "b"
assert [it["text"] for _, it in h.search("E")] == ["e"]
h.clear(keep_pinned=True)
assert [i["text"] for i in h.items] == ["b"]
h.clear(keep_pinned=False)
assert h.items == []
assert preview("x\n  y" * 40).endswith("...") and "\n" not in preview("a\nb")

import tempfile, app_data
from screens.clipboard_history_screen import ClipboardHistoryScreen
sc = ClipboardHistoryScreen()
sc.hist.add("hello")
sc.refresh()
assert len(sc.grid.children) == 1
sc.pin(0)
assert sc.hist.items[0]["pinned"]
sc.remove(0)
assert sc.hist.items == []
print("clipboard history OK")
