"""
Генерация светлой версии логотипа из тёмной (BigLogo.png) на лету.

Идея: НЕ инвертируем RGB целиком (это ломает цветные акценты — например,
фиолетовый превратится в жёлто-зелёный). Вместо этого инвертируем только
яркость (luminance), сохраняя цветовой тон и прозрачность:
  - белые/светлые пиксели (обычно текст/линии лого на тёмном фоне) -> тёмные
  - альфа-канал не трогаем, так что прозрачность остаётся как есть

Результат кэшируется на диск (BigLogo.light.png) рядом с оригиналом,
чтобы не пересчитывать каждый запуск.
"""

import os
from PIL import Image, ImageOps


def get_logo_path_for_theme(dark_logo_path: str, theme: str) -> str:
    """
    Возвращает путь к логотипу для указанной темы ('dark' или 'light').
    Для 'light' — генерирует (если ещё не сгенерирован) и кэширует light-версию.
    Если что-то пошло не так (нет исходника, ошибка PIL) — возвращает
    исходный dark_logo_path как безопасный фолбэк.
    """
    if theme != "light":
        return dark_logo_path

    base, ext = os.path.splitext(dark_logo_path)
    light_path = f"{base}.light{ext}"

    if os.path.isfile(light_path):
        return light_path

    if not os.path.isfile(dark_logo_path):
        return dark_logo_path

    try:
        _generate_light_logo(dark_logo_path, light_path)
        return light_path
    except Exception as e:
        print(f"[VIBEMP3] Не удалось сгенерировать светлое лого: {e}")
        return dark_logo_path


def _generate_light_logo(src_path: str, dst_path: str):
    img = Image.open(src_path).convert("RGBA")
    r, g, b, a = img.split()

    rgb = Image.merge("RGB", (r, g, b))
    inverted_rgb = ImageOps.invert(rgb)

    result = Image.merge("RGBA", (*inverted_rgb.split(), a))
    result.save(dst_path)
