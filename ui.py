"""
UI-компоненты: кнопки, прогресс-бар, слайдер громкости, список треков, тосты.

Цвета больше не хардкодятся модульными константами — каждый компонент
получает текущую палитру темы (см. settings.py: Settings.palette()) и
рисуется в её цветах. Это позволяет переключать тёмную/светлую тему на лету.
"""

import pygame


# ASCII-замены для символов, которые может не поддерживать фолбэк-шрифт
ASCII_FALLBACK = {
    "▶": ">",
    "⏸": "||",
    "🔊": "Vol",
    "🔇": "Mute",
    "⚙": "Set",
}


class Button:
    def __init__(self, rect: pygame.Rect, label: str, small: bool = False):
        self.rect = rect
        self.label = label
        self.hovered = False
        self.small = small  # компактный стиль для панели инструментов сверху
        self.icon: pygame.Surface | None = None  # если задана — рисуется вместо текстового label

    def draw(self, surface, font, palette: dict):
        base_color = palette["button_small_bg"] if self.small else palette["panel"]
        color = palette["accent"] if self.hovered else base_color
        radius = 6 if self.small else 8
        pygame.draw.rect(surface, color, self.rect, border_radius=radius)
        if self.small and not self.hovered:
            pygame.draw.rect(surface, palette["button_small_border"], self.rect, width=1, border_radius=radius)

        if self.icon is not None:
            icon_rect = self.icon.get_rect(center=self.rect.center)
            surface.blit(self.icon, icon_rect)
            return

        display_label = self.label
        # Если шрифт не содержит символ (metrics вернёт None) — рисуем ASCII-замену,
        # чтобы вместо пустого "квадратика" пользователь видел понятный знак
        if display_label in ASCII_FALLBACK:
            metrics = font.metrics(display_label)
            if not metrics or any(m is None for m in metrics):
                display_label = ASCII_FALLBACK[display_label]

        text = font.render(display_label, True, palette["text"])
        text_rect = text.get_rect(center=self.rect.center)
        surface.blit(text, text_rect)

    def handle_hover(self, mouse_pos):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def is_clicked(self, mouse_pos, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(mouse_pos)
        )


class VolumeSlider:
    """
    Горизонтальный слайдер громкости с круглой ручкой.
    В отличие от ProgressBar, поддерживает live-перетаскивание
    (значение обновляется всё время, пока зажата кнопка мыши).
    """

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.handle_radius = rect.height  # ручка чуть крупнее полоски, для удобного попадания мышью

    def draw(self, surface, value: float, palette: dict):
        value = max(0.0, min(1.0, value))

        # Дорожка
        pygame.draw.rect(surface, palette["progress_bg"], self.rect, border_radius=self.rect.height // 2)
        fill_width = int(self.rect.width * value)
        if fill_width > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            pygame.draw.rect(surface, palette["progress_fill"], fill_rect, border_radius=self.rect.height // 2)

        # Ручка
        handle_x = self.rect.x + fill_width
        handle_y = self.rect.centery
        pygame.draw.circle(surface, palette["text"], (handle_x, handle_y), self.handle_radius)
        pygame.draw.circle(surface, palette["accent"], (handle_x, handle_y), self.handle_radius - 2)

    def get_ratio_from_x(self, mouse_x: int) -> float:
        ratio = (mouse_x - self.rect.x) / self.rect.width
        return max(0.0, min(1.0, ratio))

    def hit_rect(self) -> pygame.Rect:
        """Область клика чуть больше самой дорожки (учитывая выступающую ручку) — удобнее попадать мышью."""
        pad = self.handle_radius
        return pygame.Rect(self.rect.x - pad, self.rect.y - pad, self.rect.width + pad * 2, self.rect.height + pad * 2)

    def is_clicked(self, mouse_pos, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.hit_rect().collidepoint(mouse_pos)
        )


class ProgressBar:
    def __init__(self, rect: pygame.Rect):
        self.rect = rect

    def draw(self, surface, progress_ratio: float, palette: dict):
        pygame.draw.rect(surface, palette["progress_bg"], self.rect, border_radius=4)
        fill_width = int(self.rect.width * max(0.0, min(1.0, progress_ratio)))
        if fill_width > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            pygame.draw.rect(surface, palette["progress_fill"], fill_rect, border_radius=4)

    def get_ratio_from_click(self, mouse_x: int) -> float:
        ratio = (mouse_x - self.rect.x) / self.rect.width
        return max(0.0, min(1.0, ratio))

    def is_clicked(self, mouse_pos, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(mouse_pos)
        )


class Toast:
    """Всплывающее уведомление снизу экрана (ошибки, статусы) — само исчезает через время."""

    def __init__(self):
        self.message = ""
        self.is_error = False
        self.shown_at_ms = -1
        self.duration_ms = 3500

    def show(self, message: str, is_error: bool = False):
        self.message = message
        self.is_error = is_error
        self.shown_at_ms = pygame.time.get_ticks()

    def is_active(self) -> bool:
        if self.shown_at_ms < 0:
            return False
        return pygame.time.get_ticks() - self.shown_at_ms < self.duration_ms

    def draw(self, surface, font, window_width, window_height, palette: dict):
        if not self.is_active():
            return

        color = palette["error"] if self.is_error else palette["success"]
        # Многострочные сообщения (например, подробности ошибки декодирования)
        lines = self.message.split("\n")
        line_surfaces = [font.render(line, True, palette["text"]) for line in lines]
        max_width = max(s.get_width() for s in line_surfaces)

        padding = 14
        box_width = min(max_width + padding * 2, window_width - 40)
        box_height = len(lines) * 20 + padding * 2
        box_x = (window_width - box_width) // 2
        box_y = window_height - box_height - 20

        box_rect = pygame.Rect(box_x, box_y, box_width, box_height)
        pygame.draw.rect(surface, palette["panel"], box_rect, border_radius=8)
        pygame.draw.rect(surface, color, box_rect, width=2, border_radius=8)

        for i, line_surf in enumerate(line_surfaces):
            surface.blit(line_surf, (box_x + padding, box_y + padding + i * 20))


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


class TrackList:
    """
    Прокручиваемый список треков плейлиста с подсветкой текущего и
    маленькой кнопкой удаления (×) у каждой строки при наведении.
    """

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.line_height = 26
        self.scroll_offset = 0  # индекс первой видимой строки
        self._row_rects: list[tuple[int, pygame.Rect, pygame.Rect]] = []  # (playlist_idx, row_rect, remove_btn_rect)

    def visible_count(self) -> int:
        return max(1, self.rect.height // self.line_height)

    def ensure_visible(self, index: int, total: int):
        """Подскроллирует так, чтобы указанный индекс был виден (например, текущий играющий трек)."""
        vc = self.visible_count()
        if index < self.scroll_offset:
            self.scroll_offset = index
        elif index >= self.scroll_offset + vc:
            self.scroll_offset = index - vc + 1
        self.scroll_offset = max(0, min(self.scroll_offset, max(0, total - vc)))

    def scroll(self, delta: int, total: int):
        vc = self.visible_count()
        self.scroll_offset = max(0, min(self.scroll_offset + delta, max(0, total - vc)))

    def draw(self, surface, font, playlist_titles, current_index, mouse_pos, palette: dict, empty_text: str):
        pygame.draw.rect(surface, palette["panel"], self.rect, border_radius=8)
        self._row_rects = []

        if not playlist_titles:
            empty_surf = font.render(empty_text, True, palette["text_dim"])
            surface.blit(empty_surf, (self.rect.x + 12, self.rect.y + 10))
            return

        vc = self.visible_count()
        start_idx = self.scroll_offset
        end_idx = min(len(playlist_titles), start_idx + vc)

        # Обрезаем отрисовку по границам списка, чтобы строки не вылезали за панель
        prev_clip = surface.get_clip()
        surface.set_clip(self.rect)

        for row, idx in enumerate(range(start_idx, end_idx)):
            y = self.rect.y + row * self.line_height
            title = playlist_titles[idx]
            is_current = idx == current_index

            row_rect = pygame.Rect(self.rect.x, y, self.rect.width, self.line_height)
            row_hovered = row_rect.collidepoint(mouse_pos)

            if is_current:
                pygame.draw.rect(surface, palette["row_current"], row_rect)
            elif row_hovered:
                pygame.draw.rect(surface, palette["row_hover"], row_rect)

            color = palette["accent"] if is_current else palette["text_dim"]
            # Обрезаем длинные названия, чтобы не наезжали на кнопку удаления
            display_title = title if len(title) < 55 else title[:52] + "…"
            text = font.render(f"{idx + 1}. {display_title}", True, color)
            surface.blit(text, (self.rect.x + 12, y + 5))

            # Кнопка удаления (×) — показываем только при наведении на строку
            remove_rect = pygame.Rect(self.rect.right - 30, y + 3, 20, 20)
            if row_hovered:
                remove_color = palette["remove_x"] if remove_rect.collidepoint(mouse_pos) else palette["text_dim"]
                x_text = font.render("×", True, remove_color)
                surface.blit(x_text, (remove_rect.x + 5, remove_rect.y - 2))

            self._row_rects.append((idx, row_rect, remove_rect))

        surface.set_clip(prev_clip)

    def handle_click(self, mouse_pos, event) -> tuple[str, int] | None:
        """
        Обрабатывает клик по списку. Возвращает ('play', idx) при клике по строке,
        ('remove', idx) при клике по кнопке ×, иначе None.
        """
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        for idx, row_rect, remove_rect in self._row_rects:
            if remove_rect.collidepoint(mouse_pos):
                return ("remove", idx)
            if row_rect.collidepoint(mouse_pos):
                return ("play", idx)
        return None
