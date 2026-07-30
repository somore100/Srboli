# srboli.spec — PyInstaller build spec for Srboli
# Run: pyinstaller srboli.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect kivy data files
kivy_datas = collect_data_files('kivy', includes=['**/*'])

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('screens', 'screens'),
        ('app_data.py', '.'),
        ('_overlay_app.py', '.'),
    ] + kivy_datas,
    hiddenimports=[
        'kivy',
        'kivy.core.window',
        'kivy.core.text.markup',
        'kivy.uix.video',
        'ffpyplayer',
        'ffpyplayer.player',
        'PIL',
        'PIL.Image',
        'PIL.ExifTags',
        'cv2',
        'psutil',
        'pygame',
        'pygame.mixer',
        'colorsys',
        'threading',
        'json',
        'subprocess',
        're',
        'math',
        'collections',
    ] + collect_submodules('kivy'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Srboli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Srboli',
)
