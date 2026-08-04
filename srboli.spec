# srboli.spec — PyInstaller build spec for Srboli

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

kivy_datas = collect_data_files('kivy', includes=['**/*'])

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('screens', 'screens'),
        ('app_data.py', '.'),
        ('logo.png', '.'),
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
    name='Srboli',
    debug=False,
    strip=False,
    upx=True,
    console=False,

    # App icon
    icon='logo.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='Srboli',
)
