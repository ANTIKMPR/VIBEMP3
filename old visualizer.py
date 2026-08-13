"""
Визуализатор в стиле градиентной гистограммы (как на референсном скрине):
синий -> фиолетовый -> розовый -> красный -> оранжевый -> жёлтый -> зелёный,
столбики с "зерном" (сеткой блоков) и плавным сглаживанием по времени.
"""

import pygame
import numpy as np


def _lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


# Градиент как на скрине: синий -> фиолетовый -> розовый -> красный -> оранжевый -> жёлтый -> зелёный
GRADIENT_STOPS = [
    (40, 60, 255),    # синий
    (140, 40, 230),   # фиолетовый
    (230, 30, 160),   # розовый/малиновый
    (240, 30, 60),    # красный
    (255, 130, 30),   # оранжевый
    (255, 220, 40),   # жёлтый
    (60, 230, 90),    # зелёный
]


def _color_for_ratio(t: float):
    """t от 0 (низкие частоты) до 1 (высокие) -> цвет по градиенту."""
    t = max(0.0, min(1.0, t))
    n = len(GRADIENT_STOPS) - 1
    idx = min(int(t * n), n - 1)
    local_t = t * n - idx
    return _lerp_color(GRADIENT_STOPS[idx], GRADIENT_STOPS[idx + 1], local_t)


class Visualizer:
    def __init__(self, rect: pygame.Rect, num_bars: int = 48):
        self.rect = rect
        self.num_bars = num_bars
        self.values = np.zeros(num_bars)       # текущие (сглаженные) высоты
        self.peak_values = np.zeros(num_bars)   # "пиковые маркеры" сверху столбика

        self.smoothing = 0.35     # скорость подъёма/спада столбика (0..1)
        self.peak_fall_speed = 0.02

        self.block_size = 4       # размер "пикселя" сетки внутри столбика
        self.block_gap = 1

    def update(self, target_values: np.ndarray):
        """Плавно подтягивает текущие высоты к новым целевым значениям."""
        target_values = np.resize(target_values, self.num_bars)

        # Атака быстрее спада — типичное поведение эквалайзеров
        rising = target_values > self.values
        self.values = np.where(
            rising,
            self.values + (target_values - self.values) * 0.6,
            self.values + (target_values - self.values) * 0.15,
        )

        self.peak_values = np.maximum(self.peak_values - self.peak_fall_speed, self.values)

    def draw(self, surface: pygame.Surface):
        x0, y0, w, h = self.rect
        bar_width = w / self.num_bars
        gap = max(1, int(bar_width * 0.15))
        inner_width = bar_width - gap

        for i in range(self.num_bars):
            ratio = i / (self.num_bars - 1) if self.num_bars > 1 else 0
            color = _color_for_ratio(ratio)

            bar_height = self.values[i] * h
            bar_x = x0 + i * bar_width
            bar_y = y0 + h - bar_height

            self._draw_blocky_bar(surface, bar_x, bar_y, inner_width, bar_height, y0 + h, color)

            # Пиковый маркер — тонкая яркая полоска над столбиком
            peak_y = y0 + h - self.peak_values[i] * h
            if self.peak_values[i] > 0.02:
                pygame.draw.rect(
                    surface, (255, 255, 255),
                    (bar_x, peak_y - 2, inner_width, 2),
                )

    def _draw_blocky_bar(self, surface, x, y, width, height, bottom, color):
        """Рисует столбик в виде стопки маленьких блоков (эффект 'пиксельной' сетки)."""
        if height <= 0:
            return

        step = self.block_size + self.block_gap
        num_blocks = max(1, int(height // step))

        for b in range(num_blocks):
            block_y = bottom - (b + 1) * step
            # Лёгкое затемнение к низу для глубины
            shade = 1.0 - (b / max(num_blocks, 1)) * 0.15
            block_color = tuple(min(255, int(c * shade)) for c in color)
            pygame.draw.rect(
                surface, block_color,
                (int(x), int(block_y), int(width), self.block_size),
            )
