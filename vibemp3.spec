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
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# Корень проекта — папка, где лежит этот .spec файл
PROJECT_ROOT = Path(SPECPATH)

# imageio-ffmpeg хранит СВОЙ бинарник ffmpeg внутри пакета (не системный),
# в подпапке binaries/ — это не Python-код, PyInstaller не подхватывает его
# автоматически по hiddenimports, нужно явно собрать как data-файлы.
# Без этого шага видео-фон VIBE-SYNC не будет работать в собранном exe даже
# если сам импорт imageio_ffmpeg проходит успешно (модуль загрузится, но
# при попытке декодировать видео не найдёт исполняемый ffmpeg рядом с собой).
_imageio_ffmpeg_datas = collect_data_files('imageio_ffmpeg')

a = Analysis(
    ['run.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=collect_dynamic_libs('pygame'),
    # datas можно было бы использовать, чтобы PyInstaller сам скопировал
    # resources/ внутрь dist/VIBEMP3/ — но мы делаем это отдельным шагом
    # в build.bat, чтобы пересборка exe не требовала пересборки ресурсов
    # каждый раз (быстрее при разработке) и чтобы пользователь мог менять
    # resources/themes/settings.json в готовой сборке без пересборки exe.
    # imageio_ffmpeg — исключение: его бинарник обязателен для видео-фона
    # VIBE-SYNC и должен попасть внутрь сборки, а не рядом отдельно.
    datas=_imageio_ffmpeg_datas,
    hiddenimports=[
        'pygame',
        'pygame.sndarray',
        'pygame.surfarray',
        'numpy',
        'pydub',
        'pydub.utils',
        'audioop',  # backport audioop-lts на Python 3.13+, сам audioop убран из stdlib
        'mutagen',
        'mutagen.mp3',
        'mutagen.id3',
        'mutagen.oggvorbis',
        'mutagen.ogg',
        'mutagen.flac',
        'PIL',
        'PIL.Image',
        'PIL.WebPImagePlugin',
        'imageio',
        'imageio.v3',
        'imageio.plugins',
        'imageio.plugins.ffmpeg',
        'imageio_ffmpeg',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VIBEMP3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # без консольного окна — обычное GUI-приложение
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / 'resources' / 'logo' / 'icon.ico')
        if (PROJECT_ROOT / 'resources' / 'logo' / 'icon.ico').is_file() else None,
)

# onefile: всё (включая то, что раньше лежало в _internal\) теперь зашито
# прямо внутрь VIBEMP3.exe. COLLECT больше не нужен — папки dist\VIBEMP3\
# как раньше не будет, будет один файл dist\VIBEMP3.exe.
