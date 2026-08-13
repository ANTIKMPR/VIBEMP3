"""
Загрузка кастомного шрифта приложения (Bildungswirkung-Regular.otf) с фолбэком
на системный Arial, если файл не найден или не смог загрузиться.

Шрифт лежит в resources/font/ рядом с остальными ресурсами (логотип, иконка) —
путь считается от расположения main.py, а не хардкодится под конкретный
компьютер/пользователя.
"""

import os
import pygame


_cache: dict[tuple[str, int, bool], pygame.font.Font] = {}


def get_font(base_dir: str, size: int, bold: bool = False) -> pygame.font.Font:
    """
    Возвращает кастомный шрифт приложения нужного размера. Результаты
    кэшируются (создание Font — не бесплатная операция, а один и тот же
    размер обычно запрашивается на каждый кадр).

    Если .otf-файл не найден или pygame не смог его прочитать — тихо
    откатывается на системный Arial, чтобы приложение не падало на
    компьютерах без этого файла в resources/font/.
    """
    cache_key = (base_dir, size, bold)
    if cache_key in _cache:
        return _cache[cache_key]

    font_path = os.path.join(base_dir, "resources", "font", "Bildungswirkung-Regular.otf")

    try:
        font = pygame.font.Font(font_path, size)
        # У кастомного .otf нет отдельного bold-начертания — эмулируем через SDL
        if bold:
            font.set_bold(True)
    except Exception as e:
        print(f"[VIBEMP3] Не удалось загрузить шрифт ({font_path}): {e}")
        font = pygame.font.SysFont("Arial", size, bold=bold)

    _cache[cache_key] = font
    return font
