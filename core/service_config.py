# core/service_config.py - which features may run inside the background
# service. Kivy-free (the daemon imports it).
#
# The service itself is OFF by default and only runs when started in
# Settings. This file only decides what a RUNNING service is allowed to do;
# each flag is re-read on every scheduler tick, so changing one takes
# effect within seconds (the UI also sends "reload" to apply it at once).

import os
import json

import app_data

# key -> (title shown in Settings, one-line explanation)
FEATURES = {
    "reminders": ("Reminders",
                  "Fire reminder notifications while Srboli is closed."),
    "folder_watch": ("File Sorter folder watcher",
                     "Apply your saved File Sorter rules to the watched "
                     "folder automatically."),
    "cover": ("Cover / Privacy Boxes",
              "Keep the privacy boxes and hotkeys running (also needs "
              "'run with the service' ticked inside Cover)."),
}


def _path():
    return os.path.join(app_data.subdir("daemon"), "service.json")


def load():
    """{feature: bool}. Missing/corrupt file -> everything allowed (the
    service is something you started on purpose)."""
    allow = {k: True for k in FEATURES}
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f).get("allow", {})
        for k in FEATURES:
            if k in data:
                allow[k] = bool(data[k])
    except Exception:
        pass
    return allow


def save(allow):
    clean = {k: bool(allow.get(k, True)) for k in FEATURES}
    try:
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"allow": clean}, f, indent=2)
        os.replace(tmp, _path())
        return True
    except OSError as e:
        print(f"service_config: save failed: {e}")
        return False


def is_allowed(feature):
    return load().get(feature, True)
