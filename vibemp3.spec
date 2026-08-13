# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec-файл для сборки VIBEMP3 в exe.

Собирает ПАПКУ с exe (--onedir), а не однофайловый exe (--onefile) —
это осознанный выбор: в onedir-режиме exe читает файлы рядом с собой
напрямую и без временной распаковки, поэтому папки resources/, themes/
и файл settings.json можно просто положить рядом с VIBEMP3.exe и всё
будет работать так же, как при запуске python-скриптом. В onefile-режиме
пришлось бы городить более хрупкую логику с sys._MEIPASS для одних путей
и sys.executable для других — onedir проще и надёжнее для конечного
пользователя, который просто открывает папку и видит все файлы.

Использование:
    pyinstaller vibemp3.spec

Результат появится в dist/VIBEMP3/ — это и есть готовая для распространения
папка. Ресурсы (resources/, themes/, settings.json, albums.json) НЕ
включаются в саму сборку этим spec-файлом — их нужно скопировать в
dist/VIBEMP3/ рядом с VIBEMP3.exe вручную один раз после первой сборки
(см. build.bat, который делает это автоматически).
"""

import sys
from pathlib import Path

block_cipher = None

# Корень проекта — папка, где лежит этот .spec файл
PROJECT_ROOT = Path(SPECPATH)

a = Analysis(
    ['run.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    # datas можно было бы использовать, чтобы PyInstaller сам скопировал
    # resources/ внутрь dist/VIBEMP3/ — но мы делаем это отдельным шагом
    # в build.bat, чтобы пересборка exe не требовала пересборки ресурсов
    # каждый раз (быстрее при разработке) и чтобы пользователь мог менять
    # resources/themes/settings.json в готовой сборке без пересборки exe.
    datas=[],
    hiddenimports=[
        'pygame',
        'numpy',
        'pydub',
        'mutagen',
        'mutagen.mp3',
        'mutagen.id3',
        'PIL',
        'PIL.Image',
    ],
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
    [],
    exclude_binaries=True,
    name='VIBEMP3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # без консольного окна — обычное GUI-приложение
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'resources' / 'logo' / 'icon.ico')
        if (PROJECT_ROOT / 'resources' / 'logo' / 'icon.ico').is_file() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VIBEMP3',
)
