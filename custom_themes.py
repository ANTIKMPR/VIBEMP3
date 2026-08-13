"""
Пользовательские темы VIBEMP3 (.vibetheme).

Формат файла — простой текст в стиле key=value (по сути INI без секций),
человекочитаемый и легко правится вручную в блокноте:

    # Комментарии начинаются с "#"
    name = Моя тема
    bg = 20,20,24
    panel = 30,30,34
    text = 235,235,240
    text_dim = 145,145,150
    accent = 255,100,180
    progress_bg = 50,50,56
    progress_fill = 255,100,180
    button_small_bg = 40,40,46
    button_small_border = 60,60,68
    row_current = 70,35,55
    row_hover = 36,36,42
    error = 200,60,60
    success = 60,160,90
    remove_x = 220,90,90

Каждый цвет — три числа 0-255 через запятую (R,G,B). Все ключи из
settings.THEMES["dark"] обязательны — если каких-то не хватает, отсутствующие
берутся из тёмной темы по умолчанию (тема всё равно загрузится, просто
недостающие элементы будут выглядеть как в тёмной теме).

Файлы хранятся в themes/ рядом с приложением, один файл — одна тема.
Имя файла (без расширения) используется как идентификатор темы в
settings.theme, например "Моя тема.vibetheme" -> theme = "custom:Моя тема".
Префикс "custom:" отличает пользовательские темы от встроенных ("dark"/
"light"/"system") без риска коллизии имён.
"""

import os
import re


THEME_FILE_EXT = ".vibetheme"
CUSTOM_THEME_PREFIX = "custom:"

REQUIRED_KEYS = (
    "bg", "panel", "text", "text_dim", "accent",
    "progress_bg", "progress_fill", "button_small_bg", "button_small_border",
    "row_current", "row_hover", "error", "success", "remove_x", "viz_wave",
)

_NAME_SAFE_RE = re.compile(r'[\\/:*?"<>|]')


def get_themes_dir(base_dir: str) -> str:
    path = os.path.join(base_dir, "themes")
    os.makedirs(path, exist_ok=True)
    return path


def is_custom_theme_id(theme_id: str) -> bool:
    return theme_id.startswith(CUSTOM_THEME_PREFIX)


def custom_theme_display_name(theme_id: str) -> str:
    """custom:Моя тема -> Моя тема"""
    return theme_id[len(CUSTOM_THEME_PREFIX):] if is_custom_theme_id(theme_id) else theme_id


def make_theme_id(display_name: str) -> str:
    return f"{CUSTOM_THEME_PREFIX}{display_name}"


def sanitize_filename(display_name: str) -> str:
    """Убирает символы, недопустимые в именах файлов Windows, из имени темы."""
    cleaned = _NAME_SAFE_RE.sub("_", display_name).strip()
    return cleaned or "Тема"


def _parse_color(value: str) -> tuple[int, int, int] | None:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 3:
        return None
    try:
        r, g, b = (max(0, min(255, int(p))) for p in parts)
        return (r, g, b)
    except ValueError:
        return None


def _format_color(color: tuple[int, int, int]) -> str:
    return f"{color[0]},{color[1]},{color[2]}"


def parse_vibetheme(text: str, fallback_palette: dict) -> tuple[str, dict]:
    """
    Парсит содержимое .vibetheme файла. Возвращает (display_name, palette).
    Недостающие или некорректные цвета подставляются из fallback_palette
    (обычно settings.THEMES["dark"]), чтобы битый/неполный файл темы не
    ронял приложение, а просто давал неполную кастомизацию.
    """
    display_name = "Без названия"
    palette = dict(fallback_palette)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()

        if key == "name":
            display_name = value or display_name
            continue

        if key in REQUIRED_KEYS:
            color = _parse_color(value)
            if color is not None:
                palette[key] = color

    return display_name, palette


def format_vibetheme(display_name: str, palette: dict) -> str:
    """Сериализует тему в текст .vibetheme файла."""
    lines = [
        "# Тема VIBEMP3 — можно редактировать вручную",
        f"name = {display_name}",
        "",
    ]
    for key in REQUIRED_KEYS:
        color = palette.get(key, (0, 0, 0))
        lines.append(f"{key} = {_format_color(color)}")
    return "\n".join(lines) + "\n"


def save_custom_theme(base_dir: str, display_name: str, palette: dict) -> str:
    """
    Сохраняет тему в themes/<имя>.vibetheme. Возвращает theme_id
    ("custom:<имя>") для использования в Settings.theme.
    """
    themes_dir = get_themes_dir(base_dir)
    safe_name = sanitize_filename(display_name)
    path = os.path.join(themes_dir, f"{safe_name}{THEME_FILE_EXT}")

    content = format_vibetheme(display_name, palette)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return make_theme_id(display_name)


def load_custom_theme(base_dir: str, display_name: str, fallback_palette: dict) -> dict | None:
    """Загружает палитру пользовательской темы по её отображаемому имени. None, если файл не найден."""
    themes_dir = get_themes_dir(base_dir)
    safe_name = sanitize_filename(display_name)
    path = os.path.join(themes_dir, f"{safe_name}{THEME_FILE_EXT}")

    if not os.path.isfile(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"[VIBEMP3] Не удалось прочитать тему ({path}): {e}")
        return None

    _, palette = parse_vibetheme(text, fallback_palette)
    return palette


def list_custom_themes(base_dir: str) -> list[str]:
    """Возвращает список отображаемых имён всех .vibetheme файлов в themes/."""
    themes_dir = get_themes_dir(base_dir)
    names = []
    try:
        for filename in sorted(os.listdir(themes_dir)):
            if filename.endswith(THEME_FILE_EXT):
                names.append(filename[: -len(THEME_FILE_EXT)])
    except OSError:
        pass
    return names


def delete_custom_theme(base_dir: str, display_name: str) -> bool:
    """Удаляет файл темы. Возвращает True, если файл существовал и был удалён."""
    themes_dir = get_themes_dir(base_dir)
    safe_name = sanitize_filename(display_name)
    path = os.path.join(themes_dir, f"{safe_name}{THEME_FILE_EXT}")
    if os.path.isfile(path):
        try:
            os.remove(path)
            return True
        except OSError as e:
            print(f"[VIBEMP3] Не удалось удалить тему ({path}): {e}")
    return False
