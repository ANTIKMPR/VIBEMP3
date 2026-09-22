@echo off
REM Запуск MP3-плеера двойным кликом на Windows.
REM Если рядом есть папка venv — используется python из неё,
REM иначе берётся системный python.
REM
REM Перед запуском проверяет, установлены ли зависимости из requirements.txt,
REM и если нет — ставит их сам через pip, не заставляя пользователя делать
REM это вручную.

setlocal

set "ROOT=%~dp0"

if exist "%ROOT%venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

REM Быстрая проверка: пытаемся импортировать все обязательные пакеты одной
REM командой. Если что-то из них отсутствует — ставим requirements.txt целиком
REM (проще и надёжнее, чем ставить каждый недостающий пакет по отдельности).
"%PYTHON%" -c "import pygame, pydub, numpy, mutagen, imageio" 2>nul
if errorlevel 1 (
    echo Не хватает некоторых зависимостей — устанавливаю из requirements.txt...
    echo.
    if exist "%ROOT%requirements.txt" (
        "%PYTHON%" -m pip install -r "%ROOT%requirements.txt"
        if errorlevel 1 (
            echo.
            echo [ОШИБКА] Не удалось установить зависимости через pip.
            echo Проверь подключение к интернету и что Python/pip установлены корректно.
            echo.
            pause
            exit /b 1
        )
        echo.
        echo Зависимости установлены.
        echo.
    ) else (
        echo [ОШИБКА] Файл requirements.txt не найден рядом с run.bat.
        pause
        exit /b 1
    )
)

"%PYTHON%" "%ROOT%run.py"

echo.
pause
