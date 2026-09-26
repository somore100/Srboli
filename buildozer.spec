[app]

title = Srboli
package.name = srboli
package.domain = org.somore100

source.dir = .
source.include_exts = py,png,jpg,jpeg,json,ttf,txt,kv,ini

source.exclude_dirs = tests,.git,.github,__pycache__,srboli_data/gallery_cache,srboli_data/metadata_cache
source.exclude_patterns = *.pyc,*.spec,*.egg-info,build.txt,license.txt,README.md,SrboliLight.spec,requirements-desktop.txt,requirements.txt

version = 2.4

# ── requirements ─────────────────────────────────────────────────────────
# Kept minimal for Android base build. Excludes heavy/complex C-extensions
# (opencv, pygame, ffpyplayer) for fast compilation.
# ── requirements ─────────────────────────────────────────────────────────
requirements = python3,kivy==2.3.1,pillow,plyer

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/logo.png

# Android specifics
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO

android.api = 34
android.minapi = 24
android.archs = arm64-v8a

android.accept_sdk_license = True
android.allow_backup = True
android.enable_androidx = True

# Target Python 3.11 for Android
p4a.python_version = 3.11

# Force pip to build charset-normalizer from source (sdist) instead of grabbing a cp314 wheel
p4a.extra_args = --no-binary charset-normalizer

[buildozer]
log_level = 2
warn_on_root = 1