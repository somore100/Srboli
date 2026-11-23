# core/music_prefs.py - the music volume shared by the Music Player and the
# mini player (0..1, remembered between runs). Pure Python.
import os

import app_data
from core.jsonio import read_json, write_json_atomic

DEFAULT_VOLUME = 0.8


def _path():
    return os.path.join(app_data.subdir("config"), "music_prefs.json")


def load_volume():
    try:
        v = float(read_json(_path(), {}).get("volume", DEFAULT_VOLUME))
    except Exception:
        v = DEFAULT_VOLUME
    return max(0.0, min(1.0, v))


def save_volume(v):
    try:
        write_json_atomic(_path(), {"volume": round(max(0.0, min(1.0, float(v))), 3)})
    except Exception:
        pass
