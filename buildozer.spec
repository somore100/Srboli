[app]

title = Srboli
package.name = srboli
package.domain = org.somore100

source.dir = .
source.include_exts = py,png,jpg,jpeg,json,ttf,txt,kv,ini

# Exclude dev files, git, caches, and desktop-only spec/requirements
source.exclude_dirs = tests,.git,.github,__pycache__,srboli_data/gallery_cache,srboli_data/metadata_cache
source.exclude_patterns = *.pyc,*.spec,*.egg-info,build.txt,license.txt,README.md,SrboliLight.spec,requirements-desktop.txt,requirements.txt

version = 2.4

# ── requirements ─────────────────────────────────────────────────────────
# Pinned charset-normalizer==3.3.2 to prevent Python 3.14 wheel mismatch errors.
# Kept opencv, pygame, ffpyplayer excluded for fast compilation.
# ── requirements ─────────────────────────────────────────────────────────
requirements = python3,kivy==2.3.1,pillow,plyer,charset-normalizer==3.3.2

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/logo.png

# ── Android specifics ────────────────────────────────────────────────────
# Updated for API 34 compatibility (includes Android 13+ granular media permissions)
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO

android.api = 34
android.minapi = 24

# Focused on 64-bit ARM to cut build time in half and avoid 32-bit slice conflicts
android.archs = arm64-v8a

android.accept_sdk_license = True
android.allow_backup = True
android.enable_androidx = True

# Pin p4a to Python 3.11 to avoid Python 3.14 wheel compilation bugs
p4a.python_version = 3.11

[buildozer]
log_level = 2
warn_on_root = 1