@echo off
REM Запуск MP3-плеера двойным кликом на Windows.
REM Если рядом есть папка venv — используется python из неё,
REM иначе берётся системный python.

setlocal

if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0run.py"
) else (
    python "%~dp0run.py"
)

echo.
pause
