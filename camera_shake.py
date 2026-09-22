"""
"Удары камеры" — короткий эффект приближения/отдаления (zoom-punch) экрана
плеера в моменты, заданные пакетом VIBE-SYNC (camera_hits: список секунд в
треке, вручную или сгенерированных по BPM — см. vibesync.py). На удар экран
резко увеличивается (или уменьшается — см. ZOOM_DIRECTION) и плавно
возвращается к нормальному масштабу — как "пульс" в такт музыке.
"""

import pygame


SHAKE_DURATION_MS = 180        # как долго длится один "пульс" масштаба
ZOOM_MAX_DELTA = 0.06          # на сколько максимально меняется масштаб в пике удара (0.06 = ±6%)
ZOOM_DIRECTION = 1             # 1 = приближение (zoom-in) на удар, -1 = отдаление (zoom-out)
HIT_MATCH_WINDOW_SEC = 0.12    # насколько точно позиция трека должна совпасть с меткой удара


class CameraShake:
    """
    Отслеживает список меток ударов (camera_hits) для текущего трека и
    держит текущий множитель масштаба экрана (1.0 = без эффекта), которым
    main.py масштабирует кадр вокруг центра для эффекта "пульса" в такт.
    """

    def __init__(self):
        self._hits: list[float] = []
        self._next_hit_idx = 0
        self._active_shake_started_at = None
        self._current_scale = 1.0
        self._track_key = None  # что-то уникальное для текущего трека, чтобы понять, когда сбрасывать состояние

    def set_hits(self, hits: list[float], track_key):
        """
        Задаёт список меток ударов (в секундах) для нового трека. track_key —
        любое значение, уникально идентифицирующее трек (например, путь к
        файлу) — используется, чтобы не пересбрасывать прогресс, если этот
        же трек всё ещё играет (set_hits может вызываться из main.py каждый
        кадр для простоты — реальный сброс происходит только при смене трека).
        """
        if track_key == self._track_key:
            return
        self._track_key = track_key
        self._hits = sorted(hits) if hits else []
        self._next_hit_idx = 0
        self._active_shake_started_at = None
        self._current_scale = 1.0

    def clear(self):
        """Сбрасывает состояние (например, когда VIBE-SYNC трек закончился/трек без ударов)."""
        self._hits = []
        self._next_hit_idx = 0
        self._active_shake_started_at = None
        self._current_scale = 1.0
        self._track_key = None

    def update(self, position_sec: float):
        """
        Вызывается каждый кадр с текущей позицией воспроизведения трека —
        продвигает указатель по меткам ударов и запускает новый "пульс",
        когда позиция догоняет очередную метку. Не полагается на точное
        совпадение (плеер не идёт строго по кадрам аудио), а на "догнала ли
        текущая позиция ближайшую ещё не сработавшую метку".
        """
        now = pygame.time.get_ticks()

        # Запускаем все метки, которые уже "позади" текущей позиции — на
        # случай просадки FPS/скачка позиции (например, после перемотки)
        # не пропускаем удар молча, а сразу катаемся по нему один раз.
        while self._next_hit_idx < len(self._hits) and self._hits[self._next_hit_idx] <= position_sec + HIT_MATCH_WINDOW_SEC:
            self._trigger_shake(now)
            self._next_hit_idx += 1

        self._current_scale = self._compute_scale(now)

    def notify_seek(self, new_position_sec: float):
        """
        Вызывается при перемотке — пересчитывает, с какой метки продолжать
        (иначе после перемотки вперёд плеер попытался бы "досрочно" отыграть
        все пропущенные удары разом, а после перемотки назад — не сыграл бы
        уже пройденные метки снова).
        """
        # Находим первую метку, которая ещё впереди новой позиции
        idx = 0
        while idx < len(self._hits) and self._hits[idx] < new_position_sec:
            idx += 1
        self._next_hit_idx = idx
        self._active_shake_started_at = None
        self._current_scale = 1.0

    def _trigger_shake(self, now_ms: int):
        self._active_shake_started_at = now_ms

    def _compute_scale(self, now_ms: int) -> float:
        if self._active_shake_started_at is None:
            return 1.0

        elapsed = now_ms - self._active_shake_started_at
        if elapsed >= SHAKE_DURATION_MS:
            self._active_shake_started_at = None
            return 1.0

        progress = elapsed / SHAKE_DURATION_MS
        # Квадратичный спад — резкий скачок масштаба в начале удара и
        # быстрое затухание к нормальному размеру, ощущается как чёткий
        # "пульс", а не плавное дыхание (важно при высоком BPM, где удары
        # идут часто и должны визуально не сливаться в постоянную рябь).
        intensity = (1.0 - progress) ** 2
        return 1.0 + ZOOM_DIRECTION * ZOOM_MAX_DELTA * intensity

    @property
    def scale(self) -> float:
        """Текущий множитель масштаба экрана (1.0 = без эффекта) — используй
        для увеличения/уменьшения кадра вокруг его центра при отрисовке."""
        return self._current_scale

    @property
    def is_active(self) -> bool:
        return self._active_shake_started_at is not None

