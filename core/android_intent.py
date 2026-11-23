# core/android_intent.py - receive "Open with Srboli" / "Share to Srboli" on
# Android. Everything touching jnius lives here and is guarded: off Android (or
# on any error) install() does nothing and the app is unaffected.
#
# The other app gives us a content:// address, not a file, so the content is
# copied into the app's cache folder and the tool gets that local copy
# (the original is never modified). Cache copies are cleared by "Clear cache".

import os

from core import open_with_core as core

_MAX_COPY = 200 * 1024 * 1024        # don't copy more than 200 MB


def _display_name(resolver, uri):
    try:
        cur = resolver.query(uri, None, None, None, None)
        if cur is not None:
            try:
                idx = cur.getColumnIndex("_display_name")
                if idx >= 0 and cur.moveToFirst():
                    return cur.getString(idx)
            finally:
                cur.close()
    except Exception:
        pass
    return None


def _copy_uri(activity, uri, mime):
    import app_data
    resolver = activity.getContentResolver()
    name = _display_name(resolver, uri) or (uri.getLastPathSegment() or "shared_file")
    folder = app_data.subdir(os.path.join("cache", "open_with"))
    dest = core.unique_path(folder, name)
    stream = resolver.openInputStream(uri)
    total = 0
    try:
        with open(dest, "wb") as out:
            buf = bytearray(65536)
            while True:
                n = stream.read(buf)
                if n <= 0:
                    break
                total += n
                if total > _MAX_COPY:
                    raise OSError("That file is too big to open this way.")
                out.write(bytes(buf[:n]))
    finally:
        stream.close()
    return {"kind": "file", "path": dest, "name": os.path.basename(dest), "mime": mime or ""}


def read_intent(intent, activity):
    """The item an Android Intent carries, or None."""
    if intent is None:
        return None
    action = intent.getAction()
    mime = intent.getType() or ""
    if action == "android.intent.action.VIEW":
        uri = intent.getData()
        if uri is None:
            return None
        if uri.getScheme() == "file":
            path = uri.getPath()
            return {"kind": "file", "path": path, "name": os.path.basename(path), "mime": mime}
        item = _copy_uri(activity, uri, mime)
        try:   # set by the overlay player's "Open in Srboli"
            item["from_overlay"] = bool(intent.getBooleanExtra("srboli_from_overlay", False))
        except Exception:
            pass
        return item
    if action == "android.intent.action.SEND":
        stream = intent.getParcelableExtra("android.intent.extra.STREAM")
        if stream is not None:
            return _copy_uri(activity, stream, mime)
        text = intent.getStringExtra("android.intent.extra.TEXT")
        if text:
            return {"kind": "text", "text": text}
    return None


def install(callback, on_error=None):
    """Call callback(item) for the intent that started the app and for every
    later one. Returns True if hooked up (Android only)."""
    if "ANDROID_ARGUMENT" not in os.environ:
        return False
    try:
        from android import activity as android_activity
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        act = PythonActivity.mActivity

        def handle(intent):
            try:
                item = read_intent(intent, act)
            except Exception as e:
                if on_error:
                    on_error(str(e))
                return
            if item:
                callback(item)

        android_activity.bind(on_new_intent=handle)
        handle(act.getIntent())
        return True
    except Exception as e:
        if on_error:
            on_error(str(e))
        return False
