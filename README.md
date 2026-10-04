# Srboli

Pocket swiss-army-knife desktop app — **22 tools in one window**, built with
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
| **Dashboard** | Quick-access hub to switch between all tools |
| **Loading / Timer** | Countdown timer with shutdown / suspend / notify actions |
| **Text Editor** | Plain-text editor with Raw ⇄ Styled Markdown view, colour wheel, autosave |
| **Script / Teleprompter** | Paste full text, auto-copy chunks one at a time; auto-advance on paste |
| **Full Editor** | Word-like rich text + multi-slide presenter + basic spreadsheet |
| **Basic Tools** | Clock, stopwatch, alarm, real calculator |
| **System Stats** | CPU / RAM / Disk / GPU + live FPS & ping graphs, plus an always-on-top overlay window |
| **Gallery Sorter** | Sort images and videos into folders, in-app video player |
| **Music Player** | Playlist manager with pygame playback |
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
| **File Sorter** | Rule-based file organizer (extension / name / size / date / image metadata → move / copy / rename / delete) |
| **Reminders** | To-do + timed reminders, daily/weekly repeats, desktop notifications via the background service |
| **Fast File Transfer** | Parallel / batched copy / move for folders of many smaller files |
| **Quick Switcher** | Global keyboard shortcuts — jump to a screen, launch an app/script, open the file picker, or run a terminal command |
| **Settings** | Reorder / hide dashboard screens, toggle lazy-loading, manage the background service and autostart |
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

pip install -r requirements.txt

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
│   └── psutil_lite.py           # /proc-based psutil fallback for Android
└── screens/
    ├── __init__.py
    ├── registry.py              # Single source of truth for the screen list
    ├── data_dir_screen.py       # First-launch + data-directory chooser
    ├── settings_screen.py
    ├── _overlay_app.py          # Always-on-top stats overlay (separate process)
    ├── sys_info.py              # Shared GPU / ping helpers
    ├── md_parse.py              # Kivy-free Markdown parser
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
    └── quickswitcher_screen.py

Contributing

Issues and pull requests are welcome — new tool screens, bug fixes, or
packaging improvements (macOS build is an open gap) are all fair game.
License

This project is source-available software. You are free to view, study,
modify, fork, and share the project for non-commercial purposes. Addons,
plugins, extensions, and integrations are also permitted under the license
terms. See the LICENSE file for full terms.