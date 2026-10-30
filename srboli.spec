# srboli.spec
import os
from PyInstaller.utils.hooks import collect_data_files
# Screens are loaded with importlib (main.try_import), so PyInstaller's import
# scan never sees them or the core.* modules only they use. List every module
# in screens/ and core/ as a hidden import so they (and their own imports)
# are compiled into the build. screens/ also stays as data: the overlay is
# started as a script from there, and backrooms looks for its json next to it.
def _modules(pkg):
    base = os.path.join(SPECPATH, pkg)
    return [pkg + '.' + f[:-3] for f in sorted(os.listdir(base))
            if f.endswith('.py') and f != '__init__.py'
            and '.sync-conflict-' not in f]

datas = [
    ('screens', 'screens'),
    ('app_data.py', '.'),
    ('backrooms_data.json', '.'),
    ('backrooms_data.json', 'screens'),
]
datas += collect_data_files('kivy')
datas += collect_data_files('ffpyplayer')
hiddenimports = ['screens', 'core'] + _modules('screens') + _modules('core') + [
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
    'tkinter',
    'pynput',
    'pynput.keyboard',
    'pynput.keyboard._xorg',
    'pynput.keyboard._win32',
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
