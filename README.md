# Srboli

A pocket swiss-knife desktop app built with Python + Kivy.

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
- Linux (PopOS/Ubuntu) or Windows

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

## Building executable (Linux)

```bash
pip install pyinstaller
pyinstaller srboli.spec
# Output: dist/Srboli
```

## Building executable (Windows)

```bat
pip install pyinstaller
pyinstaller srboli.spec
REM Output: dist\Srboli.exe
```

## Project structure

```
srboli/
├── main.py              # App entry point
├── app_data.py          # Data directory manager
├── _overlay_app.py      # System stats overlay (separate process)
├── requirements.txt
├── srboli.spec          # PyInstaller spec
└── screens/
    ├── __init__.py
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

## License

MIT

<img width="937" height="637" alt="Srboli 2026-08-24 18-43-34-V2" src="https://github.com/user-attachments/assets/943e84d4-d894-47bc-b1f9-ec6149f3d7bf" />
<img width="937" height="637" alt="Srboli 2026-08-24 18-43-14-V2" src="https://github.com/user-attachments/assets/22bde96b-28af-4b57-97bf-23872f33dfc3" />
