# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для сборки Dreamworld.exe с иконкой.
Запуск: .venv/bin/pyinstaller Dreamworld.spec
"""

import os

block_cipher = None

ROOT = os.path.abspath('.')

a = Analysis(
    ['main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        ('assets/dreamworld.ico', 'assets'),
        ('manifest.json', '.'),
        ('launcher_manifest.json', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['libtorrent'],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='Dreamworld',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=os.path.join(ROOT, 'assets', 'dreamworld.ico'),
)
