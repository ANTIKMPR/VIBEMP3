"""
Отдельное pygame-окно настроек: язык, тема (тёмная/светлая),
плавный переход между треками (слайдер 1–10 секунд).

Открывается модально поверх основного плеера: основной цикл в main.py
приостанавливается на время открытия этого окна, а после закрытия
пересоздаёт своё окно (pygame поддерживает только один активный display
за раз, так что "переключение" — это закрыть один set_mode и открыть другой).
"""

import pygame

import ui
from settings import Settings, MIN_CROSSFADE_SEC, MAX_CROSSFADE_SEC


WINDOW_WIDTH = 420
WINDOW_HEIGHT = 360
FPS = 60


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

    def __init__(self, rect: pygame.Rect, option_keys: list[str], gap: int = 10):
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


def open_settings_window(settings: Settings, icon_surface=None):
    """
    Открывает модальное окно настроек. Блокирует выполнение до закрытия окна
    (крестик, Escape или кнопка "Закрыть"). Меняет settings на месте.

    После выхода из функции вызывающий код (main.py) должен пересоздать
    своё основное окно через pygame.display.set_mode(), т.к. pygame
    поддерживает только одно активное окно за раз.
    """
    if icon_surface is not None:
        pygame.display.set_icon(icon_surface)

    pygame.display.set_caption(settings.t("settings_title"))
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    font_label = pygame.font.SysFont("Arial", 15)
    font_value = pygame.font.SysFont("Arial", 14)
    font_title = pygame.font.SysFont("Arial", 20, bold=True)

    margin = 24
    row_gap = 34

    title_y = margin
    lang_label_y = title_y + 40
    lang_row_y = lang_label_y + 26
    theme_label_y = lang_row_y + 40 + row_gap - 34
    theme_row_y = theme_label_y + 26
    crossfade_label_y = theme_row_y + 40 + row_gap - 34
    crossfade_row_y = crossfade_label_y + 30
    close_btn_y = WINDOW_HEIGHT - margin - 40

    lang_toggle = _ToggleGroup(
        pygame.Rect(margin, lang_row_y, WINDOW_WIDTH - margin * 2, 36), ["ru", "en"]
    )
    theme_toggle = _ToggleGroup(
        pygame.Rect(margin, theme_row_y, WINDOW_WIDTH - margin * 2, 36), ["dark", "light"]
    )
    crossfade_slider = _Slider(
        pygame.Rect(margin, crossfade_row_y + 10, WINDOW_WIDTH - margin * 2, 8),
        MIN_CROSSFADE_SEC, MAX_CROSSFADE_SEC,
    )
    close_btn = ui.Button(pygame.Rect(margin, close_btn_y, WINDOW_WIDTH - margin * 2, 40), "")

    dragging_crossfade = False
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        palette = settings.palette()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

            lang_key = lang_toggle.clicked_key(mouse_pos, event)
            if lang_key:
                settings.set_language(lang_key)
                pygame.display.set_caption(settings.t("settings_title"))

            theme_key = theme_toggle.clicked_key(mouse_pos, event)
            if theme_key:
                settings.set_theme(theme_key)

            if crossfade_slider.is_clicked(mouse_pos, event):
                dragging_crossfade = True
                settings.set_crossfade_sec(crossfade_slider.ratio_to_value(crossfade_slider.get_ratio_from_x(mouse_pos[0])))

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                dragging_crossfade = False

            if close_btn.is_clicked(mouse_pos, event):
                running = False

        if dragging_crossfade:
            settings.set_crossfade_sec(crossfade_slider.ratio_to_value(crossfade_slider.get_ratio_from_x(mouse_pos[0])))

        # --- Отрисовка ---
        screen.fill(palette["bg"])

        title_surf = font_title.render(settings.t("settings_title"), True, palette["text"])
        screen.blit(title_surf, (margin, title_y))

        lang_label = font_label.render(settings.t("language"), True, palette["text_dim"])
        screen.blit(lang_label, (margin, lang_label_y))
        lang_toggle.draw(screen, font_value, ["Русский", "English"], settings.language, palette, mouse_pos)

        theme_label = font_label.render(settings.t("theme"), True, palette["text_dim"])
        screen.blit(theme_label, (margin, theme_label_y))
        theme_toggle.draw(
            screen, font_value,
            [settings.t("theme_dark"), settings.t("theme_light")],
            settings.theme, palette, mouse_pos,
        )

        crossfade_label = font_label.render(
            f'{settings.t("crossfade")}: {settings.crossfade_sec}{settings.t("seconds_short")}',
            True, palette["text_dim"],
        )
        screen.blit(crossfade_label, (margin, crossfade_label_y))
        crossfade_slider.draw(screen, settings.crossfade_sec, palette)

        close_btn.label = settings.t("close")
        close_btn.handle_hover(mouse_pos)
        close_btn.draw(screen, font_value, palette)

        pygame.display.flip()
        clock.tick(FPS)

    settings.save()
