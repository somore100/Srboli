# Srboli

**A pocket swiss-army knife desktop app** — 16 tools in one window, built with Python + Kivy.

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-lightgrey)

<p align="center">
  <img width="49%" alt="Srboli main screen" src="https://github.com/user-attachments/assets/943e84d4-d894-47bc-b1f9-ec6149f3d7bf" />
  <img width="49%" alt="Srboli tool screen" src="https://github.com/user-attachments/assets/22bde96b-28af-4b57-97bf-23872f33dfc3" />
</p>

From a countdown timer to a metadata inspector, Srboli bundles the small utilities you'd otherwise hunt down as separate apps into one lightweight desktop tool, with global shortcuts to jump between them instantly.

## Features

| Screen | What it does |
|---|---|
| Loading / Timer | Countdown timer with shutdown option |
| Text Editor | Plain text editor with colour tags, autosave, script mode |
| Script Mode | Paste full text, auto-copy chunks one by one |
| Full Editor | Word + Slides + Spreadsheet in one |
| Basic Tools | Clock, stopwatch, alarm, real calculator |
| System Stats | CPU/RAM/Disk/GPU live stats + ping/FPS graphs + overlay window |
| Gallery Sorter | Sort images and videos into folders, in-app video player |
| Music Player | Playlist manager with pygame playback |
| Random Tools | Number/password/dice/list randomizer |
| Image to Text | Base64 image encoder/decoder |
| Morse Converter | Text ↔ Morse code |
| Backrooms | JSON-driven Backrooms level guide |
| Wheel of Names | Weighted spinner |
| Shape Generator | Procedural logo/pattern generator |
| Metadata Inspector | EXIF/video metadata viewer + AI image detector |
| Quick Switcher | Global keyboard shortcuts to jump between screens |

## Requirements

- Python 3.10+
- Linux (Pop!_OS / Ubuntu) or Windows

## Setup

```bash
# Clone
git clone https://github.com/somore100/Srboli.git
cd Srboli

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Run
python3 main.py
```

## Building an executable

Uses [PyInstaller](https://pyinstaller.org/) via the included `srboli.spec`.

**Linux:**
```bash
pip install pyinstaller
pyinstaller srboli.spec
# Output: dist/Srboli
```

**Windows:**
```bat
pip install pyinstaller
pyinstaller srboli.spec
REM Output: dist\Srboli.exe
```

## Project Structure

```
srboli/
├── main.py              # App entry point
├── app_data.py          # Data directory manager
├── _overlay_app.py      # System stats overlay (separate process)
├── requirements.txt
├── srboli.spec           # PyInstaller spec
└── screens/
    ├── backrooms_screen.py
    ├── basic_tools_screen.py
    ├── full_editor_screen.py
    ├── gallery_sorter_screen.py
    ├── image_text_screen.py
    ├── loading_timer_screen.py
    ├── metadata_screen.py
    ├── morse_screen.py
    ├── music_screen.py
    ├── quickswitcher_screen.py
    ├── randomizer.py
    ├── script_mode_screen.py
    ├── shape_generator_screen.py
    ├── spin_screen.py
    ├── system_stats_screen.py
    ├── text_editor_screen.py
    └── unhelpful_calc_screen.py
```

## Contributing

Issues and pull requests are welcome — new tool screens, bug fixes, or packaging improvements (a macOS build is an open gap) are all fair game.

## License

This project is source-available software.

You are free to view, study, modify, fork, and share the project for non-commercial purposes. Addons, plugins, extensions, and integrations are also permitted under the license terms.

Commercial distribution of this project, or substantially derived versions of it, is not permitted without permission from the copyright holder.

See the [LICENSE](LICENSE) file for the full terms.
