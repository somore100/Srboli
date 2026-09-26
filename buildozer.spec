[app]

title = Srboli
package.name = srboli
package.domain = org.somore100

source.dir = .
source.include_exts = py,png,jpg,jpeg,json,ttf,txt

# Keep the APK small and avoid shipping dev-only junk / desktop caches.
source.exclude_dirs = tests,.git,.github,__pycache__,srboli_data/gallery_cache,srboli_data/metadata_cache
source.exclude_patterns = *.pyc,*.spec,*.egg-info,build.txt,license.txt,README.md,SrboliLight.spec

version = 2.4

# ── requirements ─────────────────────────────────────────────────────────
# Deliberately NOT included yet: opencv-python (cv2), pygame, ffpyplayer.
# Those three are heavy/slow to cross-compile for Android (opencv can take
# 45-60+ min on a cold cache, pygame's bundled SDL2 can clash with Kivy's,
# ffpyplayer needs a full ffmpeg cross-build) and only back three screens
# (Metadata Inspector, Gallery Sorter, Music Player). Thanks to main.py's
# try_import() + Placeholder screen, the app still boots fine without them
# — those three routes just show "not available" instead of crashing.
# Add them back one at a time (`pip install python-for-android` recipe
# names: opencv, pygame, ffpyplayer) once the base APK is confirmed working.
requirements = python3,kivy==2.3.1,pillow,psutil,plyer

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/logo.png

# ── Android specifics ────────────────────────────────────────────────────
# File Sorter / Gallery Sorter / Fast Transfer all want to read+write
# arbitrary folders. Legacy external storage still works up through
# targetSdk 29-ish; on Android 11+ (API 30+) this needs the "All files
# access" special permission granted manually in Settings, or a rewrite
# onto the Storage Access Framework. Tracked as a known follow-up, not a
# build blocker.
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

android.api = 34
android.minapi = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

# Desktop-only routes (quickswitcher, background daemon start/stop via
# a Unix socket, XDG/registry autostart) will still import fine on
# Android since they're stdlib-only, they just won't do anything useful
# there yet. Left in for now; hiding them behind a platform check in
# screens/registry.py is a good follow-up once the base APK is confirmed.

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
