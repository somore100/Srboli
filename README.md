# Srboli v2.0 — Setup Guide (PopOS / Linux + Windows)

## Quick start on PopOS

```bash
# 1. System deps (Kivy needs these on Linux)
sudo apt install -y python3-pip python3-venv \
    libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev \
    libgstreamer1.0-dev gstreamer1.0-plugins-{base,good,bad,ugly} \
    libmtdev-dev xclip

# 2. Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python packages
pip install -r requirements.txt

# 4. Run
python main.py
```

## File layout expected

```
srboli/
├── main.py
├── requirements.txt
├── screens/
│   ├── __init__.py
│   ├── tts_screen.py          ← not changed (optional)
│   ├── stt_screen.py          ← not changed (optional)
│   ├── image_text_screen.py   ← UPDATED
│   └── converted/
│       ├── __init__.py
│       ├── backrooms_screen.py       ← UPDATED
│       ├── loading_timer_screen.py   ← UPDATED
│       ├── morse_screen.py           ← UPDATED
│       ├── music_screen.py           ← UPDATED
│       ├── randomizer.py             ← UPDATED (class: UtilityToolsScreen)
│       ├── spin_screen.py            ← UPDATED (arrow fixed)
│       ├── system_stats_screen.py    ← NEW
│       └── unhelpful_calc_screen.py  ← UPDATED
```

## What changed per file

| File | Changes |
|---|---|
| `main.py` | No Windows-only paths, lazy import, Linux model cache dir |
| `spin_screen.py` | Arrow direction fixed, labels no longer use broken canvas rotation |
| `randomizer.py` | Class renamed `UtilityToolsScreen`, added History tab, Dice tab, password strength bar |
| `loading_timer_screen.py` | Cross-platform shutdown (`systemctl`), pause/resume, presets, colour bar |
| `music_screen.py` | Volume slider, pause, track remove, `xdg-open` fallback, home-dir file picker |
| `morse_screen.py` | Punctuation support, copy button, history list |
| `unhelpful_calc_screen.py` | Spinner animation, expression preview, more errors, copy button |
| `backrooms_screen.py` | Home-dir file picker, config saved to `~/.srboli_backrooms_path.txt` |
| `image_text_screen.py` | Replaced tkinter dialogs with Kivy-native (works on Wayland) |
| `system_stats_screen.py` | **NEW** — CPU/RAM/disk/GPU text + live FPS & ping graphs |

## Optional extras

**Real ICMP ping** (instead of subprocess fallback):
```bash
pip install ping3
# ping3 needs raw socket access on Linux:
sudo setcap cap_net_raw+ep $(which python3)
# OR just run with sudo (not recommended)
```

**NVIDIA GPU info**:
```bash
pip install gputil
# or install nvidia-smi (comes with NVIDIA drivers)
```

**Startup slow?**
The TTS/STT screens load heavy models (Torch, Coqui). If you don't use them,
comment out their entries in `SCREENS` in `main.py`. Everything else starts in ~1s.

## Known Kivy quirks on Linux

- **Wayland**: if the window doesn't appear, try `export DISPLAY=:0` or
  force X11: `export SDL_VIDEODRIVER=x11`
- **Audio**: if pygame mixer fails, install `gstreamer1.0-plugins-good`
- **FileChooser**: all file pickers now start at `~/` (home dir) instead of
  Windows-style paths
