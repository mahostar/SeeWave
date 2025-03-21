# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Get absolute paths for the image files
current_dir = os.getcwd()  # Use current working directory instead of __file__
logo_path = os.path.join(current_dir, 'logo.png')
svg_path = os.path.join(current_dir, 'image.svg')

print(f"Looking for logo at: {logo_path}")
print(f"Looking for SVG at: {svg_path}")

if not os.path.exists(logo_path):
    raise FileNotFoundError(f"Logo file not found at {logo_path}")
if not os.path.exists(svg_path):
    raise FileNotFoundError(f"SVG file not found at {svg_path}")

# Add GTK and Cairo DLLs
binaries = []
gtk_path = os.path.join(os.environ.get('SYSTEMDRIVE', 'C:'), 'msys64', 'ucrt64', 'bin')
gtk_dlls = [
    'libcairo-2.dll',
    'libcairo-gobject-2.dll',
    'libgdk_pixbuf-2.0-0.dll',
    'libgio-2.0-0.dll',
    'libglib-2.0-0.dll',
    'libgobject-2.0-0.dll',
    'libgtk-4-1.dll',
    'libpango-1.0-0.dll',
    'libpangocairo-1.0-0.dll'
]

for dll in gtk_dlls:
    dll_path = os.path.join(gtk_path, dll)
    if os.path.exists(dll_path):
        binaries.append((dll_path, '.'))

# Add hidden imports
hidden_imports = [
    'cairo',
    'PIL',
    'PIL._tkinter_finder',
    'numpy',
    'ffmpeg',
    'tqdm'
]

a = Analysis(
    ['main_gui.py'],
    pathex=[current_dir],
    binaries=binaries,
    datas=[
        (logo_path, '.'),
        (svg_path, '.'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SeeWave',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False for a windowed application
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=logo_path
)