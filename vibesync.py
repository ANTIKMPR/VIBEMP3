"""
VIBE-SYNC — технология "музыкальных пакетов", которые подстраивают интерфейс
плеера под конкретный трек: временная цветовая тема, фон (обложка с
параллаксом или зацикленное видео) и, если видео есть, маленькая обложка
рядом с названием трека.

Формат пакета — обычный .zip со строго заданной структурой:

    (music_name).zip
    ├── resources/
    │   ├── (обложка альбома).png / .webp / .jpg   — опционально
    │   └── (видео для фона).mp4                    — опционально
    ├── (трек).mp3 / .ogg
    └── sync.json

sync.json — необязательный файл; если его нет, пакет всё равно работает
(просто без временной темы, только с обложкой/видео из resources/).
Формат sync.json:

    {
      "theme": {
        "bg": [20, 10, 30],
        "accent": [255, 80, 180],
        "text": [240, 240, 245]
      }
    }

Каждый цвет — необязателен по отдельности; недостающие берутся из обычной
активной темы пользователя (так пакет может переопределить только акцент,
например, не трогая фон).

Распаковка происходит один раз в кэш-папку (vibesync_cache/<hash>/) рядом
с приложением — повторное открытие того же .zip не распаковывает его снова
(проверяется по хэшу содержимого файла).
"""

import hashlib
import json
import os
import shutil
import zipfile


SYNC_MANIFEST_NAME = "sync.json"
RESOURCES_DIR_NAME = "resources"
AUDIO_EXTENSIONS = (".mp3", ".ogg")
IMAGE_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")
VIDEO_EXTENSIONS = (".mp4",)

THEME_COLOR_KEYS = ("bg", "accent", "text")


class VibeSyncPackageError(Exception):
    """Пакет .zip не соответствует ожидаемой структуре VIBE-SYNC."""


class VibeSyncPackage:
    """
    Распакованный VIBE-SYNC пакет: путь к аудиофайлу, опциональные путь к
    картинке обложки, путь к видео фона, словарь с переопределениями цветов
    темы (может быть пустым, если sync.json нет или он не задаёт цвета), и
    список моментов "ударов камеры" (секунды в треке, на которых экран
    должен тряхнуть/дёрнуть — привязано к битам под BPM или задано вручную).
    """

    def __init__(self, zip_path: str, extracted_dir: str,
                 audio_path: str, image_path: str | None,
                 video_path: str | None, theme_overrides: dict,
                 camera_hits: list[float], bgvideo_sync: bool = False):
        self.zip_path = zip_path
        self.extracted_dir = extracted_dir
        self.audio_path = audio_path
        self.image_path = image_path
        self.video_path = video_path
        self.theme_overrides = theme_overrides  # {"bg": (r,g,b), ...} — только заданные ключи
        self.camera_hits = camera_hits           # отсортированный список секунд, напр. [0.5, 1.0, 1.5, ...]
        self.bgvideo_sync = bgvideo_sync         # True = 1 секунда трека = 1 секунда фонового видео (зацикленно по модулю длительности видео)

    @property
    def has_video(self) -> bool:
        return self.video_path is not None

    @property
    def has_image(self) -> bool:
        return self.image_path is not None

    @property
    def has_theme_override(self) -> bool:
        return bool(self.theme_overrides)

    @property
    def has_camera_hits(self) -> bool:
        return bool(self.camera_hits)


def _cache_dir(base_dir: str) -> str:
    path = os.path.join(base_dir, "vibesync_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _file_hash(zip_path: str) -> str:
    """
    Короткий хэш содержимого zip-файла (не только имени) — используется как
    имя кэш-папки, чтобы: (а) один и тот же .zip не распаковывался повторно,
    (б) изменённый файл под тем же именем не подхватил стухший кэш.
    """
    hasher = hashlib.sha1()
    with open(zip_path, "rb") as f:
        # Читаем крупными кусками, а не весь файл в память — .zip с видео
        # внутри может быть увесистым.
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def _parse_theme_overrides(sync_data: dict) -> dict:
    """Достаёт и валидирует цвета из sync.json -> theme. Некорректные/неполные
    записи тихо пропускаются (не роняют загрузку всего пакета)."""
    theme_data = sync_data.get("theme")
    if not isinstance(theme_data, dict):
        return {}

    overrides = {}
    for key in THEME_COLOR_KEYS:
        value = theme_data.get(key)
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            continue
        try:
            r, g, b = (max(0, min(255, int(c))) for c in value)
            overrides[key] = (r, g, b)
        except (ValueError, TypeError):
            continue

    return overrides


MAX_CAMERA_HITS = 20000  # защита от абсурдно большого bpm/duration, чтобы не заспамить память


def _parse_camera_hits(sync_data: dict, duration_sec: float | None) -> list[float]:
    """
    Достаёт удары камеры из sync.json. Два способа задать их, по приоритету:

    1) Явный список секунд — "camera_hits": [0.5, 1.0, 2.25, ...] —
       используется как есть, если присутствует и это непустой список чисел.

    2) Авто-генерация по BPM — "bpm": 128 (+ опционально "bpm_offset_sec": 0.1)
       — генерирует удар на каждую долю (60/bpm секунд), от offset_sec и до
       конца трека. Требует duration_sec (длительность трека), иначе
       (например, если она ещё не известна на момент парсинга) просто не
       генерирует ничего — камера-удары по BPM не сработают без длительности,
       но остальной пакет (тема/картинка/видео) при этом не пострадает.

    Некорректные/отсутствующие данные тихо дают пустой список — камера-удары
    полностью опциональны, их отсутствие не должно ронять загрузку пакета.
    """
    explicit = sync_data.get("camera_hits")
    if isinstance(explicit, list) and explicit:
        hits = []
        for value in explicit:
            try:
                sec = float(value)
                if sec >= 0:
                    hits.append(sec)
            except (ValueError, TypeError):
                continue
        hits.sort()
        return hits[:MAX_CAMERA_HITS]

    bpm = sync_data.get("bpm")
    if bpm is None:
        return []
    try:
        bpm = float(bpm)
    except (ValueError, TypeError):
        return []
    if bpm <= 0 or duration_sec is None or duration_sec <= 0:
        return []

    try:
        offset_sec = float(sync_data.get("bpm_offset_sec", 0.0))
    except (ValueError, TypeError):
        offset_sec = 0.0
    offset_sec = max(0.0, offset_sec)

    beat_interval = 60.0 / bpm
    hits = []
    t = offset_sec
    while t <= duration_sec and len(hits) < MAX_CAMERA_HITS:
        hits.append(round(t, 3))
        t += beat_interval

    return hits


def load_package(zip_path: str, base_dir: str) -> VibeSyncPackage:
    """
    Распаковывает (или переиспользует уже распакованный) .zip и возвращает
    VibeSyncPackage. Бросает VibeSyncPackageError с понятным сообщением,
    если структура пакета не соответствует ожидаемой (нет аудиофайла и т.п.)
    — вызывающий код (GUI) должен показать это пользователю, а не падать.
    """
    if not os.path.isfile(zip_path):
        raise VibeSyncPackageError(f"Файл не найден: {zip_path}")

    try:
        package_hash = _file_hash(zip_path)
    except OSError as e:
        raise VibeSyncPackageError(f"Не удалось прочитать файл: {e}") from e

    extracted_dir = os.path.join(_cache_dir(base_dir), package_hash)

    if not os.path.isdir(extracted_dir):
        _extract_package(zip_path, extracted_dir)

    return _build_package_from_dir(zip_path, extracted_dir)


def _extract_package(zip_path: str, extracted_dir: str):
    """Распаковывает zip во временную папку, затем атомарно переименовывает
    в финальную — так параллельный/повторный запуск не увидит наполовину
    распакованный кэш."""
    tmp_dir = extracted_dir + ".tmp"
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Защита от zip-slip (файлы с ../../ в имени, пытающиеся выйти
            # за пределы папки распаковки) — extractall сам по себе в
            # современных версиях Python уже фильтрует такие пути, но
            # проверяем явно для дополнительной надёжности.
            for member in zf.namelist():
                normalized = os.path.normpath(member)
                if normalized.startswith("..") or os.path.isabs(normalized):
                    raise VibeSyncPackageError(f"Небезопасный путь внутри архива: {member}")
            zf.extractall(tmp_dir)
    except zipfile.BadZipFile as e:
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise VibeSyncPackageError(f"Файл повреждён или это не .zip: {e}") from e

    os.replace(tmp_dir, extracted_dir)


def _build_package_from_dir(zip_path: str, extracted_dir: str) -> VibeSyncPackage:
    """Ищет ожидаемые файлы (аудио, sync.json, resources/картинка+видео)
    внутри уже распакованной папки и собирает VibeSyncPackage."""

    # Некоторые zip-архиваторы кладут всё в одну вложенную папку с именем
    # архива — если верхний уровень содержит ровно одну папку и больше
    # ничего, "спускаемся" в неё, чтобы структура совпадала с ожидаемой
    # независимо от того, как именно был собран .zip.
    root = extracted_dir
    top_level = os.listdir(root)
    if len(top_level) == 1 and os.path.isdir(os.path.join(root, top_level[0])):
        root = os.path.join(root, top_level[0])

    audio_path = None
    for entry in os.listdir(root):
        full_path = os.path.join(root, entry)
        if os.path.isfile(full_path) and entry.lower().endswith(AUDIO_EXTENSIONS):
            audio_path = full_path
            break

    if audio_path is None:
        raise VibeSyncPackageError(
            "В пакете не найден аудиофайл (.mp3/.ogg) в корне архива."
        )

    theme_overrides = {}
    camera_hits = []
    bgvideo_sync = False
    sync_json_path = os.path.join(root, SYNC_MANIFEST_NAME)
    if os.path.isfile(sync_json_path):
        try:
            with open(sync_json_path, "r", encoding="utf-8") as f:
                sync_data = json.load(f)
            theme_overrides = _parse_theme_overrides(sync_data)
            camera_hits = _parse_camera_hits(sync_data, _quick_duration_sec(audio_path))
            bgvideo_sync = _parse_bgvideo_sync(sync_data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[VIBEMP3] Не удалось прочитать sync.json ({sync_json_path}): {e}")

    image_path = None
    video_path = None
    resources_dir = os.path.join(root, RESOURCES_DIR_NAME)
    if os.path.isdir(resources_dir):
        for entry in sorted(os.listdir(resources_dir)):
            full_path = os.path.join(resources_dir, entry)
            if not os.path.isfile(full_path):
                continue
            lower = entry.lower()
            if video_path is None and lower.endswith(VIDEO_EXTENSIONS):
                video_path = full_path
            elif image_path is None and lower.endswith(IMAGE_EXTENSIONS):
                image_path = full_path

    return VibeSyncPackage(
        zip_path=zip_path,
        extracted_dir=root,
        audio_path=audio_path,
        image_path=image_path,
        video_path=video_path,
        theme_overrides=theme_overrides,
        camera_hits=camera_hits,
        bgvideo_sync=bgvideo_sync,
    )


def _parse_bgvideo_sync(sync_data: dict) -> bool:
    """
    Читает флаг синхронизации фонового видео с позицией трека. Принимает
    несколько разумных вариантов имени ключа в sync.json, на случай если
    формат ещё устаканивается: "bgvideo_sync", "bg_video_sync", "bgvideo.sync".
    Значение может быть true/false, "true"/"false" или 1/0 — не роняем
    загрузку пакета из-за строгости типов в самодельном JSON.
    """
    for key in ("bgvideo_sync", "bg_video_sync", "bgvideo.sync"):
        if key in sync_data:
            value = sync_data[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes")
            if isinstance(value, (int, float)):
                return bool(value)
    return False


def _quick_duration_sec(audio_path: str) -> float | None:
    """
    Быстро читает длительность трека через mutagen (без полной PCM-
    декодировки через pydub, которая происходит только позже, когда трек
    реально начинает играть) — нужна только чтобы посчитать удары камеры
    по BPM на весь трек. Если mutagen недоступен или не смог прочитать —
    возвращает None (авто-генерация по BPM тогда просто не сработает, но
    explicit camera_hits из sync.json продолжат работать).
    """
    try:
        from mutagen import File as mutagen_File
        audio = mutagen_File(audio_path)
        if audio is not None and audio.info is not None:
            return float(audio.info.length)
    except Exception:
        pass
    return None


def is_vibesync_package(filepath: str) -> bool:
    """Быстрая проверка по расширению — используется, чтобы решить, вести
    ли файл через обычную загрузку трека или через load_package()."""
    return filepath.lower().endswith(".zip")
