# -*- mode: python ; coding: utf-8 -*- 

import os

a = Analysis(
    ['client/client.py'],  # Main script
    pathex=[],
    binaries=[],
    datas=[
        ('config.cfg', '.'),  # Include config.cfg in the root of the dist folder
        (os.path.join('assets', 'back_img.png'), 'assets'),
        (os.path.join('assets', 'timer.png'), 'assets'),
        (os.path.join('assets', 'timer.ico'), 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,  # Ensure datas is included
    [],
    name='client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/timer.ico'],
)
