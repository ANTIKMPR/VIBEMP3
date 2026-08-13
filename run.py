"""
Лаунчер MP3-плеера.

Запускай именно этот файл: `python run.py`

Перед стартом GUI проверяет:
  1. Установлены ли нужные Python-пакеты (pygame, pydub, numpy)
  2. Доступен ли ffmpeg в PATH (нужен для декодирования mp3)

Если чего-то не хватает — печатает понятную инструкцию вместо
непонятного traceback, и не даёт окну открыться в сломанном виде.
"""

import shutil
import subprocess
import sys


REQUIRED_PACKAGES = ["pygame", "pydub", "numpy"]
RECOMMENDED_PACKAGES = [
    ("PIL", "Pillow"),      # нужна для надёжной загрузки .ico-иконки
    ("mutagen", "mutagen"),  # нужна для чтения ID3-метаданных (название/исполнитель/альбом/обложка)
]

# В PyInstaller-сборке (frozen exe) все Python-зависимости уже вшиты в сам
# exe на этапе сборки — проверять их через pip/import на компьютере
# пользователя не нужно и не имеет смысла (там даже нет системного pip).
# ffmpeg — исключение: это внешний бинарник, PyInstaller его не встраивает
# автоматически, так что эту проверку оставляем всегда, в т.ч. в exe.
IS_FROZEN = getattr(sys, "frozen", False)


def check_python_packages(packages: list[str]) -> list[str]:
    """Возвращает список отсутствующих пакетов из переданного списка (имена для import)."""
    missing = []
    for package in packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    return missing


def check_ffmpeg() -> bool:
    """Проверяет, доступен ли ffmpeg в PATH."""
    if shutil.which("ffmpeg") is not None:
        return True

    # На некоторых системах shutil.which не находит .exe без явного вызова —
    # подстрахуемся прямым запуском.
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def main():
    print("Проверка зависимостей...")

    if IS_FROZEN:
        print("✓ Запущено как готовая сборка — Python-пакеты уже встроены")
    else:
        missing_packages = check_python_packages(REQUIRED_PACKAGES)
        if missing_packages:
            print()
            print("❌ Не хватает Python-пакетов:", ", ".join(missing_packages))
            print()
            print("Установи их командой:")
            print("    pip install -r requirements.txt")
            print()
            sys.exit(1)

        print("✓ Python-пакеты на месте")

        missing_recommended = [
            pip_name for import_name, pip_name in RECOMMENDED_PACKAGES
            if check_python_packages([import_name])
        ]
        if missing_recommended:
            print(f"⚠ Не хватает необязательных пакетов: {', '.join(missing_recommended)}")
            print("  Без них плеер запустится нормально, но иконка приложения")
            print("  (.ico) может не загрузиться на некоторых системах.")
            print("  Поставить: pip install " + " ".join(missing_recommended))
        else:
            print("✓ Необязательные пакеты на месте")

    if not check_ffmpeg():
        print()
        print("❌ ffmpeg не найден в PATH.")
        print("   Он нужен для декодирования mp3-файлов.")
        print()
        print("Установка на Windows (в новом окне CMD от администратора):")
        print("    winget install -e --id Gyan.FFmpeg")
        print("   После установки закрой и заново открой консоль.")
        print()
        print("Установка на macOS:")
        print("    brew install ffmpeg")
        print()
        print("Установка на Linux (Debian/Ubuntu):")
        print("    sudo apt install ffmpeg")
        print()
        sys.exit(1)

    print("✓ ffmpeg найден")
    print()
    print("Запускаю плеер...")
    print()

    # Импортируем main только после успешных проверок, чтобы не словить
    # непонятный ImportError, если что-то из зависимостей всё же не так.
    import main as player_main
    player_main.main()


if __name__ == "__main__":
    main()
