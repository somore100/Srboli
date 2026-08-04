# srboli.spec — Cross platform PyInstaller spec for Srboli

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Kivy data
kivy_datas = collect_data_files("kivy")

# Optional folders/files
datas = [
    ("screens", "screens"),
    ("app_data.py", "."),
    ("_overlay_app.py", "."),
]

for item in [
    ("wheel_saves", "wheel_saves"),
    ("assets", "assets"),
]:
    if os.path.exists(item[0]):
        datas.append(item)


hiddenimports = [
    "kivy",
    "kivy.core.window",
    "kivy.core.text.markup",
    "kivy.uix.video",

    "ffpyplayer",
    "ffpyplayer.player",

    "PIL",
    "PIL.Image",
    "PIL.ExifTags",

    "cv2",

    "psutil",

    "pygame",
    "pygame.mixer",

    "threading",
    "json",
    "subprocess",
    "re",
    "math",
    "collections",
]


a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas + kivy_datas,

    hiddenimports=hiddenimports,

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=[
        "tkinter",
    ],

    win_no_prefer_redirects=False,
    win_private_assemblies=False,

    cipher=block_cipher,
    noarchive=False,
)


pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)


exe = EXE(
    pyz,
    a.scripts,

    [],
    exclude_binaries=True,

    name="Srboli",

    debug=False,
    bootloader_ignore_signals=False,

    strip=False,

    upx=True,

    console=False,

    disable_windowed_traceback=False,

    target_arch=None,

    codesign_identity=None,
    entitlements_file=None,
)


coll = COLLECT(
    exe,

    a.binaries,
    a.datas,
    a.zipfiles,

    strip=False,

    upx=True,

    upx_exclude=[],

    name="Srboli",
)