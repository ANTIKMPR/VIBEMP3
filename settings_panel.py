"""
Панель настроек как оверлей поверх основного окна плеера.

В отличие от предыдущей версии (отдельное pygame-окно), этот компонент
рисуется прямо в существующем окне плеера — затемняющая подложка + карточка
с элементами управления. Плеер (визуализатор, воспроизведение) продолжает
жить и обновляться на заднем плане, просто закрыт панелью визуально.

Также отсюда управляется плавный переход цветовой темы: SettingsPanel не
хранит состояние анимации сам — за это отвечает ThemeTransition (см. ниже),
который лежит в main.py и лерпит палитру между старой и новой темой.
"""

import pygame

import ui
import app_font
import button_icons
import custom_themes
from settings import Settings, MIN_CROSSFADE_SEC, MAX_CROSSFADE_SEC, THEME_OPTIONS


def _clamp_channel(v: float) -> int:
    return max(0, min(255, int(v)))


def _mix(c1, c2, t):
    return tuple(_clamp_channel(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def derive_palette_from_basics(bg: tuple, accent: tuple, text: tuple, viz_wave: tuple | None = None) -> dict:
    """
    Строит полную палитру темы (все ключи из custom_themes.REQUIRED_KEYS) на
    основе трёх обязательных цветов, выбранных пользователем: фон, акцент,
    текст. Остальные цвета (кроме viz_wave) выводятся как осветлённые/
    затемнённые/смешанные производные — так пользователю не нужно вручную
    подбирать все цвета темы, а результат всё равно выглядит согласованным.

    viz_wave (цвет "пули"/волны визуализатора в момент тишины) — отдельный,
    независимо настраиваемый цвет, не выводится из bg/accent/text; если не
    передан, по умолчанию берётся тот же, что у accent.
    """
    is_dark_bg = sum(bg) < 384  # эвристика: тёмный фон -> "тёмная" производная логика

    if is_dark_bg:
        panel = _mix(bg, (255, 255, 255), 0.08)
        text_dim = _mix(text, bg, 0.45)
        progress_bg = _mix(bg, (255, 255, 255), 0.15)
        button_small_bg = _mix(bg, (255, 255, 255), 0.10)
        button_small_border = _mix(bg, (255, 255, 255), 0.20)
        row_hover = _mix(bg, (255, 255, 255), 0.08)
    else:
        panel = _mix(bg, (255, 255, 255), 0.5)
        text_dim = _mix(text, bg, 0.4)
        progress_bg = _mix(bg, (0, 0, 0), 0.10)
        button_small_bg = _mix(bg, (0, 0, 0), 0.06)
        button_small_border = _mix(bg, (0, 0, 0), 0.14)
        row_hover = _mix(bg, (0, 0, 0), 0.05)

    row_current = _mix(bg, accent, 0.25)

    return {
        "bg": bg,
        "panel": panel,
        "text": text,
        "text_dim": text_dim,
        "accent": accent,
        "progress_bg": progress_bg,
        "progress_fill": accent,
        "button_small_bg": button_small_bg,
        "button_small_border": button_small_border,
        "row_current": row_current,
        "row_hover": row_hover,
        "error": (200, 60, 60),
        "success": (60, 160, 90) if is_dark_bg else (40, 130, 70),
        "remove_x": (220, 90, 90) if is_dark_bg else (200, 70, 70),
        "viz_wave": viz_wave if viz_wave is not None else accent,
    }


def _color_to_hex(color) -> str:
    return "#{:02X}{:02X}{:02X}".format(*color)


def _hex_to_color(text: str) -> tuple | None:
    """Парсит '#RRGGBB' или 'RRGGBB' (регистр не важен). None, если не похоже на hex-цвет."""
    cleaned = text.strip().lstrip("#")
    if len(cleaned) != 6:
        return None
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


class _RGBSlider:
    """Три горизонтальных слайдера (R/G/B) для одного цвета, со свотчем-превью
    и hex-полем ввода (#RRGGBB) для точной настройки без мышки."""

    def __init__(self, rect: pygame.Rect, initial_color: tuple):
        self.color = list(initial_color)
        self.rect = rect  # общая область компонента (свотч + слайдеры + hex-поле)
        self._channel_sliders = []
        self._dragging_channel = None
        self.hex_input = _TextInput(pygame.Rect(0, 0, 10, 10), _color_to_hex(initial_color), max_length=7)
        self._layout()
        self._sync_hex_from_color()

    def _layout(self):
        swatch_w = 36
        gap = 10
        hex_w = 84
        sliders_x = self.rect.x + swatch_w + gap
        sliders_w = self.rect.width - swatch_w - gap * 2 - hex_w
        channel_h = 6
        channel_gap = 6
        self.swatch_rect = pygame.Rect(self.rect.x, self.rect.y, swatch_w, self.rect.height)
        self._channel_sliders = []
        for i in range(3):
            y = self.rect.y + i * (channel_h + channel_gap) + 3
            self._channel_sliders.append(pygame.Rect(sliders_x, y, sliders_w, channel_h))
        self.hex_input.rect = pygame.Rect(sliders_x + sliders_w + gap, self.rect.y, hex_w, self.rect.height)

    def move_to(self, x, y):
        self.rect.x, self.rect.y = x, y
        self._layout()

    def _sync_hex_from_color(self):
        if not self.hex_input.active:  # не перезаписываем, пока пользователь печатает
            self.hex_input.text = _color_to_hex(tuple(self.color))

    def handle_event(self, mouse_pos, event) -> bool:
        if self.hex_input.handle_event(mouse_pos, event):
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._apply_hex_input()
            return True

        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB and self.hex_input.active:
            self._apply_hex_input()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, ch_rect in enumerate(self._channel_sliders):
                hit = pygame.Rect(ch_rect.x - 6, ch_rect.y - 6, ch_rect.width + 12, ch_rect.height + 12)
                if hit.collidepoint(mouse_pos):
                    self._dragging_channel = i
                    self._update_channel_from_x(i, mouse_pos[0])
                    self._sync_hex_from_color()
                    return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging_channel is not None:
                self._dragging_channel = None
                return True
        return False

    def _apply_hex_input(self):
        """Валидирует и применяет введённый hex-текст. При некорректном вводе
        просто откатывает поле обратно к текущему цвету — не роняет UI."""
        parsed = _hex_to_color(self.hex_input.text)
        if parsed is not None:
            self.color = list(parsed)
        self.hex_input.active = False
        self._sync_hex_from_color()

    def update_drag(self, mouse_pos):
        if self._dragging_channel is not None:
            self._update_channel_from_x(self._dragging_channel, mouse_pos[0])
            self._sync_hex_from_color()

    def _update_channel_from_x(self, channel_idx, mouse_x):
        ch_rect = self._channel_sliders[channel_idx]
        ratio = max(0.0, min(1.0, (mouse_x - ch_rect.x) / ch_rect.width))
        self.color[channel_idx] = round(ratio * 255)

    def draw(self, surface, palette: dict, font):
        pygame.draw.rect(surface, tuple(self.color), self.swatch_rect, border_radius=6)
        pygame.draw.rect(surface, palette["button_small_border"], self.swatch_rect, width=1, border_radius=6)

        channel_colors = [(220, 70, 70), (70, 200, 90), (80, 120, 240)]
        for i, ch_rect in enumerate(self._channel_sliders):
            pygame.draw.rect(surface, palette["progress_bg"], ch_rect, border_radius=3)
            fill_w = int(ch_rect.width * (self.color[i] / 255))
            if fill_w > 0:
                fill_rect = pygame.Rect(ch_rect.x, ch_rect.y, fill_w, ch_rect.height)
                pygame.draw.rect(surface, channel_colors[i], fill_rect, border_radius=3)

        # Если поле не в фокусе — синхронизируем текст с фактическим цветом
        # на каждый кадр (страхует от рассинхрона после drag'а слайдеров).
        if not self.hex_input.active:
            self.hex_input.text = _color_to_hex(tuple(self.color))
        self.hex_input.draw(surface, font, palette)

    def get_color(self) -> tuple:
        return tuple(self.color)


class _TextInput:
    """Однострочное текстовое поле с курсором-морганием. Активируется кликом."""

    def __init__(self, rect: pygame.Rect, initial_text: str = "", max_length: int = 40):
        self.rect = rect
        self.text = initial_text
        self.max_length = max_length
        self.active = False
        self._cursor_visible = True
        self._last_blink_ms = 0

    def handle_event(self, mouse_pos, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clicked_inside = self.rect.collidepoint(mouse_pos)
            self.active = clicked_inside
            # "Съедаем" событие только если клик попал В поле — клик снаружи
            # лишь снимает фокус, но должен долететь до остальных виджетов
            # (иначе, например, клик по цветовому слайдеру после ввода имени
            # блокировался бы полем, которое было активно секунду назад).
            return clicked_inside

        if not self.active:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            # Остальные печатные символы приходят через TEXTINPUT (см. ниже) —
            # это корректно работает с любой раскладкой клавиатуры (в т.ч. кириллицей),
            # в отличие от KEYDOWN.unicode, который не всегда надёжен на Windows.
            return True

        if event.type == pygame.TEXTINPUT:
            if len(self.text) < self.max_length:
                self.text += event.text
            return True

        return False

    def draw(self, surface, font, palette: dict, placeholder: str = ""):
        border_color = palette["accent"] if self.active else palette["button_small_border"]
        pygame.draw.rect(surface, palette["button_small_bg"], self.rect, border_radius=6)
        pygame.draw.rect(surface, border_color, self.rect, width=1, border_radius=6)

        now = pygame.time.get_ticks()
        if now - self._last_blink_ms > 500:
            self._cursor_visible = not self._cursor_visible
            self._last_blink_ms = now

        display_text = self.text if (self.text or self.active) else placeholder
        color = palette["text"] if (self.text or self.active) else palette["text_dim"]
        text_surf = font.render(display_text, True, color)
        surface.blit(text_surf, (self.rect.x + 10, self.rect.centery - text_surf.get_height() // 2))

        if self.active and self._cursor_visible:
            cursor_x = self.rect.x + 10 + font.size(self.text)[0] + 2
            pygame.draw.line(
                surface, palette["text"],
                (cursor_x, self.rect.y + 6), (cursor_x, self.rect.bottom - 6), 1,
            )


OPEN_ANIM_DURATION_MS = 260   # длительность анимации появления карточки настроек
CLOSE_ANIM_DURATION_MS = 200  # чуть быстрее открытия — закрытие ощущается отзывчивее, если резче
MODE_SWITCH_ANIM_DURATION_MS = 260  # длительность слайда между главным экраном и созданием темы

# Параллакс фона: пока панель открыта, "замороженный" кадр плеера отдаляется
# (уменьшается) и сдвигается в сторону, противоположную курсору относительно
# центра окна — классический эффект глубины.
PARALLAX_MAX_SHIFT_PX = 18     # максимальное смещение фона от курсора
PARALLAX_ZOOM_OUT = 0.05       # на сколько фон "отдаляется" (уменьшается) в открытом состоянии


class _Slider:
    """Простой горизонтальный слайдер с целочисленным диапазоном (для секунд кроссфейда)."""

    def __init__(self, rect: pygame.Rect, min_value: int, max_value: int):
        self.rect = rect
        self.min_value = min_value
        self.max_value = max_value
        self.handle_radius = rect.height

    def value_to_ratio(self, value: float) -> float:
        span = self.max_value - self.min_value
        return 0.0 if span == 0 else (value - self.min_value) / span

    def ratio_to_value(self, ratio: float) -> int:
        ratio = max(0.0, min(1.0, ratio))
        return round(self.min_value + ratio * (self.max_value - self.min_value))

    def get_ratio_from_x(self, mouse_x: int) -> float:
        ratio = (mouse_x - self.rect.x) / self.rect.width
        return max(0.0, min(1.0, ratio))

    def hit_rect(self) -> pygame.Rect:
        pad = self.handle_radius
        return pygame.Rect(self.rect.x - pad, self.rect.y - pad, self.rect.width + pad * 2, self.rect.height + pad * 2)

    def is_clicked(self, mouse_pos, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.hit_rect().collidepoint(mouse_pos)
        )

    def draw(self, surface, value: float, palette: dict):
        pygame.draw.rect(surface, palette["progress_bg"], self.rect, border_radius=self.rect.height // 2)
        ratio = self.value_to_ratio(value)
        fill_width = int(self.rect.width * ratio)
        if fill_width > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            pygame.draw.rect(surface, palette["progress_fill"], fill_rect, border_radius=self.rect.height // 2)

        handle_x = self.rect.x + fill_width
        handle_y = self.rect.centery
        pygame.draw.circle(surface, palette["text"], (handle_x, handle_y), self.handle_radius)
        pygame.draw.circle(surface, palette["accent"], (handle_x, handle_y), self.handle_radius - 2)


class _ToggleGroup:
    """Ряд из 2+ кнопок-переключателей, из которых активна ровно одна (для языка/темы)."""

    def __init__(self, rect: pygame.Rect, option_keys: list[str], gap: int = 8):
        self.option_keys = option_keys
        n = len(option_keys)
        btn_width = (rect.width - gap * (n - 1)) // n
        self.buttons = []
        for i, key in enumerate(option_keys):
            btn_rect = pygame.Rect(rect.x + i * (btn_width + gap), rect.y, btn_width, rect.height)
            self.buttons.append(btn_rect)

    def draw(self, surface, font, labels: list[str], active_key: str, palette: dict, mouse_pos):
        for btn_rect, key, label in zip(self.buttons, self.option_keys, labels):
            is_active = key == active_key
            hovered = btn_rect.collidepoint(mouse_pos)
            if is_active:
                color = palette["accent"]
            elif hovered:
                color = palette["row_hover"]
            else:
                color = palette["button_small_bg"]
            pygame.draw.rect(surface, color, btn_rect, border_radius=6)
            if not is_active:
                pygame.draw.rect(surface, palette["button_small_border"], btn_rect, width=1, border_radius=6)

            text = font.render(label, True, palette["text"])
            text_rect = text.get_rect(center=btn_rect.center)
            surface.blit(text, text_rect)

    def clicked_key(self, mouse_pos, event) -> str | None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        for btn_rect, key in zip(self.buttons, self.option_keys):
            if btn_rect.collidepoint(mouse_pos):
                return key
        return None


class _Dropdown:
    """
    Капсула с текстом и стрелкой справа (см. скриншот пользователя), при клике
    раскрывает список опций. Стрелка — PNG-иконка под тему (белая/чёрная),
    с текстовым "▾" фолбэком, если файла нет на диске.
    """

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.options: list[str] = []       # список отображаемых значений (имена тем)
        self.selected: str | None = None   # None = ничего не выбрано ("Название темы" плейсхолдер)
        self.is_expanded = False
        self.arrow_icon: pygame.Surface | None = None
        self._option_rects: list[pygame.Rect] = []

    def set_options(self, options: list[str]):
        self.options = options
        if self.selected not in options:
            self.selected = None

    def refresh_icon(self, base_dir: str, effective_theme: str, size: int = 14):
        self.arrow_icon = button_icons.get_named_icon(base_dir, "idk_how_to_call_it", effective_theme, size)

    def collapsed_hit_rect(self) -> pygame.Rect:
        return self.rect

    def expanded_list_rect(self) -> pygame.Rect:
        """Область раскрытого списка опций — под капсулой, до 5 видимых строк с прокруткой не делаем
        (тем обычно немного), высота растёт по числу опций."""
        row_h = 34
        list_h = max(row_h, min(len(self.options), 5) * row_h)
        return pygame.Rect(self.rect.x, self.rect.bottom + 6, self.rect.width, list_h)

    def handle_event(self, mouse_pos, event) -> bool:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False

        if self.is_expanded:
            list_rect = self.expanded_list_rect()
            if list_rect.collidepoint(mouse_pos) and self.options:
                row_h = list_rect.height / max(1, min(len(self.options), 5))
                idx = int((mouse_pos[1] - list_rect.y) / row_h)
                if 0 <= idx < len(self.options):
                    self.selected = self.options[idx]
                self.is_expanded = False
                return True
            # Клик снаружи списка (но внутри капсулы или вовне) — просто закрываем
            self.is_expanded = False
            if self.rect.collidepoint(mouse_pos):
                return True
            return False

        if self.rect.collidepoint(mouse_pos):
            self.is_expanded = not self.is_expanded and bool(self.options)
            return True

        return False

    def draw(self, surface, font, palette: dict, mouse_pos, placeholder: str):
        """Рисует только капсулу (текст + стрелка), БЕЗ раскрытого списка —
        список рисуется отдельно через draw_expanded_list(), последним слоем
        карточки, чтобы он не оказывался перекрыт полями, нарисованными позже
        в общем потоке отрисовки (было видно на скриншоте пользователя: поле
        "Название темы" перекрывало список сверху, потому что рисовалось после)."""
        hovered = self.rect.collidepoint(mouse_pos)
        bg_color = palette["row_hover"] if hovered else palette["button_small_bg"]
        pygame.draw.rect(surface, bg_color, self.rect, border_radius=self.rect.height // 2)
        pygame.draw.rect(surface, palette["button_small_border"], self.rect, width=1, border_radius=self.rect.height // 2)

        label = self.selected if self.selected else placeholder
        color = palette["text"] if self.selected else palette["text_dim"]
        text_surf = font.render(label, True, color)
        surface.blit(text_surf, (self.rect.x + 16, self.rect.centery - text_surf.get_height() // 2))

        arrow_area = pygame.Rect(self.rect.right - 36, self.rect.y, 36, self.rect.height)
        if self.arrow_icon is not None:
            icon = self.arrow_icon
            if self.is_expanded:
                icon = pygame.transform.flip(icon, False, True)  # раскрыт -> стрелка вверх
            icon_rect = icon.get_rect(center=arrow_area.center)
            surface.blit(icon, icon_rect)
        else:
            fallback = "^" if self.is_expanded else "v"
            fallback_surf = font.render(fallback, True, palette["text_dim"])
            surface.blit(fallback_surf, fallback_surf.get_rect(center=arrow_area.center))

    def draw_expanded_list(self, surface, font, palette: dict, mouse_pos):
        """Рисует только раскрытый список опций (если он открыт). Вызывающий
        код должен вызвать это ПОСЛЕДНИМ, поверх остального содержимого экрана."""
        if not (self.is_expanded and self.options):
            return

        list_rect = self.expanded_list_rect()
        pygame.draw.rect(surface, palette["panel"], list_rect, border_radius=10)
        pygame.draw.rect(surface, palette["button_small_border"], list_rect, width=1, border_radius=10)

        row_h = list_rect.height / max(1, min(len(self.options), 5))
        prev_clip = surface.get_clip()
        surface.set_clip(list_rect)
        for i, option in enumerate(self.options):
            row_rect = pygame.Rect(list_rect.x, int(list_rect.y + i * row_h), list_rect.width, int(row_h))
            row_hovered = row_rect.collidepoint(mouse_pos)
            if option == self.selected:
                pygame.draw.rect(surface, palette["row_current"], row_rect)
            elif row_hovered:
                pygame.draw.rect(surface, palette["row_hover"], row_rect)
            option_surf = font.render(option, True, palette["text"])
            surface.blit(option_surf, (row_rect.x + 16, row_rect.centery - option_surf.get_height() // 2))
        surface.set_clip(prev_clip)


class SettingsPanel:
    """
    Оверлей-панель настроек. Не открывает своё окно — рисуется поверх текущего
    кадра плеера в том же screen. Управляется через open()/close()/is_open.
    """

    PANEL_WIDTH = 440
    PANEL_HEIGHT = 360

    def __init__(self):
        self.is_open = False        # можно ли взаимодействовать (перехватывать события)
        self.is_visible = False     # нужно ли вообще рисовать панель (включая анимацию закрытия)
        self._dragging_crossfade = False
        self._card_rect = pygame.Rect(0, 0, self.PANEL_WIDTH, self.PANEL_HEIGHT)
        self._lang_toggle = None
        self._theme_toggle = None
        self._crossfade_slider = None
        self._close_btn = None
        self._font_label = None
        self._font_value = None
        self._font_title = None
        self._on_theme_change = None  # callback(new_theme) для запуска анимации перехода
        self._opened_at_ms = 0
        self._closing_started_at_ms = 0
        self._closing_start_progress = 1.0  # прогресс открытия, с которого стартовала анимация закрытия

        # --- Создание своей темы (под-экран) ---
        self._mode = "main"  # "main" | "create_theme"
        self._base_dir = None
        self._create_btn = None
        self._name_input = None
        self._save_theme_btn = None
        self._back_btn = None
        self._bg_slider = None
        self._accent_slider = None
        self._text_slider = None
        self._wave_slider = None  # цвет "пули"/волны визуализатора — настраивается отдельно от accent
        self._create_status_message = ""
        self._theme_dropdown = None
        self._editing_existing_theme = False  # True = выбрали существующую тему -> кнопка "Применить"
        self._loaded_theme_name = None        # имя темы, из которой заполнили редактор (для сравнения при сохранении)
        self._icons_theme_loaded = None       # под какую тему сейчас загружена стрелка дропдауна

        # --- Анимация переключения между главным экраном и созданием темы ---
        self._mode_transition_from = None    # режим, из которого уезжаем ("main"/"create_theme"), None = анимации нет
        self._mode_transition_started_at_ms = 0

    def open(self, window_width: int, window_height: int, base_dir: str, on_theme_change=None):
        self.is_open = True
        self.is_visible = True
        self._mode = "main"
        self._mode_transition_from = None
        self._on_theme_change = on_theme_change
        pygame.key.start_text_input()
        self._opened_at_ms = pygame.time.get_ticks()
        self._base_dir = base_dir

        self._card_rect = pygame.Rect(
            (window_width - self.PANEL_WIDTH) // 2,
            (window_height - self.PANEL_HEIGHT) // 2,
            self.PANEL_WIDTH, self.PANEL_HEIGHT,
        )

        margin = 24
        x = self._card_rect.x + margin
        w = self.PANEL_WIDTH - margin * 2

        # --- Шаг 1: вычисляем требуемую высоту карточки под каждый экран,
        # используя ту же арифметику зазоров, что и в раскладках ниже, но
        # ДО фактического создания виджетов — чтобы сначала один раз найти
        # финальный top карточки, а потом построить оба набора виджетов
        # относительно него (без риска рассинхрона между "как посчитали
        # высоту" и "где на самом деле оказались виджеты").
        # --- Шаг 1: сначала строим раскладку главного экрана как если бы она
        # начиналась прямо от base_top (offset=0), чтобы получить ФАКТИЧЕСКИЕ
        # координаты (а не приблизительно просуммированные вручную — это
        # раньше давало рассинхрон в несколько пикселей между вычисленной
        # "высотой контента" и тем, где элементы оказывались на самом деле).
        def _layout_main(top: int):
            title_y = top + 12
            lang_label_y = title_y + 34
            lang_row_y = lang_label_y + 20
            theme_label_y = lang_row_y + 34 + 18
            theme_row_y = theme_label_y + 20
            crossfade_label_y = theme_row_y + 34 + 22
            crossfade_slider_y = crossfade_label_y + 22
            create_theme_btn_y = crossfade_slider_y + 8 + 22
            close_y = create_theme_btn_y + 38 + 16
            close_bottom = close_y + 40
            return {
                "title_y": title_y, "lang_label_y": lang_label_y, "lang_row_y": lang_row_y,
                "theme_label_y": theme_label_y, "theme_row_y": theme_row_y,
                "crossfade_label_y": crossfade_label_y, "crossfade_slider_y": crossfade_slider_y,
                "create_theme_btn_y": create_theme_btn_y, "close_y": close_y, "close_bottom": close_bottom,
            }

        zero_layout = _layout_main(0)
        main_content_height = zero_layout["close_bottom"] + margin

        create_content_height = (
            12 + 34 + 22 + 40 + 18 + 22 + 36 + 18 + 22
            + 33 + 10 + 33 + 10 + 33 + 16 + 20 + 33 + 20 + 40 + 24
        )
        needed_height = max(main_content_height, create_content_height, self.PANEL_HEIGHT)

        self._card_rect.height = needed_height
        self._card_rect.y = (window_height - self._card_rect.height) // 2
        base_top = self._card_rect.y

        # Главный экран (язык/тема/кроссфейд) обычно компактнее экрана
        # создания темы — карточка же имеет единую высоту под оба режима.
        # Центрируем контент главного экрана внутри доступной высоты карточки:
        # ищем offset, при котором зазор сверху (до title_y) и зазор снизу
        # (после close_btn) становятся равны. Решается напрямую из
        # "нулевой" раскладки выше — без приближений и ручного подбора.
        offset = max(0, (needed_height - zero_layout["close_bottom"] - zero_layout["title_y"]) // 2)
        main_top = base_top + offset

        layout = _layout_main(main_top)
        title_y = layout["title_y"]
        lang_label_y = layout["lang_label_y"]
        lang_row_y = layout["lang_row_y"]
        theme_label_y = layout["theme_label_y"]
        theme_row_y = layout["theme_row_y"]
        crossfade_label_y = layout["crossfade_label_y"]
        crossfade_slider_y = layout["crossfade_slider_y"]
        create_theme_btn_y = layout["create_theme_btn_y"]
        close_y = layout["close_y"]

        self._lang_toggle = _ToggleGroup(pygame.Rect(x, lang_row_y, w, 34), ["ru", "en"])
        self._theme_toggle = _ToggleGroup(pygame.Rect(x, theme_row_y, w, 34), list(THEME_OPTIONS))
        self._crossfade_slider = _Slider(
            pygame.Rect(x, crossfade_slider_y, w, 8), MIN_CROSSFADE_SEC, MAX_CROSSFADE_SEC
        )
        self._create_btn = ui.Button(pygame.Rect(x, create_theme_btn_y, w, 38), "", small=True)
        self._close_btn = ui.Button(pygame.Rect(x, close_y, w, 40), "")

        self._label_y = {
            "lang": lang_label_y,
            "theme": theme_label_y,
            "crossfade": crossfade_label_y,
            "title": title_y,
        }

        if self._font_label is None:
            self._font_label = app_font.get_font(base_dir, 14)
            self._font_value = app_font.get_font(base_dir, 13)
            self._font_title = app_font.get_font(base_dir, 19, bold=True)

        self._init_create_theme_widgets(x, w, base_top)

    def _init_create_theme_widgets(self, x: int, w: int, base_top: int):
        """Создаёт элементы под-экрана "Создать тему" (та же карточка, тот же x/w,
        своя раскладка сверху вниз — переиспользует title_y карточки).
        Возвращает требуемую высоту карточки под этот экран (без изменения
        self._card_rect напрямую — это теперь делает open() один раз для
        обоих экранов сразу, чтобы растяжение под один не сдвигало контент
        другого вниз)."""
        title_y = base_top + 12
        dropdown_label_y = title_y + 34
        dropdown_y = dropdown_label_y + 22
        name_label_y = dropdown_y + 40 + 18
        name_input_y = name_label_y + 22
        colors_label_y = name_input_y + 36 + 18
        bg_slider_y = colors_label_y + 22
        accent_slider_y = bg_slider_y + 33 + 10
        text_slider_y = accent_slider_y + 33 + 10
        wave_label_y = text_slider_y + 33 + 16
        wave_slider_y = wave_label_y + 20
        buttons_y = wave_slider_y + 33 + 20

        self._theme_dropdown = _Dropdown(pygame.Rect(x, dropdown_y, w, 40))

        self._name_input = _TextInput(pygame.Rect(x, name_input_y, w, 36))

        default_palette = derive_palette_from_basics((18, 18, 20), (120, 90, 255), (230, 230, 235))
        slider_w = w
        self._bg_slider = _RGBSlider(pygame.Rect(x, bg_slider_y, slider_w, 33), default_palette["bg"])
        self._accent_slider = _RGBSlider(pygame.Rect(x, accent_slider_y, slider_w, 33), default_palette["accent"])
        self._text_slider = _RGBSlider(pygame.Rect(x, text_slider_y, slider_w, 33), default_palette["text"])
        self._wave_slider = _RGBSlider(pygame.Rect(x, wave_slider_y, slider_w, 33), default_palette["viz_wave"])

        btn_gap = 10
        btn_w = (w - btn_gap) // 2
        self._back_btn = ui.Button(pygame.Rect(x, buttons_y, btn_w, 40), "", small=True)
        self._save_theme_btn = ui.Button(pygame.Rect(x + btn_w + btn_gap, buttons_y, btn_w, 40), "", small=True)

        self._create_label_y = {
            "title": title_y,
            "dropdown": dropdown_label_y,
            "name": name_label_y,
            "colors": colors_label_y,
            "wave": wave_label_y,
        }
        self._create_buttons_y = buttons_y

    def _open_progress(self) -> float:
        """
        Возвращает текущий прогресс анимации открытия в диапазоне [0, 1]
        (0 = полностью закрыта/невидима, 1 = полностью открыта), с учётом
        ease-out кривой. Работает одинаково и во время open(), и во время
        close() — во втором случае просто идёт от текущего значения к 0.
        """
        now = pygame.time.get_ticks()

        if self.is_open:
            elapsed = now - self._opened_at_ms
            raw_t = min(1.0, elapsed / OPEN_ANIM_DURATION_MS)
            return 1 - (1 - raw_t) ** 3  # ease-out при открытии

        # Закрывается: линейно уходим от _closing_start_progress к 0 —
        # так что если панель закрыли ДО того, как открытие доиграло до конца,
        # анимация закрытия стартует с того промежуточного состояния, а не с 1.0.
        elapsed = now - self._closing_started_at_ms
        raw_t = min(1.0, elapsed / CLOSE_ANIM_DURATION_MS)
        eased_t = raw_t ** 2  # ease-in при закрытии — стартует медленно, ускоряется к исчезновению
        return self._closing_start_progress * (1 - eased_t)

    def _switch_mode(self, new_mode: str):
        """Переключает режим карточки (главный экран <-> создание темы) с
        горизонтальной слайд-анимацией: старый экран уезжает в сторону смены,
        новый въезжает с противоположной стороны до центра."""
        if new_mode == self._mode:
            return
        self._mode_transition_from = self._mode
        self._mode_transition_started_at_ms = pygame.time.get_ticks()
        self._mode = new_mode

        if new_mode == "create_theme":
            self._refresh_theme_dropdown_options()
            self._editing_existing_theme = False
            self._loaded_theme_name = None
            self._theme_dropdown.selected = None
            self._name_input.text = ""
            default_palette = derive_palette_from_basics((18, 18, 20), (120, 90, 255), (230, 230, 235))
            self._bg_slider.color = list(default_palette["bg"])
            self._bg_slider._sync_hex_from_color()
            self._accent_slider.color = list(default_palette["accent"])
            self._accent_slider._sync_hex_from_color()
            self._text_slider.color = list(default_palette["text"])
            self._text_slider._sync_hex_from_color()
            self._wave_slider.color = list(default_palette["viz_wave"])
            self._wave_slider._sync_hex_from_color()

    def _refresh_theme_dropdown_options(self):
        if self._base_dir is not None:
            self._theme_dropdown.set_options(custom_themes.list_custom_themes(self._base_dir))

    def _mode_switch_progress(self) -> float:
        """
        Прогресс переключения режима в [0, 1] с ease-out (0 = только начали
        уезжать, 1 = новый экран полностью на месте). Возвращает 1.0, если
        анимация не идёт (обычное статичное состояние).
        """
        if self._mode_transition_from is None:
            return 1.0
        elapsed = pygame.time.get_ticks() - self._mode_transition_started_at_ms
        raw_t = min(1.0, elapsed / MODE_SWITCH_ANIM_DURATION_MS)
        if raw_t >= 1.0:
            self._mode_transition_from = None
            return 1.0
        return 1 - (1 - raw_t) ** 3  # ease-out

    def close(self):
        if not self.is_open and not self.is_visible:
            return
        # Считаем прогресс ДО того, как выставим is_open=False — иначе
        # _open_progress() увидит уже is_open=False и пойдёт по ветке
        # "закрывается", даст неверную (уже уменьшающуюся) стартовую точку.
        current_progress = self._open_progress() if self.is_open else 0.0
        self.is_open = False
        self.is_visible = True  # остаётся видимой на время анимации закрытия
        self._dragging_crossfade = False
        self._closing_started_at_ms = pygame.time.get_ticks()
        self._closing_start_progress = current_progress
        pygame.key.stop_text_input()

    def handle_event(self, mouse_pos, event, settings: Settings):
        """Обрабатывает один pygame-event. Возвращает True, если событие "съедено" панелью
        (не должно дальше долетать до элементов плеера под ней)."""
        if not self.is_open:
            return False

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self._mode == "create_theme":
                self._switch_mode("main")
            else:
                self.close()
            return True

        if self._mode == "create_theme":
            return self._handle_create_theme_event(mouse_pos, event, settings)

        lang_key = self._lang_toggle.clicked_key(mouse_pos, event)
        if lang_key:
            settings.set_language(lang_key)
            return True

        theme_key = self._theme_toggle.clicked_key(mouse_pos, event)
        if theme_key and theme_key != settings.theme:
            old_effective = settings.effective_theme()
            settings.set_theme(theme_key)
            new_effective = settings.effective_theme()
            if self._on_theme_change and old_effective != new_effective:
                self._on_theme_change(new_effective)
            return True

        if self._crossfade_slider.is_clicked(mouse_pos, event):
            self._dragging_crossfade = True
            settings.set_crossfade_sec(
                self._crossfade_slider.ratio_to_value(self._crossfade_slider.get_ratio_from_x(mouse_pos[0]))
            )
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_dragging = self._dragging_crossfade
            self._dragging_crossfade = False
            if was_dragging:
                return True

        if self._create_btn.is_clicked(mouse_pos, event):
            self._switch_mode("create_theme")
            self._create_status_message = ""
            return True

        if self._close_btn.is_clicked(mouse_pos, event):
            self.close()
            return True

        # Клик вне карточки закрывает панель; клик внутри неё просто "съедается",
        # чтобы не проваливался на кнопки плеера под панелью.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self._card_rect.collidepoint(mouse_pos):
                self.close()
            return True

        return self._card_rect.collidepoint(mouse_pos)

    def _handle_create_theme_event(self, mouse_pos, event, settings: Settings) -> bool:
        was_selected = self._theme_dropdown.selected
        if self._theme_dropdown.handle_event(mouse_pos, event):
            if self._theme_dropdown.selected != was_selected and self._theme_dropdown.selected is not None:
                self._load_existing_theme_into_editor(self._theme_dropdown.selected)
            return True

        if self._name_input.handle_event(mouse_pos, event):
            return True

        if self._bg_slider.handle_event(mouse_pos, event):
            return True
        if self._accent_slider.handle_event(mouse_pos, event):
            return True
        if self._text_slider.handle_event(mouse_pos, event):
            return True
        if self._wave_slider.handle_event(mouse_pos, event):
            return True

        if self._back_btn.is_clicked(mouse_pos, event):
            self._switch_mode("main")
            return True

        if self._save_theme_btn.is_clicked(mouse_pos, event):
            self._save_current_custom_theme(settings)
            return True

        # Клик вне карточки закрывает панель целиком (как и в главном режиме)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self._card_rect.collidepoint(mouse_pos):
                self.close()
            return True

        return self._card_rect.collidepoint(mouse_pos)

    def _load_existing_theme_into_editor(self, display_name: str):
        """Подгружает сохранённую .vibetheme в редактор (имя + слайдеры),
        чтобы отредактировать существующую тему вместо создания новой."""
        from settings import THEMES, DEFAULT_THEME
        palette = custom_themes.load_custom_theme(self._base_dir, display_name, THEMES[DEFAULT_THEME])
        if palette is None:
            return

        self._name_input.text = display_name
        self._editing_existing_theme = True
        self._loaded_theme_name = display_name

        self._bg_slider.color = list(palette["bg"])
        self._bg_slider._sync_hex_from_color()
        self._accent_slider.color = list(palette["accent"])
        self._accent_slider._sync_hex_from_color()
        self._text_slider.color = list(palette["text"])
        self._text_slider._sync_hex_from_color()
        self._wave_slider.color = list(palette.get("viz_wave", palette["accent"]))
        self._wave_slider._sync_hex_from_color()

    def _save_current_custom_theme(self, settings: Settings):
        display_name = self._name_input.text.strip()
        if not display_name:
            self._create_status_message = settings.t("theme_name_empty")
            return

        palette = derive_palette_from_basics(
            self._bg_slider.get_color(),
            self._accent_slider.get_color(),
            self._text_slider.get_color(),
            self._wave_slider.get_color(),
        )
        theme_id = custom_themes.save_custom_theme(self._base_dir, display_name, palette)

        old_effective = settings.effective_theme()
        old_palette_snapshot = dict(settings.palette())
        settings.set_theme(theme_id)
        new_effective = settings.effective_theme()
        if self._on_theme_change and old_effective != new_effective:
            self._on_theme_change(new_effective)

        self._switch_mode("main")
        self._create_status_message = ""

    def update_drag(self, mouse_pos, settings: Settings):
        if not self.is_open:
            return
        if self._mode == "create_theme":
            self._bg_slider.update_drag(mouse_pos)
            self._accent_slider.update_drag(mouse_pos)
            self._text_slider.update_drag(mouse_pos)
            self._wave_slider.update_drag(mouse_pos)
        elif self._dragging_crossfade:
            settings.set_crossfade_sec(
                self._crossfade_slider.ratio_to_value(self._crossfade_slider.get_ratio_from_x(mouse_pos[0]))
            )

    def draw(self, surface, mouse_pos, settings: Settings, palette: dict, background_snapshot: pygame.Surface | None = None):
        if not self.is_visible:
            return

        window_w, window_h = surface.get_size()

        # Дропдаун-стрелка должна быть под цвет текущей темы (белая на тёмной,
        # чёрная на светлой) — проверяем и перегружаем при необходимости.
        effective_theme = settings.effective_theme()
        if self._theme_dropdown is not None and effective_theme != self._icons_theme_loaded:
            self._theme_dropdown.refresh_icon(self._base_dir, effective_theme)
            self._icons_theme_loaded = effective_theme

        eased_t = self._open_progress()

        # Если анимация закрытия доиграла до конца — панель больше не видима,
        # этот кадр рисуем как последний (eased_t уже ~0, ничего не будет видно).
        if not self.is_open and eased_t <= 0.0:
            self.is_visible = False
            return

        # --- Параллакс-фон ---
        # Если нам передали чистый снимок кадра плеера (до оверлея) — рисуем его
        # уменьшенным и смещённым от курсора вместо статичной картинки. Смещение
        # и степень отдаления нарастают вместе с анимацией открытия (eased_t),
        # так что при появлении панели фон одновременно "уезжает назад".
        if background_snapshot is not None:
            zoom = 1.0 - PARALLAX_ZOOM_OUT * eased_t
            scaled_w = max(1, int(window_w * zoom))
            scaled_h = max(1, int(window_h * zoom))
            scaled_bg = pygame.transform.smoothscale(background_snapshot, (scaled_w, scaled_h))

            # Курсор относительно центра окна, нормализованный в [-1, 1] по каждой оси
            center_x, center_y = window_w / 2, window_h / 2
            norm_dx = max(-1.0, min(1.0, (mouse_pos[0] - center_x) / center_x)) if center_x else 0.0
            norm_dy = max(-1.0, min(1.0, (mouse_pos[1] - center_y) / center_y)) if center_y else 0.0

            # Фон сдвигается в сторону, ПРОТИВОПОЛОЖНУЮ курсору — как будто мы
            # заглядываем "за" передний план в сторону движения мыши.
            shift_x = -norm_dx * PARALLAX_MAX_SHIFT_PX * eased_t
            shift_y = -norm_dy * PARALLAX_MAX_SHIFT_PX * eased_t

            bg_x = (window_w - scaled_w) / 2 + shift_x
            bg_y = (window_h - scaled_h) / 2 + shift_y

            surface.fill(palette["bg"])
            surface.blit(scaled_bg, (bg_x, bg_y))
        # Если снимок не передан — предполагаем, что вызывающий код уже
        # отрисовал плеер прямо на surface (старое поведение, без параллакса).

        # Затемняющая подложка на весь плеер — тоже плавно проявляется
        overlay_alpha = int(140 * eased_t)
        overlay = pygame.Surface((window_w, window_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, overlay_alpha))
        surface.blit(overlay, (0, 0))

        # --- Карточка настроек: анимация "приближения" (масштаб + прозрачность) ---
        card_scale = 0.85 + 0.15 * eased_t
        card_alpha = int(255 * eased_t)

        card_w = max(1, int(self._card_rect.width * card_scale))
        card_h = max(1, int(self._card_rect.height * card_scale))
        card_cx, card_cy = self._card_rect.center

        card_surface = pygame.Surface((self._card_rect.width, self._card_rect.height), pygame.SRCALPHA)
        local_rect = pygame.Rect(0, 0, self._card_rect.width, self._card_rect.height)

        self._close_btn.handle_hover(mouse_pos)
        self._create_btn.handle_hover(mouse_pos)
        self._back_btn.handle_hover(mouse_pos)
        self._save_theme_btn.handle_hover(mouse_pos)

        mode_t = self._mode_switch_progress()  # 1.0 = не анимируется, иначе [0,1) во время слайда

        if mode_t >= 1.0:
            # Обычное статичное состояние — рисуем текущий режим как есть
            if self._mode == "create_theme":
                self._draw_create_theme_contents(card_surface, local_rect, mouse_pos, settings, palette)
            else:
                self._draw_card_contents(card_surface, local_rect, mouse_pos, settings, palette)
        else:
            # Идёт слайд-переход: старый экран (self._mode_transition_from)
            # уезжает влево, новый (self._mode) въезжает с правого края —
            # рисуем оба на отдельных surface и сдвигаем по X при блите.
            card_w_local, card_h_local = card_surface.get_size()

            from_surface = pygame.Surface((card_w_local, card_h_local), pygame.SRCALPHA)
            to_surface = pygame.Surface((card_w_local, card_h_local), pygame.SRCALPHA)

            def render_mode(target_surface, mode_name):
                if mode_name == "create_theme":
                    self._draw_create_theme_contents(target_surface, local_rect, mouse_pos, settings, palette)
                else:
                    self._draw_card_contents(target_surface, local_rect, mouse_pos, settings, palette)

            render_mode(from_surface, self._mode_transition_from)
            render_mode(to_surface, self._mode)

            # Направление слайда: переход В "create_theme" -> старое уезжает
            # влево, новое въезжает справа. Переход обратно В "main" — наоборот.
            entering_create_theme = self._mode == "create_theme"
            direction = -1 if entering_create_theme else 1

            from_offset_x = direction * card_w_local * mode_t
            to_offset_x = direction * card_w_local * (mode_t - 1)

            # Фон карточки рисуем один раз под обоими слоями, чтобы не было
            # видно шва/просвета между уезжающим и въезжающим контентом.
            pygame.draw.rect(card_surface, palette["panel"], local_rect, border_radius=12)
            pygame.draw.rect(card_surface, palette["button_small_border"], local_rect, width=1, border_radius=12)

            prev_clip = card_surface.get_clip()
            card_surface.set_clip(local_rect)
            card_surface.blit(from_surface, (from_offset_x, 0))
            card_surface.blit(to_surface, (to_offset_x, 0))
            card_surface.set_clip(prev_clip)

        scaled_card = pygame.transform.smoothscale(card_surface, (card_w, card_h))
        scaled_card.set_alpha(card_alpha)
        surface.blit(scaled_card, (card_cx - card_w // 2, card_cy - card_h // 2))

    def _draw_card_contents(self, surface, card_rect: pygame.Rect, mouse_pos, settings: Settings, palette: dict):
        """Рисует содержимое карточки настроек в локальных координатах (0,0)-(w,h),
        чтобы затем весь результат можно было масштабировать одним блоком."""
        pygame.draw.rect(surface, palette["panel"], card_rect, border_radius=12)
        pygame.draw.rect(surface, palette["button_small_border"], card_rect, width=1, border_radius=12)

        # Все дочерние элементы (_lang_toggle и т.д.) хранят координаты в системе
        # основного окна (от self._card_rect), а тут мы рисуем в локальной системе
        # самой карточки (от 0,0) — считаем смещение один раз.
        offset_x = -self._card_rect.x
        offset_y = -self._card_rect.y

        def shifted(rect: pygame.Rect) -> pygame.Rect:
            return rect.move(offset_x, offset_y)

        title_surf = self._font_title.render(settings.t("settings_title"), True, palette["text"])
        surface.blit(title_surf, (24, self._label_y["title"] + offset_y))

        lang_label = self._font_label.render(settings.t("language"), True, palette["text_dim"])
        surface.blit(lang_label, (24, self._label_y["lang"] + offset_y))
        self._draw_toggle_group(surface, self._lang_toggle, offset_x, offset_y,
                                 ["Русский", "English"], settings.language, palette, mouse_pos)

        theme_label = self._font_label.render(settings.t("theme"), True, palette["text_dim"])
        surface.blit(theme_label, (24, self._label_y["theme"] + offset_y))
        theme_labels = [settings.t("theme_dark"), settings.t("theme_light"), settings.t("theme_system")]
        self._draw_toggle_group(surface, self._theme_toggle, offset_x, offset_y,
                                 theme_labels, settings.theme, palette, mouse_pos)

        crossfade_label = self._font_label.render(
            f'{settings.t("crossfade")}: {settings.crossfade_sec}{settings.t("seconds_short")}',
            True, palette["text_dim"],
        )
        surface.blit(crossfade_label, (24, self._label_y["crossfade"] + offset_y))
        self._draw_slider_shifted(surface, self._crossfade_slider, offset_x, offset_y, settings.crossfade_sec, palette)

        create_rect_shifted = shifted(self._create_btn.rect)
        pygame.draw.rect(
            surface,
            palette["accent"] if self._create_btn.hovered else palette["button_small_bg"],
            create_rect_shifted, border_radius=8,
        )
        if not self._create_btn.hovered:
            pygame.draw.rect(surface, palette["button_small_border"], create_rect_shifted, width=1, border_radius=8)
        create_label = self._font_value.render(settings.t("create_theme"), True, palette["text"])
        surface.blit(create_label, create_label.get_rect(center=create_rect_shifted.center))

        close_rect_shifted = shifted(self._close_btn.rect)
        pygame.draw.rect(
            surface,
            palette["accent"] if self._close_btn.hovered else palette["button_small_bg"],
            close_rect_shifted, border_radius=8,
        )
        close_label = self._font_value.render(settings.t("close"), True, palette["text"])
        surface.blit(close_label, close_label.get_rect(center=close_rect_shifted.center))

    def _draw_create_theme_contents(self, surface, card_rect: pygame.Rect, mouse_pos, settings: Settings, palette: dict):
        """Рисует под-экран "Создать тему": имя, три RGB-слайдера (фон/акцент/текст),
        кнопки "Назад"/"Сохранить". Локальные координаты — как в _draw_card_contents."""
        pygame.draw.rect(surface, palette["panel"], card_rect, border_radius=12)
        pygame.draw.rect(surface, palette["button_small_border"], card_rect, width=1, border_radius=12)

        offset_x = -self._card_rect.x
        offset_y = -self._card_rect.y

        def shifted(rect: pygame.Rect) -> pygame.Rect:
            return rect.move(offset_x, offset_y)

        title_surf = self._font_title.render(settings.t("create_theme"), True, palette["text"])
        surface.blit(title_surf, (24, self._create_label_y["title"] + offset_y))

        dropdown_label = self._font_label.render(settings.t("existing_theme"), True, palette["text_dim"])
        surface.blit(dropdown_label, (24, self._create_label_y["dropdown"] + offset_y))

        dropdown_shifted = shifted(self._theme_dropdown.rect)
        original_dropdown_rect = self._theme_dropdown.rect
        self._theme_dropdown.rect = dropdown_shifted
        self._theme_dropdown.draw(surface, self._font_value, palette, mouse_pos, settings.t("theme_name"))
        self._theme_dropdown.rect = original_dropdown_rect

        name_label = self._font_label.render(settings.t("theme_name"), True, palette["text_dim"])
        surface.blit(name_label, (24, self._create_label_y["name"] + offset_y))

        name_input_shifted = shifted(self._name_input.rect)
        original_rect = self._name_input.rect
        self._name_input.rect = name_input_shifted
        self._name_input.draw(surface, self._font_value, palette, placeholder=settings.t("theme_name"))
        self._name_input.rect = original_rect

        colors_label = self._font_label.render(settings.t("theme"), True, palette["text_dim"])
        surface.blit(colors_label, (24, self._create_label_y["colors"] + offset_y))

        for slider, label_key in (
            (self._bg_slider, "bg"), (self._accent_slider, "accent"), (self._text_slider, "text"),
        ):
            original = slider.rect
            slider.rect = shifted(original)
            slider._layout()
            slider.draw(surface, palette, self._font_value)
            slider.rect = original
            slider._layout()

        wave_label = self._font_label.render(settings.t("viz_wave_color"), True, palette["text_dim"])
        surface.blit(wave_label, (24, self._create_label_y["wave"] + offset_y))
        original_wave_rect = self._wave_slider.rect
        self._wave_slider.rect = shifted(original_wave_rect)
        self._wave_slider._layout()
        self._wave_slider.draw(surface, palette, self._font_value)
        self._wave_slider.rect = original_wave_rect
        self._wave_slider._layout()

        if self._create_status_message:
            status_surf = self._font_label.render(self._create_status_message, True, palette["error"])
            surface.blit(status_surf, (24, self._create_buttons_y + offset_y - 22))

        back_rect_shifted = shifted(self._back_btn.rect)
        pygame.draw.rect(
            surface,
            palette["accent"] if self._back_btn.hovered else palette["button_small_bg"],
            back_rect_shifted, border_radius=8,
        )
        if not self._back_btn.hovered:
            pygame.draw.rect(surface, palette["button_small_border"], back_rect_shifted, width=1, border_radius=8)
        back_label = self._font_value.render(settings.t("back"), True, palette["text"])
        surface.blit(back_label, back_label.get_rect(center=back_rect_shifted.center))

        save_rect_shifted = shifted(self._save_theme_btn.rect)
        pygame.draw.rect(surface, palette["accent"], save_rect_shifted, border_radius=8)
        is_editing = self._loaded_theme_name is not None and self._name_input.text.strip() == self._loaded_theme_name
        save_text = settings.t("apply_theme") if is_editing else settings.t("save")
        save_label = self._font_value.render(save_text, True, palette["text"])
        surface.blit(save_label, save_label.get_rect(center=save_rect_shifted.center))

        # Раскрытый список дропдауна рисуется САМЫМ ПОСЛЕДНИМ, поверх поля
        # имени и всего остального контента — иначе более поздние элементы
        # (например, поле "Название темы") перекрывают список сверху.
        original_dropdown_rect = self._theme_dropdown.rect
        self._theme_dropdown.rect = dropdown_shifted
        self._theme_dropdown.draw_expanded_list(surface, self._font_value, palette, mouse_pos)
        self._theme_dropdown.rect = original_dropdown_rect

    def _draw_toggle_group(self, surface, toggle: "_ToggleGroup", offset_x, offset_y, labels, active_key, palette, mouse_pos):
        for btn_rect, key, label in zip(toggle.buttons, toggle.option_keys, labels):
            shifted_rect = btn_rect.move(offset_x, offset_y)
            is_active = key == active_key
            hovered = btn_rect.collidepoint(mouse_pos)  # hover считается в реальных координатах окна
            if is_active:
                color = palette["accent"]
            elif hovered:
                color = palette["row_hover"]
            else:
                color = palette["button_small_bg"]
            pygame.draw.rect(surface, color, shifted_rect, border_radius=6)
            if not is_active:
                pygame.draw.rect(surface, palette["button_small_border"], shifted_rect, width=1, border_radius=6)
            text = self._font_value.render(label, True, palette["text"])
            surface.blit(text, text.get_rect(center=shifted_rect.center))

    def _draw_slider_shifted(self, surface, slider: "_Slider", offset_x, offset_y, value, palette):
        rect = slider.rect.move(offset_x, offset_y)
        pygame.draw.rect(surface, palette["progress_bg"], rect, border_radius=rect.height // 2)
        ratio = slider.value_to_ratio(value)
        fill_width = int(rect.width * ratio)
        if fill_width > 0:
            fill_rect = pygame.Rect(rect.x, rect.y, fill_width, rect.height)
            pygame.draw.rect(surface, palette["progress_fill"], fill_rect, border_radius=rect.height // 2)
        handle_x = rect.x + fill_width
        handle_y = rect.centery
        pygame.draw.circle(surface, palette["text"], (handle_x, handle_y), slider.handle_radius)
        pygame.draw.circle(surface, palette["accent"], (handle_x, handle_y), slider.handle_radius - 2)
