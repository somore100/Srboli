# Srboli

Pocket swiss-army-knife desktop app — **47 tools in one window**, built with
Python + Kivy. Even if you don't see a use for every feature at first, odds
are at least one will be useful — and you might even end up using several.

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS%20%7C%20Android-lightgrey)

<img width="1920" height="1008" alt="Screenshot From 2026-11-23 15-24-34" src="https://github.com/user-attachments/assets/dcc789af-2a73-4c54-bddf-74f7aef60e0a" />

From countdown timer to metadata inspector, Srboli bundles small utilities
you'd otherwise hunt down as separate apps into one lightweight desktop
tool, with global shortcuts to jump between them.

## Features

| Screen | What it does |
|---|---|
| **Loading and screen changes** | Settings: screen change (fade or instant) and what shows while a tool builds (plain text by default, the logo, or stay on the current screen) |
| **Manage tools** | Settings -> "Remove or restore tools permanently...": a removed tool disappears from the Dashboard, search and shortcuts and is not loaded at start-up (hiding in Settings only drops it from the list). Always restorable |
| **Themes** | Settings -> Theme: Dark (default), Blue or Yellow & white, plus a Rounded buttons switch; applied at the next start |
| **Mini player** | Opening a sound from another app ("Open with Srboli") shows a small player at the bottom: seek bar, play/pause, loop, volume (shared with the Music Player), an optional "play the next track" when the folder has more sounds, a minimise arrow, and "Open in Srboli" for the full tools |
| **Dashboard** | Quick-access tile hub: search (with aliases, Enter opens the first hit), pinned and Recent rows (long-press or right-click to pin), and collapsible sections (Writing, Files, Media, Math and data, System, Fun) |
| **Loading / Timer** | Countdown timer with shutdown / suspend / notify actions. For "shut down when the upload is done" use Power Off When Done |
| **Text Editor** | Plain-text editor with Raw ⇄ Styled Markdown view, colour wheel, autosave; exports .txt / .html / .md / checked-and-indented .json |
| **Script / Teleprompter** | Paste full text, auto-copy chunks one at a time; auto-advance on paste |
| **Full Editor** | Outline document (nested sections with Markdown bodies, colour swatches + wheel) + slides generated from the outline (per-slide colours / image / skip, full-screen presenter) + coloured tables (per-cell fill/text colours, add/remove rows and columns, SUM/AVG/formulas) that can be placed inside sections; exports everything to HTML |
| **Math Steps** | Type an equation or expression and solve it line by line: every line is checked, the first wrong one is explained ("a sign looks wrong", "you moved 3 across `=` without flipping it"), three levels of hints, and a full solution on request. Covers linear and quadratic equations (factoring, square root, quadratic formula) and simplifying; other polynomials are checked but not solved |
| **Basic Tools** | Clock, stopwatch, alarm, real calculator |
| **System Stats** | CPU / RAM / Disk / GPU + live FPS & ping graphs, plus an always-on-top overlay window |
| **Gallery Sorter** | Sort images and videos into folders, in-app video player. Remembers your sources, destinations and the picture you were on; next visit asks "Continue where you left off?" |
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
| **Backup** | Full, incremental and differential backups of a folder, with a preview first, a list of your backups and restore. Restoring never overwrites, deleting a backup is refused while later ones need it |
| **Folder Sync** | One way (mirror) or two way, with a preview first. Two way carries changes and deletions both ways and keeps both versions on a conflict. Overwritten or removed files are moved to a ".srboli-replaced" folder, never deleted |
| **AI (optional)** | Off by default. In Settings: turn it on, pick Ollama (a model on your PC) or an API key, and tick which tools may use it. Then File Sorter can write a rule from plain words, Text Editor can fix, shorten or rewrite text, and Learn can write a whole course. A built-in guide suggests an Ollama model for your PC and gives the install steps. The AI only proposes; you review before anything changes |
| **Quick Switcher** | Global keyboard shortcuts — jump to a screen, launch an app/script, open the file picker, or run a terminal command |
| **Minesweeper** | Classic Minesweeper: 3 difficulties, long-press to flag, tap a number to chord, timer and best times |
| **Infinite Mines** | Raw demo of an endless minesweeper: pan and zoom a map that is generated as you explore. Stepping on a mine leaves a crater with a scorched zone that heals as you solve the cells around it; a ring around it opens for you so recovery needs no blind guess; solved 9x9 sectors earn points (flagged mines pay a bonus) that pay for instant repairs and hints; dots and flashes reward each move |
| **Chess** | Full-rules chess (castling, en passant, promotion, check/mate/stalemate) vs. a built-in AI at 3 levels or two-player pass-and-play, with undo |
| **Disk Space** | Where did the space go? Scan a folder or drive once, then drill into the biggest folders (tap to go inside), see the 100 largest files and a breakdown by kind (pictures, video, archives...). Shows free space, can be stopped, copies a text report. Read-only: it never deletes anything |
| **Folder Colors** | Linux and Windows: give a folder a colour or one of your pictures as its icon, shown by the file manager (GNOME Files, Nemo, Dolphin, Thunar, Explorer). Optionally all subfolders too. "Reset to normal" removes exactly what it added; files inside are never touched |
| **Power Off When Done** | Computer only. Shut down, sleep or just notify when a task ends. It watches a program you pick (it exited), network traffic (the cloud upload stopped), CPU or disk activity (a render or file copy finished) staying quiet for a few minutes. It only counts once it has seen the task working, then shows a 60 second countdown you can cancel |
| **Startup Manager** | Computer only. Lists the apps that start when you log in (Linux autostart files, Windows Run keys and Startup folder) and lets you switch each one off or back on. Nothing is deleted. Android does not allow this, so the screen explains that |
| **Clipboard History** | What you copied lately: tap an entry to copy it again, pin the ones to keep, search, delete. Watches the clipboard while Srboli is open (can be paused). Kept in memory only unless you turn on "Keep after closing", because a clipboard often holds passwords |
| **QR Code** | Make a QR code from text, a link or a Wi-Fi login (live preview, two repair levels, up to 271 bytes), save it as a PNG, or read one from a picture (computer builds). Uses its own small encoder, no extra library |
| **Colour Picker** | Pick a colour from anywhere on the screen (computer; Srboli hides for a moment and captures it, not on Wayland) or from a picture (everywhere, drag to fine-tune). Edit with sliders or a hex code, copy as HEX / RGB / HSL, see the contrast with white and black, keep a palette |
| **Image Tools** | Two modes. *Each file*: shrink (longest side), compress (quality) and convert (JPG / PNG / WEBP) a whole batch and see before/after sizes. *Combine into one image*: stack, side by side or grid, with gap, size and order. Originals are never changed: results go to a `srboli_images` folder next to the first picture |
| **Drawing** | A simple sketchpad: brush, eraser, line, box and oval (outline or filled), 10 colours plus any hex colour, size slider, four backgrounds, undo / redo (Clear can be undone too), and Save PNG |
| **PDF Tools** | Merge several PDFs into one (set the order), or split one PDF: a file per page, N pages per file, or pick pages (`1-3, 5, 8-`) into a new file. Shows page counts, reports password-protected or damaged files clearly. Originals are never changed: results go to a `srboli_pdf` folder next to the first file. Needs the pypdf library (in the requirements files) |
| **Pomodoro** | Focus timer: focus rounds with short breaks and a long break after every few rounds (all lengths adjustable), a notification when a phase ends, the screen stays on while it runs, and a count of today's finished rounds. Keeps running while you use other tools; a skipped focus round is not counted |
| **File Inspector** | Look inside any file or folder: its real type from the contents (not the extension) with a warning when the name lies, MIME type, size, dates, permissions and owner, text or hex preview, and MD5/SHA-1/SHA-256/SHA-512 checksums with a "does it match the one I was given?" check. Read-only |
| **Bulk Renamer** | Rename a folder's files with stacked rules (replace, regex, case, prefix/suffix, numbering, dates, patterns, extension), a live old-to-new preview that flags clashes and bad names, a confirm step, and Undo. Swaps and chains work, and a failure part-way puts everything back |
| **Text Workbench** | One screen, five tabs, for the jobs people write small scripts for: sort, reverse, shuffle, dedupe, filter and number lines; pull emails, links, IPs, numbers or dates out of a text; test a regex with live matches and replace with it; compare two texts or files; count words and reading time. "Use result as input" chains the steps |
| **Learn** | Import an AI-written course (JSON) and study it Duolingo-style |
| **Cover / Privacy Boxes** | Desktop-only privacy boxes, blackout and hide-from-recording with global hotkeys |
| **Linux Shortcut Creator** | Fill in a form to make a `.desktop` launcher for the application menu (and Desktop); lists, edits and deletes the ones it made |
| **Touch Test** | Shows what each tap looks like to the app (finger vs. mouse duplicates) and has the duplicate-tap filter switch |
| **File Converter** | Batch-convert images (png/jpg/webp/bmp/gif/tiff/ico/pdf), documents (txt/md/html/docx/pdf/csv/tsv/json) and - on desktop with ffmpeg - audio/video |
| **Settings** | Reorder (within a section) / hide dashboard screens, toggle lazy-loading, manage the background service and autostart, move or clear your data folder safely, export logs/data as a zip, save a diagnostic report, see and grant Android permissions |
| **Open with / Share to Srboli** (Android) | Pick Srboli in "Open with" or "Share" for text, images, audio, video, PDFs and zips: a small chooser asks what to do: audio can play in the Music Player, text files open in the Text Editor, shared text in the Text Workbench, anything can go to the File Inspector. The original is never changed (a copy is used) |

## Requirements

- Python 3.10+
- Linux (Pop!OS / Ubuntu), Windows or macOS (Android via Buildozer)

Optional, per feature — install only what you need:

- `Pillow` — image thumbnails, EXIF read/write, image previews
- `opencv-python` — video thumbnails, frame strips, video metadata
- `pygame` — Music Player playback
- `ffpyplayer` — in-app video playback (Gallery Sorter)
- `psutil` — System Stats (Linux/Windows; Android uses a bundled fallback)
- `GPUtil` or `nvidia-smi` — GPU stats
- `ping3` — ping without shelling out to the system `ping`
- `send2trash` — File Sorter's delete action uses the recycle bin when available

## Download

Builds are on the repository's **Releases** page. On Windows, **extract the whole
zip first** (right-click -> Extract All) and run `Srboli.exe` from the extracted
`Srboli` folder. Starting it from inside the zip window fails with "Failed to
load Python DLL", because Windows only unpacks that one file and leaves the
`_internal` folder behind.

## Setup

Clone:

```bash
git clone https://github.com/somore100/Srboli.git
cd Srboli
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
```

```bat
python -m venv .venv
.venv\Scripts\activate           REM Windows
```

Install dependencies:

```bash
pip install -r requirements-desktop.txt
```

Run:

```bash
python3 main.py
```

Only one copy runs at a time per config (a second launch exits). Set
`SROBOLI_MULTI=1` to allow several, e.g. while developing.

Global hotkeys for the Cover tool need `pynput`, which is optional:

```bash
pip install -r requirements-hotkeys.txt
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -m "not display"          # Kivy-free core tests (CI runs the tests on release tags; run them yourself first with `xvfb-run -a bash tests/run_all.sh`)
xvfb-run -a pytest               # everything, including the screen tests (Linux)
```

`python3 main.py --selftest out.txt` loads every tool and writes
`SELFTEST OK` or the failures; the release builds run it too.

## Building an executable

Uses PyInstaller via the included `srboli.spec` (a one-folder build).

Linux / macOS:

```bash
pip install pyinstaller
pyinstaller srboli.spec
# Output: dist/Srboli/Srboli
```

Windows:

```bat
pip install pyinstaller
pyinstaller srboli.spec
REM Output: dist\Srboli\Srboli.exe
```

To include the optional global-hotkey support, install
`requirements-hotkeys.txt` and set `SROBOLI_HOTKEYS=1` before building.
Keyboard-hook libraries inside a packaged exe are a common antivirus false
positive on Windows, so it is left out by default.

## Project structure

```text
srboli/
├── main.py                  # App entry point (also dispatches --overlay, --daemon, --selftest)
├── app_data.py              # Config + data-directory manager
├── requirements-desktop.txt # Desktop dependencies
├── requirements-dev.txt     # Test dependencies
├── requirements-hotkeys.txt # Optional: pynput for Cover hotkeys
├── srboli.spec              # PyInstaller spec
├── buildozer.spec           # Android build
├── license.txt
├── core/                    # Logic and helpers (most of it Kivy-free and unit-tested)
│   ├── theme.py                 # Colour tokens + global widget styling
│   ├── navigation.py            # Screen manager, Loading screen, Esc / Ctrl+K
│   ├── permissions.py           # Android permission prompts, asked in context
│   ├── kivy_patches.py          # Android workarounds for Kivy internals (version-checked)
│   ├── single_instance.py       # One running copy per config
│   ├── safe_math.py             # Calculator arithmetic without eval()
│   ├── jsonio.py                # Atomic JSON writes, corrupt files quarantined
│   ├── logs.py / toast.py       # Capped log files, bottom toast messages
│   ├── window_state.py          # Remember window size and position
│   ├── selftest.py              # --selftest
│   ├── dashboard_core.py        # Dashboard sections / search / pins / recents
│   ├── file_safety.py           # "Safe to touch yet?" check + verified copy/move
│   ├── file_sorter_core.py      # Rule engine (shared with the daemon)
│   ├── file_sorter_watch.py     # Folder watcher for the background service
│   ├── backup_core.py           # Full / incremental / differential backup + restore
│   ├── sync_core.py             # One-way folder mirror (nothing deleted)
│   ├── twoway_core.py           # Two-way folder sync (keeps both versions on conflict)
│   ├── ai_core.py               # AI settings and requests (Ollama / API), off by default
│   ├── ai_rules.py              # Plain words -> a checked File Sorter rule
│   ├── transfer_core.py         # Fast Transfer engine + auto-tune
│   ├── reminders_core.py        # Reminder scheduling (shared with the daemon)
│   ├── daemon.py / daemon_ipc.py / autostart.py  # Background service
│   ├── chess_core.py            # Chess rules + AI
│   ├── infinite_mines_core.py   # Infinite Mines: seeded endless world, blasts, healing (no dependencies)
│   ├── math_steps_core.py       # Math Steps: parser, step checker, hints, linear + quadratic solver (no dependencies)
│   ├── learn_core.py            # Course engine for Learn
│   ├── disk_usage_core.py       # One-pass folder scan: folder sizes, biggest files, kinds for Disk Space
│   ├── folder_icons_core.py     # Coloured / picture folder icons for Folder Colors (gio, .directory, desktop.ini)
│   ├── clipboard_history_core.py # Clipboard History: newest-first list, dedupe, pins, search, optional save
│   ├── qr_core.py               # QR Code: own encoder (versions 1-10, L/M), PNG export, OpenCV image scan, Wi-Fi text
│   ├── color_core.py            # Colour Picker: parse/convert HEX-RGB-HSL, contrast, screen/picture sampling, palette
│   ├── image_tools_core.py      # Image Tools: batch shrink/compress/convert, combine into one image
│   ├── drawing_core.py          # Drawing: strokes, undo/redo/clear history, Pillow rendering to PNG
│   ├── pdf_tools_core.py        # PDF Tools: page-range parsing, merge, split, extract (pypdf, loaded on use)
│   ├── pomodoro_core.py         # Pomodoro: phase state machine on an injected clock, settings, per-day totals
│   ├── startup_core.py          # Startup Manager: list/switch login-start entries (Linux .desktop, Windows Run + StartupApproved)
│   ├── when_done_core.py        # Power Off When Done: quiet-detection state machine, process/network/CPU/disk sampler, power commands
│   ├── gallery_session.py       # Gallery Sorter: remembers the last session for "Continue where you left off?"
│   ├── clean_env.py             # Launch system programs without the AppImage's bundled libraries
│   ├── file_inspect_core.py     # File type by contents, dates, permissions, checksums and previews for File Inspector
│   ├── bulk_rename_core.py      # Rules, preview, safe two-phase rename and undo for Bulk Renamer
│   ├── text_workbench_core.py   # Lines, extract, regex, diff and stats for Text Workbench
│   ├── outline_core.py / slides_core.py / table_core.py  # Full Editor
│   ├── converter_core.py        # File Converter engine
│   ├── cover_core.py / cover_app.py  # Cover boxes (separate tkinter process)
│   ├── desktop_entry.py         # .desktop launcher builder
│   ├── touch_dedupe.py / tap_guard.py  # Ghost-tap filters
│   ├── notify.py                # Desktop notifications
│   ├── android_storage.py / psutil_lite.py  # Android helpers
│   ├── pathbar.py / seekbar.py / tickbox.py  # Shared widgets
│   └── version.py               # The one place the app version lives
├── screens/
│   ├── registry.py              # Single source of truth for the screen list
│   ├── dashboard_screen.py      # Tile dashboard
│   ├── scaffold.py              # ToolScreen: shared top bar + content width
│   ├── settings_screen.py / data_location.py
│   ├── dialogs.py               # Shared confirm / message popups
│   └── *_screen.py              # One file per tool (see Features)
└── tests/                       # Run with pytest; each test_*.py also runs on its own
```

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

Pushing a `v*` tag also builds the Windows EXE, Linux AppImage, macOS app and
Android APK in GitHub Actions (`.github/workflows/build-srboli.yml`) and
publishes them on the repository's **Releases** page
(`Srboli-<tag>-Windows.zip`, `-x86_64.AppImage`, `.apk`, `-macOS.zip`), so
finished builds can be downloaded without opening the workflow run.

### Touch notes (Android)

Finger taps arrive from SDL once; the app switches off SDL's synthesized mouse
events so a tap is never doubled (Touch Test shows "Filter active"). Finger
touches carry `button=None`, so code that treats "has a button" as "is a mouse"
must check for a real button name (`"left"`, `"right"`).

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

## Contributing

Issues and pull requests are welcome — new tool screens, bug fixes, or
packaging improvements are all fair game. Run `pytest -m "not display"` before opening a pull request.
## License

This project is source-available software. You are free to view, study,
modify, fork, and share the project for non-commercial purposes. Addons,
plugins, extensions, and integrations are also permitted under the license
terms. See [license.txt](license.txt) for full terms.
