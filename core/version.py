# core/version.py - the ONE place the app version lives.
# Bump it every build: it is shown on the dashboard footer and must match
# `version =` in buildozer.spec (Android derives its versionCode from that,
# and a higher versionCode is what lets a new APK install over the old one).
VERSION = "3.3"
