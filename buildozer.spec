[app]

title = Srboli
package.name = srboli
package.domain = org.somore100

source.dir = .
source.include_exts = py,png,jpg,jpeg,json,ttf,txt

source.exclude_dirs = tests,.git,.github,__pycache__,srboli_data/gallery_cache,srboli_data/metadata_cache
source.exclude_patterns = *.pyc,*.spec,*.egg-info,build.txt,license.txt,README.md,SrboliLight.spec,requirements-desktop.txt,requirements.txt

version = 2.4

# Core dependencies. Don't pin python3's own version here — p4a.branch
# below is what actually controls which CPython gets built.
# psutil deliberately excluded: it has a compiled C extension, there's no
# p4a recipe for it, and PyPI doesn't publish Android-tagged wheels for it
# either, so pip has nowhere to get it from during the cross-build. It only
# backs System Stats and the desktop overlay app — both gracefully show
# "not available" via main.py's try_import()+Placeholder instead of
# crashing the build or the app.
requirements = python3,kivy==2.3.1,pillow

orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/logo.png

# Android specifics
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

android.api = 34
android.minapi = 24
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

# p4a.python_version is NOT a real buildozer.spec key (buildozer silently
# ignores unknown keys). The actual lever is which p4a branch/tag gets
# cloned.
#
# History of getting this pin right:
#   - unset / master -> currently mid-migration to building CPython 3.14 as
#     host/target Python, which breaks on packages like charset_normalizer
#     that don't yet have wheels for that Android platform tag.
#   - stable -> the opposite problem: it predates p4a's AAB (Android App
#     Bundle) support entirely (added Aug 2021), so this buildozer version
#     refuses to use it ("requires a python-for-android version with AAB
#     support").
# 2026.5.9 is p4a's actual latest tagged PyPI release (10 May 2026) — long
# after AAB support existed, and from before the still-unreleased CPython
# 3.14 migration currently sitting on master. Pinning to the tag by name
# gives a fixed, reproducible checkout instead of riding either branch.
p4a.branch = 2026.5.9

[buildozer]
log_level = 2
warn_on_root = 1