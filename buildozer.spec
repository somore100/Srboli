[app]

title = Srboli
package.name = srboli
package.domain = org.somore100

source.dir = .
source.include_exts = py,png,jpg,jpeg,json,ttf,txt

source.exclude_dirs = tests,.git,.github,__pycache__,srboli_data/gallery_cache,srboli_data/metadata_cache
source.exclude_patterns = *.pyc,*.spec,*.egg-info,build.txt,license.txt,README.md,SrboliLight.spec,requirements-desktop.txt,requirements.txt

version = 2.4

# Core dependencies (keep 'python3' as the recipe name)
requirements = python3,kivy==2.3.1,pillow,psutil

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

# Target stable Python 3.11 runtime inside the APK
p4a.python_version = 3.11

[buildozer]
log_level = 2
warn_on_root = 1