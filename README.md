# Srboli

Pocket swiss-army-knife desktop app — **29 tools in one window**, built with
Python + Kivy. Even if you don't see a use for every feature at first, odds
are at least one will be useful — and you might even end up using several.

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-lightgrey)

<p align="center">
  <img width="49%" alt="Srboli main screen" src="https://github.com/user-attachments/assets/943e84d4-d894-47bc-b1f9-ec6149f3d7bf" />
  <img width="49%" alt="Srboli tool screen" src="https://github.com/user-attachments/assets/22bde96b-28af-4b57-97bf-23872f33dfc3" />
</p>

From countdown timer to metadata inspector, Srboli bundles small utilities
you'd otherwise hunt down as separate apps into one lightweight desktop
tool, with global shortcuts to jump between them.

## Features

| Screen | What it does |
|---|---|
| **Dashboard** | Quick-access hub: search box, a Recent row, and collapsible sections (Writing, Files, Media, Math and data, System, Fun) |
| **Loading / Timer** | Countdown timer with shutdown / suspend / notify actions |
| **Text Editor** | Plain-text editor with Raw ⇄ Styled Markdown view, colour wheel, autosave; exports .txt / .html / .md / checked-and-indented .json |
| **Script / Teleprompter** | Paste full text, auto-copy chunks one at a time; auto-advance on paste |
| **Full Editor** | Outline document (nested sections with Markdown bodies, colour swatches + wheel) + slides generated from the outline (per-slide colours / image / skip, full-screen presenter) + coloured tables (per-cell fill/text colours, add/remove rows and columns, SUM/AVG/formulas) that can be placed inside sections; exports everything to HTML |
| **Basic Tools** | Clock, stopwatch, alarm, real calculator |
| **System Stats** | CPU / RAM / Disk / GPU + live FPS & ping graphs, plus an always-on-top overlay window |
| **Gallery Sorter** | Sort images and videos into folders, in-app video player |
| **Music Player** | Playlist manager with pygame playback, tap-or-drag seek bar and volume control |
| **Randomizer Tools** | Number / password / dice / list / coin picker |
| **Image to Text** | Any file ⇄ Base64 (background-threaded for large files) |
| **Morse Converter** | Text ⇄ Morse code, with a tap-to-type keypad |
| **Binary / Hex Converter** | Text ⇄ Binary / Hex / Decimal |
| **Function Plotter** | y=f(x), parametric, polar; pencil-to-spline; fill + integral; PNG export |
| **Backrooms** | JSON-driven Backrooms level guide |
| **Wheel of Names** | Weighted spinner with numbers mode |
| **Unhelpful Calc** | A calculator that never gives you the right answer |
| **Shape Generator** | Procedural logo / pattern generator (PNG + SVG export) |
| **Metadata Inspector** | EXIF / video metadata viewer + AI-image indicator |
| **File Sorter** | Rule-based file organizer (extension / name / size / date / image metadata → move / copy / rename / delete). Leaves files alone that are still being written, empty, open in another program or locked by an editor; moves are verified before the original is deleted |
| **Reminders** | To-do + timed reminders, daily/weekly repeats, desktop notifications via the background service |
| **Fast File Transfer** | Parallel copy / move for folders of many smaller files, with a real Auto-tune that measures the best worker count on your disk; same "is it finished?" protection and verified moves |
| **Quick Switcher** | Global keyboard shortcuts — jump to a screen, launch an app/script, open the file picker, or run a terminal command |
| **Minesweeper** | Classic Minesweeper: 3 difficulties, long-press to flag, tap a number to chord, timer and best times |
| **Chess** | Full-rules chess (castling, en passant, promotion, check/mate/stalemate) vs. a built-in AI at 3 levels or two-player pass-and-play, with undo |
| **Learn** | Import an AI-written course (JSON) and study it Duolingo-style |
| **Cover / Privacy Boxes** | Desktop-only privacy boxes, blackout and hide-from-recording with global hotkeys |
| **Linux Shortcut Creator** | Fill in a form to make a `.desktop` launcher for the application menu (and Desktop); lists, edits and deletes the ones it made |
| **Touch Test** | Shows what each tap looks like to the app (finger vs. mouse duplicates) and has the duplicate-tap filter switch |
| **File Converter** | Batch-convert images (png/jpg/webp/bmp/gif/tiff/ico/pdf), documents (txt/md/html/docx/pdf/csv/tsv/json) and - on desktop with ffmpeg - audio/video |
| **Settings** | Reorder (within a section) / hide dashboard screens, toggle lazy-loading, manage the background service and autostart |
| **Data Directory** | First-launch + settings screen for choosing where Srboli stores its data |

## Requirements

- Python 3.10+
- Linux (Pop!OS / Ubuntu) or Windows

Optional, per feature — install only what you need:

- `Pillow` — image thumbnails, EXIF read/write, image previews
- `opencv-python` — video thumbnails, frame strips, video metadata
- `pygame` — Music Player playback
- `ffpyplayer` — in-app video playback (Gallery Sorter)
- `psutil` — System Stats (Linux/Windows; Android uses a bundled fallback)
- `GPUtil` or `nvidia-smi` — GPU stats
- `ping3` — ping without shelling out to the system `ping`
- `send2trash` — File Sorter's delete action uses the recycle bin when available

## Setup

Clone:

```bash
git clone https://github.com/somore100/Srboli.git
cd Srboli

Create virtual environment:
bash

python3 -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

Install dependencies:
bash

pip install -r requirements-desktop.txt

Run:
bash

python3 main.py

Building an executable

Uses PyInstaller via the included srboli.spec.

Linux:
bash

pip install pyinstaller
pyinstaller srboli.spec
# Output: dist/Srboli

Windows:
bat

pip install pyinstaller
pyinstaller srboli.spec
REM Output: dist\Srboli.exe

Project structure
text

srboli/
├── main.py                  # App entry point (also dispatches `--overlay`)
├── app_data.py              # Data-directory manager
├── requirements.txt
├── srboli.spec              # PyInstaller spec
├── LICENSE
├── core/
│   ├── android_storage.py       # Shared-storage root helper (Android vs desktop)
│   ├── daemon_ipc.py            # IPC with the background service
│   ├── autostart.py             # "Start service at login" toggles
│   ├── file_sorter_core.py      # Rule engine (Kivy-free, shared with the daemon)
│   ├── file_sorter_watch.py     # Folder watcher for the background service
│   ├── reminders_core.py        # Reminder scheduling logic (shared with the daemon)
│   ├── psutil_lite.py           # /proc-based psutil fallback for Android
│   ├── version.py               # The one place the app version lives
│   ├── advlog.py                # Optional advanced logging (Settings)
│   ├── bootlog.py               # Boot breadcrumbs: where did the app get stuck?
│   ├── chess_core.py            # Chess rules + AI (Kivy-free)
│   ├── learn_core.py            # Course engine for the Learn screen
│   ├── seekbar.py               # Thick tap/drag progress bar (Music Player)
│   ├── dashboard_core.py        # Dashboard sections / search / recents (Kivy-free)
│   ├── file_safety.py           # "Safe to touch yet?" check + verified copy/move (Kivy-free)
│   ├── transfer_core.py         # Fast Transfer engine + auto-tune (Kivy-free)
│   ├── desktop_entry.py         # .desktop launcher builder / installer (Kivy-free)
│   ├── slides_core.py           # Slides derived from the Full Editor outline (Kivy-free)
│   ├── table_core.py            # Full Editor coloured tables + formulas (Kivy-free)
│   ├── outline_core.py          # Full Editor outline tree + Markdown/HTML output (Kivy-free)
│   ├── cover_core.py / cover_app.py  # Cover boxes (separate tkinter process)
│   ├── converter_core.py        # File Converter engine
│   ├── touch_dedupe.py / tap_guard.py  # Ghost-tap filters
│   ├── notify.py                # Desktop notifications for reminders
│   ├── pathbar.py               # Path bar for every file chooser
│   └── tickbox.py               # Large labelled on/off toggle
└── screens/
    ├── __init__.py
    ├── registry.py              # Single source of truth for the screen list
    ├── data_dir_screen.py       # First-launch + data-directory chooser
    ├── settings_screen.py
    ├── _overlay_app.py          # Always-on-top stats overlay (separate process)
    ├── sys_info.py              # Shared GPU / ping helpers
    ├── md_parse.py              # Kivy-free Markdown parser
    ├── md_editor.py             # Markdown text box with formatting bar (Full Editor)
    ├── md_view.py               # Styled (rendered) Markdown view
    ├── loading_timer_screen.py
    ├── text_editor_screen.py
    ├── script_mode_screen.py
    ├── full_editor_screen.py
    ├── basic_tools_screen.py
    ├── system_stats_screen.py
    ├── gallery_sorter_screen.py
    ├── music_screen.py
    ├── randomizer.py
    ├── image_text_screen.py
    ├── morse_screen.py
    ├── binary_screen.py
    ├── function_plotter_screen.py
    ├── backrooms_screen.py
    ├── spin_screen.py
    ├── unhelpful_calc_screen.py
    ├── shape_generator_screen.py
    ├── metadata_screen.py
    ├── file_sorter_screen.py
    ├── reminders_screen.py
    ├── fast_transfer_screen.py
    ├── quickswitcher_screen.py
    ├── minesweeper_screen.py
    ├── chess_screen.py
    ├── learn_screen.py
    ├── shortcut_screen.py
    ├── dialogs.py               # Shared confirm / message popups
    ├── cover_screen.py
    ├── touch_test_screen.py
    └── file_converter_screen.py

## Building for Android

Uses [Buildozer](https://github.com/kivy/buildozer) via the included
`buildozer.spec` (package `org.somore100.srboli`, API 34, min API 24,
`arm64-v8a` + `armeabi-v7a`).

```bash
pip install buildozer
buildozer android debug
# Output: bin/srboli-<version>-*-debug.apk
```

On Android the app uses `core/psutil_lite.py` instead of `psutil`, and
desktop-only tools (such as Cover) are unavailable. The app version lives in
`core/version.py` and **must match** `version =` in `buildozer.spec`: Android
derives its versionCode from it, and a higher versionCode is what lets a new
APK install over the old one. Bump both on every build.

Pushing a `v*` tag also builds the Windows EXE, Linux AppImage and Android APK
in GitHub Actions (`.github/workflows/build-srboli.yml`).

## Advanced logging

For diagnosing input problems (ghost taps, frozen clicks) and UI stalls.
Off by default; turn it on in **Settings > Advanced logging**. It applies
immediately, no restart needed.

It writes `Srboli_advanced.log` into the `logs` folder of your data
directory (the previous run is kept as `Srboli_advanced.prev.log`; the file is
capped at about 1.5 MB). Each line is timestamped and tagged:

| Tag | What it records |
|---|---|
| `env` | Platform, Kivy version, input providers and `[input]` config at start |
| `touch` | Every down/up: device, button, position, widgets under it, other active touches |
| `key` | Key presses (typed letters are not recorded, only Ctrl/Alt shortcuts) |
| `screen` | Every screen change |
| `build` | How long each screen took to build |
| `stall` | The main loop was blocked for more than 0.35 s |

A separate `Srboli_boot.log` of start-up breadcrumbs is always kept, to show
where the app got stuck if it freezes on launch.

Contributing

Issues and pull requests are welcome — new tool screens, bug fixes, or
packaging improvements (macOS build is an open gap) are all fair game.
License

This project is source-available software. You are free to view, study,
modify, fork, and share the project for non-commercial purposes. Addons,
plugins, extensions, and integrations are also permitted under the license
terms. See the LICENSE file for full terms.