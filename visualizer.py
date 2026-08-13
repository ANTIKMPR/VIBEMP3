"""
Визуализатор: белые/цвета темы столбики-эквалайзер, с "АФК-волной" —
если музыка не играет (тишина) достаточно долго, по столбикам слева направо
проходит цветная волна (цвет настраивается в теме, ключ palette["viz_wave"]).
Автор идеи и первой версии волновой логики — Google Gemini, в коллаборации
с обычным градиентным визуализатором VIBEMP3.
"""

import pygame
import numpy as np


def _lerp_color(c1, c2, t):
    """Интерполяция (плавный переход) между двумя цветами."""
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


class Visualizer:
    def __init__(self, rect: pygame.Rect, num_bars: int = 48):
        self.rect = rect
        self.num_bars = num_bars
        self.values = np.zeros(num_bars)       # текущие (сглаженные) высоты
        self.peak_values = np.zeros(num_bars)  # "пиковые маркеры" сверху столбика

        self.smoothing = 0.35
        self.peak_fall_speed = 0.02

        self.block_size = 4
        self.block_gap = 1

        # --- Логика АФК (цветовая волна при тишине) ---
        self.idle_frames = 0
        self.afk_threshold = 120  # Кадров тишины до появления волны (при 60 FPS = 2 сек)

        self.wave_active = False
        self.wave_x = 0.0
        self.wave_speed = 12.0  # Скорость движения волны в пикселях/кадр

        # Цвета обновляются каждый кадр из палитры темы через set_theme_colors() —
        # значения по умолчанию здесь используются только пока set_theme_colors
        # ещё ни разу не вызывался (например, в первом кадре до отрисовки).
        self.wave_color = (180, 50, 255)
        self.base_color = (255, 255, 255)

    def set_theme_colors(self, base_color: tuple, wave_color: tuple):
        """
        Обновляет цвета столбиков и волны из текущей палитры темы. Вызывается
        каждый кадр перед draw() — так визуализатор всегда соответствует
        активной (в т.ч. кастомной) теме без отдельной логики смены темы здесь.
        """
        self.base_color = base_color
        self.wave_color = wave_color

    def update(self, target_values: np.ndarray):
        """Обновление высот и логики АФК."""
        target_values = np.resize(target_values, self.num_bars)

        # Плавное движение столбиков
        rising = target_values > self.values
        self.values = np.where(
            rising,
            self.values + (target_values - self.values) * 0.6,
            self.values + (target_values - self.values) * 0.15,
        )

        self.peak_values = np.maximum(self.peak_values - self.peak_fall_speed, self.values)

        # Проверка на тишину
        if np.max(target_values) < 0.01:
            self.idle_frames += 1
        else:
            self.idle_frames = 0

        # Запуск координаты, от которой красится визуализатор
        if self.idle_frames > self.afk_threshold and not self.wave_active:
            self.wave_active = True
            self.wave_x = self.rect.x - 100  # Начинаем за левым краем

        # Движение координаты волны
        if self.wave_active:
            self.wave_x += self.wave_speed
            # Когда хвост волны ушёл далеко за правый край
            if self.wave_x > self.rect.x + self.rect.width + 250:
                self.wave_active = False
                # Откидываем таймер немного назад, чтобы была пауза перед следующей волной
                self.idle_frames = self.afk_threshold - 60

    def _get_bar_color(self, bar_center_x: float) -> tuple:
        """Вычисляет цвет столбика в зависимости от его расстояния до волны."""
        if not self.wave_active:
            return self.base_color

        distance = self.wave_x - bar_center_x

        # Настройки ширины цветового пятна
        head_glow = 50.0    # Плавное нарастание цвета впереди
        tail_length = 200.0  # Длинный затухающий хвост позади

        if -head_glow <= distance <= 0:
            # Передняя часть волны
            intensity = 1.0 - (abs(distance) / head_glow)
            return _lerp_color(self.base_color, self.wave_color, intensity)

        elif 0 < distance <= tail_length:
            # Задняя часть (хвост) волны
            intensity = 1.0 - (distance / tail_length)
            return _lerp_color(self.base_color, self.wave_color, intensity)

        return self.base_color

    def draw(self, surface: pygame.Surface):
        x0, y0, w, h = self.rect
        bar_width = w / self.num_bars
        gap = max(1, int(bar_width * 0.15))
        inner_width = bar_width - gap

        for i in range(self.num_bars):
            bar_height = self.values[i] * h
            bar_x = x0 + i * bar_width
            bar_center_x = bar_x + inner_width / 2

            # Цвет столбика с учётом АФК-волны
            current_color = self._get_bar_color(bar_center_x)

            bar_y = y0 + h - bar_height

            # Рисуем столбик (даже при малой высоте — хотя бы нижний пиксель)
            self._draw_blocky_bar(surface, bar_x, bar_y, inner_width, bar_height, y0 + h, current_color)

            # "Нулевая" черта, чтобы в режиме тишины визуализатор был виден
            if bar_height < self.block_size:
                pygame.draw.rect(
                    surface, current_color,
                    (int(bar_x), int(y0 + h - self.block_size), int(inner_width), self.block_size),
                )

            # Пиковый маркер сверху
            peak_y = y0 + h - self.peak_values[i] * h
            if self.peak_values[i] > 0.02:
                pygame.draw.rect(
                    surface, current_color,
                    (bar_x, peak_y - 2, inner_width, 2),
                )

    def _draw_blocky_bar(self, surface, x, y, width, height, bottom, color):
        """Рисует столбик блоками (эффект сетки), применяя переданный цвет."""
        if height <= 0:
            return

        step = self.block_size + self.block_gap
        num_blocks = max(1, int(height // step))

        for b in range(num_blocks):
            block_y = bottom - (b + 1) * step

            # Лёгкое затемнение к низу для визуального объёма
            shade = 1.0 - (b / max(num_blocks, 1)) * 0.15
            block_color = tuple(min(255, int(c * shade)) for c in color)

            pygame.draw.rect(
                surface, block_color,
                (int(x), int(block_y), int(width), self.block_size),
            )
