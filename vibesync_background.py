"""
Фон плеера для VIBE-SYNC треков:

- Если в пакете есть видео (resources/*.mp4) — оно играет зацикленным фоном
  окна, а маленькая обложка (если есть картинка) рисуется рядом с названием
  трека, как обычный album art.
- Если видео нет, но есть картинка обложки — она становится параллакс-фоном
  окна: слегка увеличена, лениво сдвигается в сторону, противоположную
  курсору (тот же приём, что уже используется в settings_panel.py для фона
  за панелью настроек).
- Если нет ни того, ни другого — фона нет, ничего не рисуется, вызывающий
  код (main.py) просто заливает обычный цвет темы как раньше.

Видео декодируется через imageio (ffmpeg-бэкенд) покадрово в реальном
времени — для VIBE-SYNC-роликов ожидаются короткие зацикленные фоновые
видео, не полнометражные, так что не требуется предзагрузка в память.
"""

import pygame

try:
    import imageio.v3 as iio
    _IMAGEIO_AVAILABLE = True
except ImportError:
    _IMAGEIO_AVAILABLE = False


PARALLAX_MAX_SHIFT_PX = 22   # максимальное смещение параллакс-фона от курсора
PARALLAX_ZOOM = 1.08         # насколько картинка/видео увеличены относительно окна (даёт запас для сдвига без чёрных краёв)
DARKEN_ALPHA = 175           # затемнение поверх фона (картинки/видео), 0-255 — сильнее, чтобы текст интерфейса читался поверх любого фона


class _VideoPlayer:
    """
    Покадровое воспроизведение зацикленного mp4 через imageio.

    Два режима работы:
    - Обычный (без sync) — просто крутится по собственному внутреннему
      таймеру (по fps видео), независимо от позиции трека, зацикливаясь
      по достижении конца.
    - Синхронизированный (bgvideo_sync=true в sync.json) — кадр видео
      подстраивается под текущую позицию трека: 1 секунда трека = 1 секунда
      видео. Если видео короче трека, оно зацикливается по модулю своей
      длительности (см. VibeSyncBackground.update()/set_track_position()).

    Кадры отдаются уже обрезанными под целевой размер без искажения
    пропорций (crop-to-fill — как CSS object-fit: cover), а не растянутыми.
    """

    def __init__(self, video_path: str, target_size: tuple):
        self.video_path = video_path
        self.target_size = target_size
        self._reader = None
        self._fps = 24.0
        self._duration_sec = None
        self._last_frame_surface: pygame.Surface | None = None
        self._last_advance_ms = 0
        self._broken = False
        self._is_paused = False

        # Позиция чтения потока — сколько кадров уже прочитано от начала
        # текущего reader'а. Нужна, чтобы решить (в синхронизированном
        # режиме), можно ли просто дочитать вперёд до нужного кадра, или
        # надо пересоздавать reader с нуля (целевой кадр уже позади).
        self._frames_read = 0

        if not _IMAGEIO_AVAILABLE:
            self._broken = True
            return

        try:
            self._reader = iio.imiter(video_path, plugin="FFMPEG")
            meta = iio.immeta(video_path, plugin="FFMPEG")
            self._fps = float(meta.get("fps", 24.0)) or 24.0
            duration = meta.get("duration")
            self._duration_sec = float(duration) if duration else None
        except Exception as e:
            print(f"[VIBEMP3] Не удалось открыть видео VIBE-SYNC ({video_path}): {e}")
            self._broken = True

    @property
    def is_broken(self) -> bool:
        return self._broken

    @property
    def duration_sec(self) -> float | None:
        return self._duration_sec

    def set_paused(self, paused: bool):
        """Ставит/снимает паузу — во время паузы кадры не продвигаются,
        последний декодированный кадр остаётся на экране неподвижным
        (используется, чтобы видео стояло вместе с треком)."""
        self._is_paused = paused

    def _restart_reader(self):
        try:
            self._reader = iio.imiter(self.video_path, plugin="FFMPEG")
            self._frames_read = 0
        except Exception as e:
            print(f"[VIBEMP3] Не удалось перезапустить видео VIBE-SYNC ({self.video_path}): {e}")
            self._broken = True

    def _next_raw_frame(self):
        """Читает следующий кадр из imageio-итератора, зацикливая видео при
        достижении конца (пересоздаёт reader). None, если видео сломано."""
        if self._reader is None:
            return None
        _t0 = pygame.time.get_ticks()
        try:
            frame = next(self._reader)
            self._frames_read += 1
            _elapsed = pygame.time.get_ticks() - _t0
            if _elapsed > 20:
                print(f"[VIBEMP3][perf] decode frame: {_elapsed}ms")
            return frame
        except StopIteration:
            self._restart_reader()
            if self._broken:
                return None
            try:
                frame = next(self._reader)
                self._frames_read += 1
                return frame
            except Exception as e:
                print(f"[VIBEMP3] Не удалось прочитать кадр после перезапуска видео VIBE-SYNC ({self.video_path}): {e}")
                self._broken = True
                return None
        except Exception as e:
            print(f"[VIBEMP3] Ошибка чтения кадра видео VIBE-SYNC ({self.video_path}): {e}")
            self._broken = True
            return None

    def _make_surface(self, raw) -> pygame.Surface:
        """Конвертирует numpy-кадр в pygame.Surface и обрезает под
        target_size без искажения пропорций (crop-to-fill)."""
        _t0 = pygame.time.get_ticks()
        # imageio отдаёт (H, W, 3) RGB numpy-массив; pygame ожидает (W, H, 3)
        surface = pygame.surfarray.make_surface(raw.swapaxes(0, 1))
        result = _scale_crop_to_fill(surface, self.target_size, fast=True)
        _elapsed = pygame.time.get_ticks() - _t0
        if _elapsed > 10:
            print(f"[VIBEMP3][perf] make_surface (convert+crop): {_elapsed}ms, raw shape={raw.shape}, target={self.target_size}")
        return result

    def get_current_frame(self) -> pygame.Surface | None:
        """
        Возвращает текущий кадр как Surface, продвигая видео по собственному
        внутреннему таймеру (по fps видео) — используется в обычном
        (не синхронизированном с треком) режиме. На паузе кадр не
        продвигается, отдаётся последний декодированный.
        """
        if self._broken:
            return None
        if self._is_paused:
            return self._last_frame_surface

        now = pygame.time.get_ticks()
        frame_interval_ms = 1000.0 / self._fps

        if self._last_frame_surface is None or (now - self._last_advance_ms) >= frame_interval_ms:
            raw = self._next_raw_frame()
            if raw is None:
                return self._last_frame_surface
            try:
                self._last_frame_surface = self._make_surface(raw)
                self._last_advance_ms = now
            except Exception as e:
                print(f"[VIBEMP3] Не удалось преобразовать кадр видео VIBE-SYNC: {e}")
                self._broken = True
                return self._last_frame_surface

        return self._last_frame_surface

    def get_frame_at_track_position(self, track_position_sec: float) -> pygame.Surface | None:
        """
        Синхронизированный режим (bgvideo_sync=true): возвращает кадр,
        соответствующий текущей позиции трека — 1 секунда трека = 1 секунда
        видео. Если видео короче трека, зацикливается по модулю своей
        длительности. На паузе (см. set_paused) кадр не продвигается.
        """
        if self._broken:
            return None
        if self._is_paused:
            return self._last_frame_surface
        if self._duration_sec is None or self._duration_sec <= 0:
            # Не знаем длительность видео — не можем синхронизировать по
            # модулю, откатываемся на обычный таймер, чтобы хоть что-то
            # показать вместо чёрного экрана.
            return self.get_current_frame()

        target_time = track_position_sec % self._duration_sec
        target_frame_idx = int(target_time * self._fps)

        if target_frame_idx < self._frames_read:
            # Целевой кадр уже позади (перемотка назад или зацикливание
            # видео при более длинном треке) — единственный надёжный способ
            # вернуться назад с imiter-потоком это пересоздать reader.
            self._restart_reader()
            if self._broken:
                return None

        # Дочитываем вперёд до целевого кадра (обычно недорого — несколько
        # кадров за раз при плавном воспроизведении, см. замер скорости).
        _skip_start = self._frames_read
        raw = None
        while self._frames_read <= target_frame_idx:
            raw = self._next_raw_frame()
            if raw is None:
                break
        _skipped = self._frames_read - _skip_start
        if _skipped > 3:
            print(f"[VIBEMP3][perf] skipped {_skipped} video frames in one call (target_frame_idx={target_frame_idx})")

        if raw is not None:
            try:
                self._last_frame_surface = self._make_surface(raw)
            except Exception as e:
                print(f"[VIBEMP3] Не удалось преобразовать кадр видео VIBE-SYNC: {e}")
                self._broken = True

        return self._last_frame_surface

    def close(self):
        if self._reader is not None:
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None


def _scale_crop_to_fill(source: pygame.Surface, target_size: tuple, fast: bool = False) -> pygame.Surface:
    """
    Масштабирует source так, чтобы полностью покрыть target_size без
    искажения пропорций, обрезая лишнее по одной из осей (аналог CSS
    object-fit: cover) — вместо растягивания/сжатия картинки под
    произвольное соотношение сторон окна.

    fast=True использует pygame.transform.scale (без сглаживания) вместо
    smoothscale — для кадров видео, которые пересчитываются на каждый новый
    декодированный кадр (20-30 раз/сек), а не один раз при загрузке.
    """
    target_w, target_h = target_size
    src_w, src_h = source.get_size()
    scale_fn = pygame.transform.scale if fast else pygame.transform.smoothscale
    if src_w == 0 or src_h == 0:
        return scale_fn(source, target_size)

    scale = max(target_w / src_w, target_h / src_h)
    scaled_w, scaled_h = round(src_w * scale), round(src_h * scale)
    scaled = scale_fn(source, (scaled_w, scaled_h))

    crop_x = max(0, (scaled_w - target_w) // 2)
    crop_y = max(0, (scaled_h - target_h) // 2)
    crop_rect = pygame.Rect(crop_x, crop_y, target_w, target_h)

    result = pygame.Surface(target_size)
    result.blit(scaled, (0, 0), area=crop_rect)
    return result


class VibeSyncBackground:
    """
    Держит текущее состояние фона для активного VIBE-SYNC трека: либо
    параллакс-картинка, либо видеоплеер, либо ничего. main.py вызывает
    set_package() при смене трека и draw_background()/draw_small_cover()
    каждый кадр.
    """

    def __init__(self):
        self._active_package = None  # идентичность объекта VibeSyncPackage, для которого сейчас загружены ресурсы
        self._cover_image_scaled: pygame.Surface | None = None  # картинка, УЖЕ смасштабированная под PARALLAX_ZOOM (не пересчитывается каждый кадр)
        self._small_cover_image: pygame.Surface | None = None  # маленькая версия (для отображения рядом с названием, когда есть видео)
        self._video_player: _VideoPlayer | None = None
        self._darken_overlay: pygame.Surface | None = None  # кэш затемняющей подложки — пересоздаётся только при смене размера окна
        self._darken_overlay_size: tuple | None = None

    def set_package(self, package, window_size: tuple):
        """
        Обновляет загруженные ресурсы под новый активный пакет (или None,
        если текущий трек — не VIBE-SYNC). Ничего не делает, если пакет тот
        же самый, что уже загружен (сравнение по идентичности объекта).
        """
        if package is self._active_package:
            return

        self._release_current()
        self._active_package = package

        if package is None:
            return

        zoomed_w = round(window_size[0] * PARALLAX_ZOOM)
        zoomed_h = round(window_size[1] * PARALLAX_ZOOM)

        if package.has_image:
            try:
                raw = pygame.image.load(package.image_path).convert()
                small_size = 44
                self._small_cover_image = pygame.transform.smoothscale(raw, (small_size, small_size))
                # Параллакс-картинку масштабируем ОДИН раз здесь (не каждый
                # кадр в draw_background) — на кадр остаётся только дешёвый
                # blit со сдвигом позиции, а не smoothscale заново.
                cropped = _scale_crop_to_fill(raw, (zoomed_w, zoomed_h))
                self._cover_image_scaled = cropped
            except Exception as e:
                print(f"[VIBEMP3] Не удалось загрузить обложку VIBE-SYNC ({package.image_path}): {e}")
                self._cover_image_scaled = None
                self._small_cover_image = None

        if package.has_video:
            # Декодируем видео сразу под увеличенный (ZOOM) размер — иначе
            # пришлось бы делать smoothscale дважды на каждый кадр (один раз
            # в _VideoPlayer до целевого размера окна, второй раз в
            # _draw_parallax_layer до ZOOM-размера).
            self._video_player = _VideoPlayer(package.video_path, (zoomed_w, zoomed_h))
            if self._video_player.is_broken:
                self._video_player = None

    def _release_current(self):
        if self._video_player is not None:
            self._video_player.close()
            self._video_player = None
        self._cover_image_scaled = None
        self._small_cover_image = None

    def _get_darken_overlay(self, window_size: tuple) -> pygame.Surface:
        """Возвращает закэшированную затемняющую подложку нужного размера,
        пересоздавая её только если размер окна поменялся (обычно не
        меняется вообще — окно фиксированного размера) — иначе это была бы
        аллокация нового Surface + заливка на каждый кадр."""
        if self._darken_overlay is None or self._darken_overlay_size != window_size:
            self._darken_overlay = pygame.Surface(window_size, pygame.SRCALPHA)
            self._darken_overlay.fill((0, 0, 0, DARKEN_ALPHA))
            self._darken_overlay_size = window_size
        return self._darken_overlay

    @property
    def has_background(self) -> bool:
        """Есть ли что рисовать фоном прямо сейчас (видео ИЛИ параллакс-картинка)."""
        return self._video_player is not None or (self._cover_image_scaled is not None and not self._has_video_package)

    @property
    def _has_video_package(self) -> bool:
        return self._active_package is not None and self._active_package.has_video

    @property
    def has_small_cover(self) -> bool:
        """Есть ли маленькая обложка для показа рядом с названием (случай "есть видео")."""
        return self._has_video_package and self._small_cover_image is not None

    def draw_background(self, surface: pygame.Surface, mouse_pos: tuple,
                         track_position_sec: float = 0.0, is_paused: bool = False):
        """
        Рисует фон на весь surface: видео (если есть) или картинку обложки
        (если видео нет) — оба варианта с одинаковым параллакс-сдвигом от
        курсора и затемняющей подложкой поверх, чтобы текст интерфейса
        оставался читаемым независимо от того, что на фоне. Ничего не
        делает, если фона нет — вызывающий код должен сам залить обычный
        цвет темы до вызова этого метода.

        track_position_sec/is_paused нужны видео: пауза останавливает кадр
        вместе с треком, а если у пакета включён bgvideo_sync — кадр
        подстраивается под текущую позицию трека (1 сек трека = 1 сек видео).

        Источник (картинка/видеокадр) уже приходит смасштабированным под
        PARALLAX_ZOOM заранее (картинка — в set_package, видео — decode
        сразу под нужный размер в _VideoPlayer) — здесь остаётся только
        дешёвый blit со сдвигом позиции, без smoothscale на каждый кадр.
        """
        if self._video_player is not None:
            self._video_player.set_paused(is_paused)
            if self._active_package is not None and self._active_package.bgvideo_sync:
                frame = self._video_player.get_frame_at_track_position(track_position_sec)
            else:
                frame = self._video_player.get_current_frame()
            if frame is not None:
                self._draw_parallax_layer(surface, frame, mouse_pos)
            return

        if self._cover_image_scaled is not None and not self._has_video_package:
            self._draw_parallax_layer(surface, self._cover_image_scaled, mouse_pos)

    def _draw_parallax_layer(self, surface: pygame.Surface, prescaled_source: pygame.Surface, mouse_pos: tuple):
        """
        Блитит уже готовый (заранее смасштабированный под PARALLAX_ZOOM)
        source со сдвигом позиции в сторону, противоположную курсору, и
        накладывает закэшированную затемняющую подложку поверх. Никаких
        smoothscale/аллокаций Surface на этом пути — только пара blit'ов.
        """
        window_w, window_h = surface.get_size()
        scaled_w, scaled_h = prescaled_source.get_size()

        center_x, center_y = window_w / 2, window_h / 2
        norm_dx = max(-1.0, min(1.0, (mouse_pos[0] - center_x) / center_x)) if center_x else 0.0
        norm_dy = max(-1.0, min(1.0, (mouse_pos[1] - center_y) / center_y)) if center_y else 0.0

        shift_x = -norm_dx * PARALLAX_MAX_SHIFT_PX
        shift_y = -norm_dy * PARALLAX_MAX_SHIFT_PX

        pos_x = (window_w - scaled_w) / 2 + shift_x
        pos_y = (window_h - scaled_h) / 2 + shift_y

        surface.blit(prescaled_source, (pos_x, pos_y))
        surface.blit(self._get_darken_overlay((window_w, window_h)), (0, 0))

    def draw_small_cover(self, surface: pygame.Surface, pos: tuple, palette: dict):
        """Рисует маленькую квадратную обложку (со скруглением) в указанной
        позиции — используется рядом с названием трека, когда у пакета есть видео."""
        if self._small_cover_image is None:
            return
        rect = self._small_cover_image.get_rect(topleft=pos)
        pygame.draw.rect(surface, palette["button_small_border"], rect.inflate(4, 4), width=1, border_radius=8)
        surface.blit(self._small_cover_image, pos)
