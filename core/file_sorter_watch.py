# core/file_sorter_watch.py - background folder watcher for File Sorter.
#
# Kivy-free (the daemon never imports Kivy). Reads a small config file the
# File Sorter screen writes, and every poll applies the saved rules to the
# watched folder using the same engine as the UI (core.file_sorter_core).
#
# Safety rules (nobody is at the screen to confirm anything):
#   * delete rules only run if the rule has "Auto-delete" ticked; otherwise
#     the delete is skipped.
#   * files are only acted on once their size has stopped changing.
#   * a file already handled (unchanged since) is not handled again, so a
#     "copy" rule can't copy the same file every poll.
#   * files already inside a rule's destination folder are ignored, so a
#     "move into a subfolder of the watched folder" rule can't loop.
import os
import json
import time
import datetime

import app_data
import core.file_sorter_core as fsc

CONFIG_NAME = "_watch_config.json"
STATE_NAME = "_watch_state.json"
LOG_NAME = "_watch.log"
POLL_SECONDS = 20
MAX_STATE = 5000
MAX_LOG_BYTES = 200_000


def _p(name):
    return os.path.join(fsc._rulesets_dir(), name)


def load_config():
    try:
        with open(_p(CONFIG_NAME), encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    return {"enabled": bool(cfg.get("enabled", False)),
            "source_folder": cfg.get("source_folder", ""),
            "recursive": bool(cfg.get("recursive", True)),
            "ruleset": cfg.get("ruleset", fsc.LAST_USED_KEY)}


def save_config(cfg):
    try:
        with open(_p(CONFIG_NAME), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"FileSorter watch: save config failed: {e}")
        return False


def _load_state():
    try:
        with open(_p(STATE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    if len(state) > MAX_STATE:
        for k in list(state)[:len(state) - MAX_STATE]:
            state.pop(k, None)
    try:
        with open(_p(STATE_NAME), "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def _log_line(msg):
    path = _p(LOG_NAME)
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_BYTES:
            os.replace(path, path + ".old")
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{stamp}  {msg}\n")
    except Exception:
        pass


def _sig(path):
    st = os.stat(path)
    return [int(st.st_mtime), st.st_size]


def _dest_dirs(rules):
    out = []
    for r in rules:
        a = r.get("action", {})
        if a.get("type") in ("move", "copy") and a.get("dest"):
            out.append(os.path.normpath(a["dest"]))
    return out


def _inside(path, dirs):
    p = os.path.normpath(path)
    return any(p == d or p.startswith(d + os.sep) for d in dirs)


def _collect(folder, recursive):
    files = []
    if recursive:
        for root_dir, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            files += [os.path.join(root_dir, n) for n in names
                      if not n.startswith(".")]
    else:
        for n in os.listdir(folder):
            p = os.path.join(folder, n)
            if os.path.isfile(p) and not n.startswith("."):
                files.append(p)
    return files


def scan_once(cfg=None, stop_check=None):
    """One pass. Returns the number of files acted on."""
    cfg = cfg or load_config()
    folder = cfg["source_folder"]
    if not cfg["enabled"] or not folder or not os.path.isdir(folder):
        return 0
    rules = fsc.load_ruleset(cfg["ruleset"])
    if not rules:
        return 0

    state = _load_state()
    skip_dirs = _dest_dirs(rules)
    candidates = []
    for p in _collect(folder, cfg["recursive"]):
        if _inside(p, skip_dirs):
            continue
        try:
            if state.get(p) == _sig(p):
                continue
        except OSError:
            continue
        candidates.append(p)
    if not candidates:
        return 0

    fsc.clear_meta_cache()
    plan = fsc.build_plan(candidates, rules)
    acted = 0
    counter = 1
    for path, matched in plan:
        if stop_check and stop_check():
            break
        _log_line(path)
        current, exists = path, True
        for rule in matched:
            if not exists:
                break
            if not fsc.wait_for_stable_file(current, log=_log_line,
                                            stop_check=stop_check):
                exists = False
                break
            current, exists = fsc.apply_action(
                current, rule["action"], counter, _log_line,
                confirm_delete=lambda p: False)   # no one to ask
        counter += 1
        acted += 1
        if exists:
            try:
                state[current] = _sig(current)
            except OSError:
                pass
        # the original path is "done" too (e.g. after a copy or a skipped
        # delete it still exists in place)
        if os.path.exists(path):
            try:
                state[path] = _sig(path)
            except OSError:
                pass
    _save_state(state)
    return acted
