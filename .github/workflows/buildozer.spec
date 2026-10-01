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
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

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
#   - unset / master -> mid-migration to CPython 3.14; broke on
#     charset_normalizer ("not a supported wheel on this platform").
#   - stable -> predates AAB support; buildozer refuses it.
#   - v2026.05.09 -> clones fine and compiles Kivy, but hits the same
#     charset_normalizer error. Root cause: commit 2f107b15 ("Add support
#     for prebuilt wheels", #3280) made run_pymodules_install do a dry-run
#     resolve WITH --platform flags, then a real install WITHOUT them, so
#     pip rejects the Android-tagged wheel. Triggered by the Kivy recipe's
#     own python_depends (certifi, chardet, idna, requests, urllib3,
#     filetype), not by anything in this project's requirements.
# v2024.01.21 is the last tag BEFORE that commit (verified with
# `git tag --contains 2f107b15` -> only v2026.05.09). It uses the older
# single-step pip install, builds CPython 3.11.5, and is well after AAB
# support. Note the git tag is v-prefixed and zero-padded.
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1