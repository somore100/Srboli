# core/android_storage.py
# Shared helper for storage access on Android. Kivy-free-ish: only touches
# android/jnius when actually running on Android, so it's safe to import
# from the daemon or from desktop builds too.
#
# WHY THIS EXISTS
# ----------------
# `os.path.expanduser("~")`, which every FileChooser in this app used to
# start from, resolves on Android to the app's *private* sandbox dir
# (something like /data/user/0/org.somore100.srboli/files). That directory
# is readable/writable with zero permissions, which is exactly why the
# pickers "worked" but showed nothing useful, and why any code that then
# tried to read/write a *real* user file (a photo, a download, anything
# outside that sandbox) raised PermissionError and crashed — Android's
# scoped storage silently has no access there, permission list in
# buildozer.spec or not.
#
# `READ_EXTERNAL_STORAGE` / `WRITE_EXTERNAL_STORAGE` are also close to
# inert on Android 11+ (API 30+): they no longer grant broad filesystem
# access. The permission that actually does what this app needs (browse
# and edit arbitrary files across the device, like a file manager) is
# MANAGE_EXTERNAL_STORAGE, which can't be granted via the normal runtime
# popup — it requires sending the user to a dedicated system settings
# screen once.

import os

try:
    from kivy.utils import platform as _kivy_platform
    ON_ANDROID = (_kivy_platform == "android")
except Exception:
    ON_ANDROID = False


def shared_storage_root():
    """Best starting path for a FileChooser: real shared storage on
    Android, the user's home dir everywhere else."""
    if ON_ANDROID:
        for candidate in ("/storage/emulated/0", "/sdcard"):
            if os.path.isdir(candidate):
                return candidate
    return os.path.expanduser("~")


def has_full_storage_access():
    if not ON_ANDROID:
        return True
    try:
        from jnius import autoclass
        Environment = autoclass("android.os.Environment")
        return bool(Environment.isExternalStorageManager())
    except Exception:
        return False


def request_full_storage_access():
    """Send the user to the 'Allow access to manage all files' system
    settings screen for this app. Does nothing off-Android or if already
    granted. Must be called from the UI/main thread (fine to call from
    App.build() or an on_release handler)."""
    if not ON_ANDROID or has_full_storage_access():
        return
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        intent = Intent(
            Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
            Uri.parse(f"package:{activity.getPackageName()}"),
        )
        activity.startActivity(intent)
    except Exception as exc:
        print(f"!! request_full_storage_access failed: {exc}")


def request_basic_permissions():
    """Ask for the ordinary runtime permissions too (harmless, and still
    needed on Android 10 and below, or as a fallback). Safe no-op
    elsewhere."""
    if not ON_ANDROID:
        return
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
        ])
    except Exception as exc:
        print(f"!! request_basic_permissions failed: {exc}")
