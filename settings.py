"""
Настройки приложения: язык, тема (light/dark), время кроссфейда между треками.

Хранятся в JSON рядом с приложением (settings.json). Модуль также содержит
словари переводов и цветовые палитры тем — остальной код обращается к ним
через Settings, а не хардкодит цвета/строки.
"""

import json
import os
import sys

import custom_themes


# Тот же принцип, что и в main.py: в PyInstaller-сборке __file__ указывает
# во временную распакованную папку, а не туда, где реально лежит exe.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

DEFAULT_LANGUAGE = "ru"
DEFAULT_THEME = "dark"
DEFAULT_CROSSFADE_SEC = 3
DEFAULT_VOLUME = 0.7

MIN_CROSSFADE_SEC = 1
MAX_CROSSFADE_SEC = 10

# "system" — специальное значение темы: приложение отслеживает системную
# тему Windows (светлая/тёмная) и подстраивается под неё автоматически.
THEME_OPTIONS = ("dark", "light", "system")


# ---------- Переводы ----------

TRANSLATIONS = {
    "ru": {
        "add_folder": "+ Папка",
        "add_files": "+ Файлы",
        "clear": "Очистить",
        "settings": "Настройки",
        "settings_title": "Настройки",
        "language": "Язык",
        "theme": "Тема",
        "theme_dark": "Тёмная",
        "theme_light": "Светлая",
        "theme_system": "Как в Windows",
        "crossfade": "Плавный переход между треками",
        "seconds_short": "с",
        "close": "Закрыть",
        "no_track": "Нет трека — добавь музыку кнопками сверху",
        "playlist_empty": "Плейлист пуст — добавь треки кнопками сверху",
        "volume": "Громкость",
        "added_tracks": "Добавлено треков: {n}",
        "no_new_tracks": "В этой папке не найдено новых mp3-файлов",
        "files_already_added": "Эти файлы уже есть в плейлисте",
        "playlist_cleared": "Плейлист очищен",
        "theme_custom_prefix": "Своя: ",
        "create_theme": "Создать тему",
        "edit_theme": "Изменить",
        "delete_theme": "Удалить",
        "theme_name": "Название темы",
        "theme_created": "Тема сохранена: {name}",
        "theme_deleted": "Тема удалена",
        "theme_name_empty": "Введи название темы",
        "back": "Назад",
        "save": "Сохранить",
        "apply_theme": "Применить",
        "existing_theme": "Выбрать существующую тему",
        "viz_wave_color": "Цвет волны визуализатора",
    },
    "en": {
        "add_folder": "+ Folder",
        "add_files": "+ Files",
        "clear": "Clear",
        "settings": "Settings",
        "settings_title": "Settings",
        "language": "Language",
        "theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "theme_system": "Match Windows",
        "crossfade": "Crossfade between tracks",
        "seconds_short": "s",
        "close": "Close",
        "no_track": "No track — add music using the buttons above",
        "playlist_empty": "Playlist is empty — add tracks using the buttons above",
        "volume": "Volume",
        "added_tracks": "Tracks added: {n}",
        "no_new_tracks": "No new mp3 files found in this folder",
        "files_already_added": "These files are already in the playlist",
        "playlist_cleared": "Playlist cleared",
        "theme_custom_prefix": "Custom: ",
        "create_theme": "Create theme",
        "edit_theme": "Edit",
        "delete_theme": "Delete",
        "theme_name": "Theme name",
        "theme_created": "Theme saved: {name}",
        "theme_deleted": "Theme deleted",
        "theme_name_empty": "Enter a theme name",
        "back": "Back",
        "save": "Save",
        "apply_theme": "Apply",
        "existing_theme": "Pick an existing theme",
        "viz_wave_color": "Visualizer wave color",
    },
}


# ---------- Палитры тем ----------
# Одинаковый набор ключей для каждой темы — остальной код всегда обращается
# по ключу (theme.bg, theme.text и т.д.), никогда не хардкодит RGB напрямую.

THEMES = {
    "dark": {
        "bg": (18, 18, 20),
        "panel": (28, 28, 32),
        "text": (230, 230, 235),
        "text_dim": (140, 140, 148),
        "accent": (120, 90, 255),
        "progress_bg": (50, 50, 56),
        "progress_fill": (150, 110, 255),
        "button_small_bg": (40, 40, 46),
        "button_small_border": (60, 60, 68),
        "row_current": (45, 38, 70),
        "row_hover": (36, 36, 42),
        "error": (200, 60, 60),
        "success": (60, 160, 90),
        "remove_x": (220, 90, 90),
        "viz_wave": (180, 50, 255),
    },
    "light": {
        "bg": (245, 245, 248),
        "panel": (255, 255, 255),
        "text": (30, 30, 34),
        "text_dim": (110, 110, 118),
        "accent": (120, 90, 255),
        "progress_bg": (222, 222, 228),
        "progress_fill": (150, 110, 255),
        "button_small_bg": (232, 232, 238),
        "button_small_border": (210, 210, 218),
        "row_current": (228, 222, 250),
        "row_hover": (234, 234, 240),
        "error": (200, 60, 60),
        "success": (40, 130, 70),
        "remove_x": (200, 70, 70),
        "viz_wave": (180, 50, 255),
    },
}


def get_windows_system_theme() -> str:
    """
    Определяет текущую тему оформления Windows ('dark' или 'light') через реестр.
    На не-Windows системах (или при любой ошибке чтения реестра) возвращает
    DEFAULT_THEME как безопасный фолбэк.

    Windows хранит выбор темы приложений в разделе Personalize:
      AppsUseLightTheme = 0 -> тёмная тема, 1 -> светлая тема
    """
    if os.name != "nt":
        return DEFAULT_THEME

    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value else "dark"
    except Exception:
        return DEFAULT_THEME


class Settings:
    """Текущие настройки приложения + (де)сериализация в JSON."""

    def __init__(self, base_dir: str = BASE_DIR):
        self.language = DEFAULT_LANGUAGE
        self.theme = DEFAULT_THEME
        self.crossfade_sec = DEFAULT_CROSSFADE_SEC
        self.volume = DEFAULT_VOLUME
        self.repeat_mode = "off"  # "off" | "one" | "all"
        self.last_folder: str | None = None
        self.last_files: list[str] = []  # отдельные mp3, добавленные через "+ Файлы" (не через папку)
        # base_dir — папка приложения, где лежат settings.json, themes/,
        # resources/ и т.д. Передаётся явно (а не читается из __file__ этого
        # модуля), потому что при запуске из PyInstaller-exe __file__ модуля
        # указывает во временную распакованную директорию, а не туда, где
        # реально лежит exe и должны сохраняться пользовательские файлы.
        self._base_dir = base_dir

    # ---------- Доступ к переводу/теме ----------

    def t(self, key: str, **kwargs) -> str:
        """Возвращает переведённую строку по ключу для текущего языка (с фолбэком на ru)."""
        table = TRANSLATIONS.get(self.language, TRANSLATIONS[DEFAULT_LANGUAGE])
        text = table.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
        return text.format(**kwargs) if kwargs else text

    def effective_theme(self) -> str:
        """
        Возвращает реально применяемую БАЗОВУЮ тему ('dark'/'light') — то есть
        то, под какую версию иконок/лого нужно подстраиваться. Для 'system'
        подставляет текущую тему Windows. Для кастомных тем ('custom:...')
        определяет "тёмная она или светлая" по фактической яркости фона
        (bg) самой темы — иначе, например, светлая кастомная тема получила
        бы белые (для тёмной темы) транспортные кнопки, которые на светлом
        фоне почти не видно.
        """
        if self.theme == "system":
            return get_windows_system_theme()
        if custom_themes.is_custom_theme_id(self.theme):
            bg = self.palette().get("bg", THEMES[DEFAULT_THEME]["bg"])
            return "light" if sum(bg) >= 384 else "dark"
        return self.theme

    def palette(self) -> dict:
        """
        Возвращает словарь цветов текущей темы. Для кастомных тем читает
        .vibetheme файл с диска; если файл пропал — тихо откатывается на
        тёмную тему по умолчанию, чтобы приложение не падало.
        """
        if custom_themes.is_custom_theme_id(self.theme):
            display_name = custom_themes.custom_theme_display_name(self.theme)
            palette = custom_themes.load_custom_theme(self._base_dir, display_name, THEMES[DEFAULT_THEME])
            if palette is not None:
                return palette
            return THEMES[DEFAULT_THEME]
        return THEMES.get(self.effective_theme(), THEMES[DEFAULT_THEME])

    # ---------- Мутаторы (с валидацией) ----------

    def set_language(self, language: str):
        if language in TRANSLATIONS:
            self.language = language

    def set_theme(self, theme: str):
        if theme in THEME_OPTIONS or custom_themes.is_custom_theme_id(theme):
            self.theme = theme

    def set_crossfade_sec(self, seconds: float):
        self.crossfade_sec = max(MIN_CROSSFADE_SEC, min(MAX_CROSSFADE_SEC, seconds))

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))

    def set_repeat_mode(self, mode: str):
        if mode in ("off", "one", "all"):
            self.repeat_mode = mode

    def set_last_folder(self, folder_path: str | None):
        self.last_folder = folder_path

    def set_last_files(self, filepaths: list[str]):
        self.last_files = list(filepaths)

    # ---------- Персистентность ----------

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "theme": self.theme,
            "crossfade_sec": self.crossfade_sec,
            "volume": self.volume,
            "repeat_mode": self.repeat_mode,
            "last_folder": self.last_folder,
            "last_files": self.last_files,
        }

    def load_from_dict(self, data: dict):
        self.set_language(data.get("language", self.language))
        self.set_theme(data.get("theme", self.theme))
        self.set_crossfade_sec(data.get("crossfade_sec", self.crossfade_sec))
        self.set_volume(data.get("volume", self.volume))
        self.set_repeat_mode(data.get("repeat_mode", self.repeat_mode))
        self.set_last_folder(data.get("last_folder", self.last_folder))
        self.set_last_files(data.get("last_files", self.last_files))

    def save(self, path: str | None = None):
        path = path or os.path.join(self._base_dir, "settings.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[VIBEMP3] Не удалось сохранить настройки ({path}): {e}")

    def load(self, path: str | None = None):
        path = path or os.path.join(self._base_dir, "settings.json")
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.load_from_dict(data)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[VIBEMP3] Не удалось загрузить настройки ({path}): {e}")
