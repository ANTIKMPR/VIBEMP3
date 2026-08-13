"""
Плавный переход между палитрами тем (тёмная/светлая).

ThemeTransition хранит "от какой" и "до какой" палитры идёт переход и
текущий прогресс во времени. get_palette() на каждый кадр возвращает
палитру с полинтерполированными цветами (lerp по каждому RGB-каналу),
которую остальной код рисует как обычную палитру — компоненты UI не
знают, что она "анимированная".
"""

import pygame


TRANSITION_DURATION_MS = 280


def _lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _lerp_palette(palette_a: dict, palette_b: dict, t: float) -> dict:
    return {key: _lerp_color(palette_a[key], palette_b[key], t) for key in palette_a}


class ThemeTransition:
    def __init__(self):
        self._from_palette = None
        self._to_palette = None
        self._started_at_ms = 0
        self._active = False

    def start(self, from_palette: dict, to_palette: dict):
        """Запускает анимацию перехода от текущей палитры к новой."""
        self._from_palette = dict(from_palette)
        self._to_palette = dict(to_palette)
        self._started_at_ms = pygame.time.get_ticks()
        self._active = True

    def get_palette(self, target_palette: dict) -> dict:
        """
        Возвращает палитру для отрисовки текущего кадра: во время анимации —
        промежуточную интерполированную, иначе — просто target_palette как есть.
        target_palette всегда передаётся заново (на случай, если тема успела
        поменяться ещё раз до завершения предыдущей анимации).
        """
        if not self._active:
            return target_palette

        elapsed = pygame.time.get_ticks() - self._started_at_ms
        t = min(1.0, elapsed / TRANSITION_DURATION_MS)

        if t >= 1.0:
            self._active = False
            return target_palette

        # Плавное замедление к концу (ease-out) вместо линейного перехода
        eased_t = 1 - (1 - t) ** 2
        return _lerp_palette(self._from_palette, self._to_palette, eased_t)

    @property
    def is_active(self) -> bool:
        return self._active
