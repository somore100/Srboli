# srboli.spec
import os
from PyInstaller.utils.hooks import collect_data_files
datas = [
    ('screens', 'screens'),
    ('app_data.py', '.'),
]
datas += collect_data_files('kivy')
datas += collect_data_files('ffpyplayer')
hiddenimports = [
    'kivy',
    'kivy.core.window',
    'kivy.core.text.markup',
    'kivy.uix.video',
    'ffpyplayer',
    'ffpyplayer.player',
    'PIL',
    'PIL.Image',
    'cv2',
    'psutil',
    'pygame',
    'pygame.mixer',
    'send2trash',
]
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'pytest',
        'kivy.tests',
    ],
    noarchive=False,
)
pyz = PYZ(
    a.pure,
    a.zipped_data
)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Srboli',
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Srboli',
)
