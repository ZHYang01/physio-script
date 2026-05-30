# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Physio Script - macOS .app bundle

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Project root
ROOT = Path(SPECPATH)

# Local transcription stack has native libs and bundled data (e.g. the silero
# VAD model inside faster_whisper, the ctranslate2 / onnxruntime shared libs).
# collect_all pulls in their binaries + data + hidden imports so the frozen app
# can run transcription fully offline.
_fw_datas, _fw_binaries, _fw_hidden = [], [], []
for _pkg in ('faster_whisper', 'ctranslate2', 'onnxruntime', 'tokenizers', 'av'):
    _d, _b, _h = collect_all(_pkg)
    _fw_datas += _d
    _fw_binaries += _b
    _fw_hidden += _h

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[
        ('/opt/homebrew/lib/libportaudio.dylib', '.'),
    ] + _fw_binaries,
    datas=[
        (str(ROOT / 'prompts'), 'prompts'),
        # Qt plugins are bundled automatically by PyInstaller's PyQt6 hook
        # (which also fixes their @rpath links). Do NOT copy them manually —
        # a raw copy leaves the platform plugins unable to find the Qt
        # frameworks and the app fails with "Could not find the Qt platform
        # plugin 'cocoa'".
    ] + _fw_datas,
    hiddenimports=[
        'pyaudio',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'requests',
        'pyperclip',
        'dotenv',
        'numpy',
    ] + _fw_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / 'qt_hook.py')],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'scipy',
        'PIL',
        'PySide6',
        'PySide2',
        'PyQt5',
        'shiboken6',
    ],
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
    name='PhysioScript',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'PhysioScript.icns') if (ROOT / 'PhysioScript.icns').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PhysioScript',
)

app = BUNDLE(
    coll,
    name='PhysioScript.app',
    icon=str(ROOT / 'PhysioScript.icns') if (ROOT / 'PhysioScript.icns').exists() else None,
    bundle_identifier='com.physioscript.app',
    info_plist={
        'CFBundleDisplayName': 'Physio Script',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSMicrophoneUsageDescription': 'Physio Script needs microphone access to record patient sessions for transcription.',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
    },
)
