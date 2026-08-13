@echo off
REM Собирает VIBEMP3 в exe (папка dist\VIBEMP3\) и копирует туда же
REM ресурсы (resources\, themes\, если есть) — после сборки в
REM dist\VIBEMP3\ будет самодостаточная папка: VIBEMP3.exe + resources\
REM рядом, ничего больше не нужно для запуска на чужом компьютере.

setlocal

set "ROOT=%~dp0"
set "DIST=%ROOT%dist\VIBEMP3"

echo ============================================
echo  VIBEMP3 - сборка exe
echo ============================================
echo.

REM Используем python из venv, если есть — так же, как run.bat
if exist "%ROOT%venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Проверяю, установлен ли PyInstaller...
"%PYTHON%" -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller не найден, устанавливаю...
    "%PYTHON%" -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo [ОШИБКА] Не удалось установить PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo Собираю exe (это может занять пару минут)...
"%PYTHON%" -m PyInstaller "%ROOT%vibemp3.spec" --noconfirm
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Сборка не удалась, смотри вывод выше.
    pause
    exit /b 1
)

echo.
echo Копирую ресурсы рядом с exe...

if exist "%ROOT%resources" (
    xcopy /E /I /Y "%ROOT%resources" "%DIST%\resources" >nul
    echo   resources\ скопирована
) else (
    echo   [!] Папка resources\ не найдена рядом со скриптом — пропускаю
)

if exist "%ROOT%themes" (
    xcopy /E /I /Y "%ROOT%themes" "%DIST%\themes" >nul
    echo   themes\ скопирована
)

if exist "%ROOT%settings.json" (
    copy /Y "%ROOT%settings.json" "%DIST%\settings.json" >nul
    echo   settings.json скопирован
)

if exist "%ROOT%albums.json" (
    copy /Y "%ROOT%albums.json" "%DIST%\albums.json" >nul
    echo   albums.json скопирован
)

echo.
echo ============================================
echo  Готово! Собранное приложение здесь:
echo  %DIST%
echo.
echo  Внутри лежит VIBEMP3.exe и resources\ рядом —
echo  всю папку dist\VIBEMP3\ можно скопировать на
echo  другой компьютер и запустить без Python.
echo ============================================
echo.
pause
