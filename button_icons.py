"""
Загрузка PNG-иконок для транспортных кнопок (play/pause/prev/next), а также
иконки кнопки настроек (webp).

Файлы лежат в resources/ui/ в двух вариантах на каждую иконку — белая
версия для тёмной темы, чёрная для светлой (имя файла оканчивается на
_white / _black). Кнопка "предыдущий трек" использует next_button_*.png
как есть (стрелка смотрит влево), а "следующий трек" — тот же файл,
отзеркаленный по горизонтали кодом (rotate/flip), т.к. отдельного
prev_button-файла нет.

Если каких-то файлов не найдено — get_icon()/get_settings_icon() возвращают
None, и вызывающий код (main.py) должен откатиться на текстовый/шрифтовой
символ, чтобы кнопка всё равно была видна и рабоча.

.webp читаем через Pillow (а не pygame.image.load напрямую) — не все сборки
SDL_image, с которыми может быть установлен pygame на компьютере пользователя,
умеют webp "из коробки", а Pillow эту зависимость снимает.
"""

import os
import pygame

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


ICON_NAMES = {
    "play": "pause_button",
    "pause": "play_button",
    "prev": "next_button",  # как есть, стрелка уже смотрит влево
    "next": "next_button",  # тот же файл, но отзеркаленный при загрузке
}

# Возможные варианты имени файла иконки настроек — на диске оно пришло с
# пробелом ("settings white.webp"), но поддержим и вариант с подчёркиванием
# на случай, если файл потом переименуют для единообразия с остальными.
SETTINGS_ICON_NAME_CANDIDATES = {
    "white": ["settings white.webp", "settings_white.webp"],
    "black": ["settings black.webp", "settings_black.webp"],
}

_cache: dict[tuple, pygame.Surface | None] = {}


def _theme_suffix(effective_theme: str) -> str:
    # white-иконки читаются на тёмном фоне, black — на светлом
    return "white" if effective_theme == "dark" else "black"


def _load_image_any_format(path: str) -> pygame.Surface:
    """
    Грузит изображение (png/webp/что угодно поддерживаемое) в pygame Surface.
    Пробует pygame.image.load напрямую (быстрее, работает для png/jpg всегда
    и для webp — если SDL_image собран с поддержкой). Если не вышло и есть
    Pillow — конвертирует через него как более надёжный фолбэк для webp.
    """
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception as direct_error:
        if not _PIL_AVAILABLE:
            raise
        pil_img = Image.open(path).convert("RGBA")
        mode = pil_img.mode
        size = pil_img.size
        data = pil_img.tobytes()
        return pygame.image.fromstring(data, size, mode).convert_alpha()


def get_icon(base_dir: str, action: str, effective_theme: str, size: int) -> pygame.Surface | None:
    """
    Возвращает Surface с иконкой нужного действия ('play'/'pause'/'prev'/'next'),
    под нужную тему, отмасштабированную под size x size. None, если файла нет
    на диске или его не удалось загрузить — тогда вызывающий код должен
    показать текстовый фолбэк вместо иконки.
    """
    cache_key = ("transport", base_dir, action, effective_theme, size)
    if cache_key in _cache:
        return _cache[cache_key]

    base_name = ICON_NAMES.get(action)
    if base_name is None:
        _cache[cache_key] = None
        return None

    suffix = _theme_suffix(effective_theme)
    path = os.path.join(base_dir, "resources", "ui", f"{base_name}_{suffix}.png")

    try:
        raw = _load_image_any_format(path)
        scaled = pygame.transform.smoothscale(raw, (size, size))
        if action == "next":
            # next_button_*.png смотрит влево — для "следующего трека" отражаем по горизонтали
            scaled = pygame.transform.flip(scaled, True, False)
        result = scaled
    except Exception as e:
        print(f"[VIBEMP3] Не удалось загрузить иконку кнопки ({path}): {e}")
        result = None

    _cache[cache_key] = result
    return result


def get_settings_icon(base_dir: str, effective_theme: str, size: int) -> pygame.Surface | None:
    """
    Возвращает Surface с иконкой шестерёнки настроек под нужную тему,
    отмасштабированную под size x size. None при отсутствии файла —
    вызывающий код должен откатиться на текстовый символ "⚙".
    """
    cache_key = ("settings", base_dir, effective_theme, size)
    if cache_key in _cache:
        return _cache[cache_key]

    suffix = _theme_suffix(effective_theme)
    candidates = SETTINGS_ICON_NAME_CANDIDATES[suffix]

    result = None
    last_error = None
    for filename in candidates:
        path = os.path.join(base_dir, "resources", "ui", filename)
        if not os.path.isfile(path):
            continue
        try:
            raw = _load_image_any_format(path)
            result = pygame.transform.smoothscale(raw, (size, size))
            break
        except Exception as e:
            last_error = (path, e)

    if result is None and last_error is not None:
        path, e = last_error
        print(f"[VIBEMP3] Не удалось загрузить иконку настроек ({path}): {e}")

    _cache[cache_key] = result
    return result


def get_named_icon(base_dir: str, base_filename: str, effective_theme: str, size: int) -> pygame.Surface | None:
    """
    Общая загрузка иконки по базовому имени файла (без темы/расширения),
    например 'idk_how_to_call_it' -> ищет idk_how_to_call_it_white.png или
    .webp для тёмной темы, idk_how_to_call_it_black.* для светлой.
    Используется для иконок вроде стрелки выпадающего списка. None при
    отсутствии файла — вызывающий код откатывается на текстовый символ.
    """
    suffix = _theme_suffix(effective_theme)
    cache_key = ("named", base_dir, base_filename, effective_theme, size)
    if cache_key in _cache:
        return _cache[cache_key]

    result = None
    last_error = None
    for ext in (".png", ".webp"):
        path = os.path.join(base_dir, "resources", "ui", f"{base_filename}_{suffix}{ext}")
        if not os.path.isfile(path):
            continue
        try:
            raw = _load_image_any_format(path)
            result = pygame.transform.smoothscale(raw, (size, size))
            break
        except Exception as e:
            last_error = (path, e)

    if result is None and last_error is not None:
        path, e = last_error
        print(f"[VIBEMP3] Не удалось загрузить иконку ({path}): {e}")

    _cache[cache_key] = result
    return result
