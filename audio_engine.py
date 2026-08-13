"""
Аудио-движок: воспроизведение mp3 через pygame.mixer + подготовка
сырых PCM-сэмплов, синхронизированных с позицией воспроизведения,
для последующего FFT-анализа в визуализаторе.

Подход: mp3 декодируется целиком в PCM один раз при загрузке трека
(через pydub/ffmpeg). Дальше во время воспроизведения мы просто
берём срез сэмплов вокруг текущей позиции проигрывания и считаем
по нему FFT — это даёт "реалтайм" картину без сложного стриминга.
"""

import os
import sys
import subprocess
import numpy as np
import pygame

# --- Подавление мелькающих консольных окон ffmpeg на Windows ---
#
# pydub декодирует mp3 через внешний ffmpeg.exe, запуская его через
# subprocess.Popen БЕЗ каких-либо флагов подавления окна. В обычном GUI-
# приложении на Windows (наш exe собран с console=False) это означает, что
# на каждый вызов AudioSegment.from_mp3() (то есть на каждое переключение
# трека — мы декодируем заранее, для кроссфейда) на долю секунды мелькает
# отдельное чёрное окно консоли ffmpeg.
#
# Чиним глобально: монки-патчим subprocess.Popen ДО импорта pydub, чтобы
# все процессы, которые pydub запускает изнутри, автоматически получали
# CREATE_NO_WINDOW. Патчим сам subprocess.Popen (а не правим pydub), чтобы
# это работало вне зависимости от версии pydub и не терялось при обновлении
# библиотеки. На не-Windows платформах ничего не делаем — там этой проблемы
# не существует, а STARTUPINFO/CREATE_NO_WINDOW там и не определены.
if sys.platform == "win32":
    _original_popen_init = subprocess.Popen.__init__

    def _patched_popen_init(self, *args, **kwargs):
        kwargs.setdefault("creationflags", 0)
        kwargs["creationflags"] |= subprocess.CREATE_NO_WINDOW
        return _original_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _patched_popen_init

from pydub import AudioSegment

try:
    from mutagen import File as mutagen_File
    from mutagen.id3 import ID3, APIC
    _MUTAGEN_AVAILABLE = True
except ImportError:
    _MUTAGEN_AVAILABLE = False


def read_track_metadata(filepath: str) -> dict:
    """
    Читает ID3-метаданные mp3-файла через mutagen: название, исполнитель,
    альбом, сырые байты обложки (если есть). Не декодирует аудио — быстрая
    операция, отдельная от полной PCM-декодировки в Track.

    Всегда возвращает словарь с этими ключами, даже если mutagen недоступен
    или файл без тегов — тогда title подставляется из имени файла, а
    остальные поля остаются None/пустыми. Так вызывающий код (плейлист,
    список альбомов) не должен отдельно проверять наличие каждого поля.
    """
    fallback_title = os.path.splitext(os.path.basename(filepath))[0]
    result = {"title": fallback_title, "artist": None, "album": None, "cover_bytes": None}

    if not _MUTAGEN_AVAILABLE:
        return result

    try:
        audio = mutagen_File(filepath)
        if audio is None:
            return result

        tags = audio.tags
        if tags is not None:
            # ID3v2 хранит текстовые теги как объекты с .text (список строк)
            if "TIT2" in tags:
                result["title"] = str(tags["TIT2"].text[0]) or fallback_title
            if "TPE1" in tags:
                result["artist"] = str(tags["TPE1"].text[0]) or None
            if "TALB" in tags:
                result["album"] = str(tags["TALB"].text[0]) or None

            # Обложка лежит в APIC-фрейме(ах); берём первую найденную
            for key in tags.keys():
                if key.startswith("APIC"):
                    result["cover_bytes"] = tags[key].data
                    break
    except Exception as e:
        print(f"[VIBEMP3] Не удалось прочитать метаданные ({filepath}): {e}")

    return result


class Track:
    """Декодированный трек: метаданные + PCM-сэмплы для анализа и воспроизведения."""

    def __init__(self, filepath: str):
        self.filepath = filepath

        meta = read_track_metadata(filepath)
        self.title = meta["title"]
        self.artist = meta["artist"]
        self.album = meta["album"]
        self.cover_bytes = meta["cover_bytes"]

        # Декодируем mp3 в PCM через pydub (использует ffmpeg под капотом).
        # Заворачиваем в понятную ошибку, чтобы GUI мог показать её пользователю,
        # а не упасть молча (частые причины: нет ffmpeg в PATH, битый файл).
        try:
            segment = AudioSegment.from_mp3(filepath)
        except Exception as e:
            raise RuntimeError(
                f"Не удалось декодировать '{self.title}'.\n"
                f"Проверь, что установлен ffmpeg и файл не повреждён.\n"
                f"Подробности: {e}"
            ) from e

        self.duration_sec = segment.duration_seconds

        # Для FFT-анализа используем моно float32 в [-1, 1] — визуализатору
        # не важна стерео-картина, а моно проще и быстрее анализировать.
        mono_segment = segment.set_channels(1)
        self.sample_rate = mono_segment.frame_rate
        mono_samples = np.array(mono_segment.get_array_of_samples(), dtype=np.float32)
        mono_max_val = float(1 << (8 * mono_segment.sample_width - 1))
        self.samples = mono_samples / mono_max_val

        # Для реального воспроизведения через pygame.mixer.Sound нужен
        # стерео 16-bit буфер — pygame.Sound не проигрывает файлы напрямую,
        # только сырые сэмплы в память (это и даёт нам возможность держать
        # два трека в двух каналах одновременно для кроссфейда, в отличие
        # от pygame.mixer.music, который умеет только один трек за раз).
        playback_segment = segment.set_channels(2).set_sample_width(2)  # 16-bit stereo
        raw_bytes = playback_segment.raw_data
        
        # Сохраняем массив как атрибут, чтобы потом отрезать от него куски при перемотке
        self.stereo_array = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)
        self.sound = pygame.sndarray.make_sound(np.ascontiguousarray(self.stereo_array))

    def get_window(self, position_sec: float, window_size: int = 2048) -> np.ndarray:
        """
        Возвращает окно сэмплов вокруг текущей позиции воспроизведения.
        Если позиция выходит за пределы трека — возвращает тишину.
        """
        center_idx = int(position_sec * self.sample_rate)
        start = max(0, center_idx - window_size // 2)
        end = start + window_size

        if start >= len(self.samples):
            return np.zeros(window_size, dtype=np.float32)

        window = self.samples[start:end]
        if len(window) < window_size:
            # Дополняем нулями, если не хватает данных (конец трека)
            window = np.pad(window, (0, window_size - len(window)))

        return window


class AudioEngine:
    """
    Аудио-движок с поддержкой кроссфейда через два независимых канала
    pygame.mixer.Channel. В отличие от pygame.mixer.music (умеет играть
    только один трек за раз), Channel+Sound позволяют держать старый и
    новый трек одновременно и плавно менять их громкость друг напротив
    друга — это и есть кроссфейд.

    В любой момент времени есть "активный" канал (тот, что считается
    current_track для целей прогресс-бара/FFT) и, во время перехода,
    "затухающий" канал со старым треком. update() должен вызываться каждый
    кадр из главного цикла — именно она продвигает плавность перехода.
    """

    NUM_CHANNELS = 2

    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
        pygame.mixer.set_num_channels(self.NUM_CHANNELS)

        self._channels = [pygame.mixer.Channel(i) for i in range(self.NUM_CHANNELS)]
        self._active_channel_idx = 0  # индекс канала, который сейчас "текущий" трек

        self.playlist: list[str] = []
        self.current_index: int = -1
        self.current_track: Track | None = None

        self._paused = False
        self._playback_offset = 0.0  # сколько секунд уже проиграно до последнего play()
        self._play_started_at = 0.0  # значение pygame.time.get_ticks() на момент старта

        self._volume = 0.7  # громкость по умолчанию (0.0..1.0)

        self.repeat_mode = "off"  # "off" | "one" | "all"
        self.crossfade_sec = 3.0  # длительность кроссфейда; настраивается через set_crossfade_sec()

        # Состояние активного перехода между треками (кроссфейда), если он идёт
        self._transition_active = False
        self._transition_started_at = 0.0
        self._fading_out_channel_idx: int | None = None  # канал со старым треком, который затихает
        self._fading_out_track: Track | None = None       # нужен, чтобы дорисовать позицию/FFT старого трека, пока он ещё звучит

        self._metadata_cache: dict[str, dict] = {}  # filepath -> {title, artist, album, cover_bytes}

    def get_metadata(self, filepath: str) -> dict:
        """
        Возвращает лёгкие метаданные файла (без полной PCM-декодировки,
        в отличие от Track()) — для отображения в списке плейлиста, где
        декодировать каждый трек целиком было бы слишком медленно.
        Результат кэшируется в памяти на время сессии.
        """
        if filepath not in self._metadata_cache:
            self._metadata_cache[filepath] = read_track_metadata(filepath)
        return self._metadata_cache[filepath]

    def set_crossfade_sec(self, seconds: float):
        """Устанавливает длительность кроссфейда между треками (в секундах). 0 = мгновенное переключение."""
        self.crossfade_sec = max(0.0, seconds)

    # ---------- Управление плейлистом ----------

    def load_folder(self, folder_path: str):
        """Загружает все mp3-файлы из папки в плейлист (заменяет текущий плейлист)."""
        files = sorted(
            f for f in os.listdir(folder_path)
            if f.lower().endswith(".mp3")
        )
        self.playlist = [os.path.join(folder_path, f) for f in files]
        self.current_index = -1

    def add_folder(self, folder_path: str) -> int:
        """Добавляет все mp3 из папки в конец текущего плейлиста. Возвращает число добавленных файлов."""
        files = sorted(
            f for f in os.listdir(folder_path)
            if f.lower().endswith(".mp3")
        )
        added = [os.path.join(folder_path, f) for f in files]
        # Не дублируем уже добавленные пути
        added = [p for p in added if p not in self.playlist]
        self.playlist.extend(added)
        return len(added)

    def add_files(self, filepaths: list[str]) -> int:
        """Добавляет отдельные mp3-файлы в конец плейлиста. Возвращает число добавленных файлов."""
        added = []
        for p in filepaths:
            # Проверяем и против уже имеющегося плейлиста, и против того, что
            # уже отобрали в этом же вызове — иначе дубль внутри filepaths
            # (например, пользователь выбрал один файл дважды) проскочит.
            if p.lower().endswith(".mp3") and p not in self.playlist and p not in added:
                added.append(p)
        self.playlist.extend(added)
        return len(added)

    def remove_index(self, index: int):
        """Удаляет трек из плейлиста по индексу. Если это текущий играющий трек — останавливает воспроизведение."""
        if not (0 <= index < len(self.playlist)):
            return

        if index == self.current_index:
            self._stop_all_channels()
            self.current_track = None
            self._paused = False
            self._playback_offset = 0.0

        del self.playlist[index]

        if index < self.current_index:
            self.current_index -= 1
        elif index == self.current_index:
            self.current_index = -1

    def clear_playlist(self):
        """Полностью очищает плейлист и останавливает воспроизведение."""
        self._stop_all_channels()
        self.playlist = []
        self.current_index = -1
        self.current_track = None
        self._paused = False
        self._playback_offset = 0.0

    def has_tracks(self) -> bool:
        return len(self.playlist) > 0

    def _stop_all_channels(self):
        for ch in self._channels:
            ch.stop()
        self._transition_active = False
        self._fading_out_channel_idx = None
        self._fading_out_track = None

    # ---------- Управление воспроизведением ----------

    def play_index(self, index: int, crossfade: bool = True):
        """
        Переключает воспроизведение на трек по индексу.

        Если crossfade=True и уже что-то играет — новый трек запускается на
        втором (неактивном) канале, и update() будет плавно сводить громкость
        старого канала к 0, а нового — к текущей self._volume, в течение
        self.crossfade_sec. Если crossfade=False, или ничего ещё не играло,
        или crossfade_sec == 0 — переключение происходит мгновенно (старое
        поведение, как раньше с pygame.mixer.music).

        Может выбросить RuntimeError (например, если файл битый или
        отсутствует ffmpeg) — вызывающий код (GUI) должен это перехватывать
        и показывать пользователю, а не давать всему приложению упасть.
        """
        if not (0 <= index < len(self.playlist)):
            return

        filepath = self.playlist[index]

        # Декодируем трек (может занять время на длинных файлах — это ок,
        # происходит один раз при переключении трека). Если не получилось —
        # не трогаем текущее состояние воспроизведения.
        track = Track(filepath)

        do_crossfade = (
            crossfade
            and self.crossfade_sec > 0
            and self.current_track is not None
            and not self._paused
            and self._channels[self._active_channel_idx].get_busy()
        )

        if do_crossfade:
            old_channel_idx = self._active_channel_idx
            new_channel_idx = 1 - self._active_channel_idx

            new_channel = self._channels[new_channel_idx]
            new_channel.set_volume(0.0)
            new_channel.play(track.sound)

            self._fading_out_channel_idx = old_channel_idx
            self._fading_out_track = self.current_track
            self._transition_active = True
            self._transition_started_at = pygame.time.get_ticks()

            self._active_channel_idx = new_channel_idx
        else:
            # Мгновенное переключение — останавливаем всё и играем на активном канале
            self._stop_all_channels()
            channel = self._channels[self._active_channel_idx]
            channel.set_volume(self._volume)
            channel.play(track.sound)

        self.current_index = index
        self.current_track = track

        self._paused = False
        self._playback_offset = 0.0
        self._play_started_at = pygame.time.get_ticks()

    def update(self):
        """
        Продвигает активный кроссфейд, если он идёт. Должна вызываться
        каждый кадр из главного цикла (main.py) — pygame.mixer.Channel не
        имеет коллбэков по времени, поэтому громкость приходится плавно
        подкручивать вручную кадр за кадром.
        """
        if not self._transition_active:
            return

        elapsed_sec = (pygame.time.get_ticks() - self._transition_started_at) / 1000.0
        t = min(1.0, elapsed_sec / self.crossfade_sec) if self.crossfade_sec > 0 else 1.0

        new_channel = self._channels[self._active_channel_idx]
        new_channel.set_volume(self._volume * t)

        if self._fading_out_channel_idx is not None:
            old_channel = self._channels[self._fading_out_channel_idx]
            old_channel.set_volume(self._volume * (1.0 - t))

        if t >= 1.0:
            # Переход завершён — глушим и освобождаем старый канал полностью
            if self._fading_out_channel_idx is not None:
                self._channels[self._fading_out_channel_idx].stop()
            self._transition_active = False
            self._fading_out_channel_idx = None
            self._fading_out_track = None

    def play_next(self, crossfade: bool = True) -> str | None:
        """Переключает на следующий трек. Возвращает текст ошибки, если декодирование не удалось, иначе None."""
        if not self.playlist:
            return None
        next_index = (self.current_index + 1) % len(self.playlist)
        try:
            self.play_index(next_index, crossfade=crossfade)
            return None
        except RuntimeError as e:
            return str(e)

    def play_prev(self, crossfade: bool = True) -> str | None:
        """Переключает на предыдущий трек. Возвращает текст ошибки, если декодирование не удалось, иначе None."""
        if not self.playlist:
            return None
        prev_index = (self.current_index - 1) % len(self.playlist)
        try:
            self.play_index(prev_index, crossfade=crossfade)
            return None
        except RuntimeError as e:
            return str(e)

    # ---------- Повтор ----------

    def cycle_repeat_mode(self) -> str:
        """Переключает режим повтора по кругу: off -> all -> one -> off. Возвращает новый режим."""
        order = ["off", "all", "one"]
        current_idx = order.index(self.repeat_mode) if self.repeat_mode in order else 0
        self.repeat_mode = order[(current_idx + 1) % len(order)]
        return self.repeat_mode

    def advance_on_track_end(self) -> str | None:
        """
        Вызывается, когда текущий трек естественно закончился (см.
        is_track_finished()), чтобы решить, что делать дальше — с учётом
        repeat_mode:
          - "one": повторяет тот же трек с начала
          - "all" (или "off", но не последний трек): переходит к следующему
          - "off" на последнем треке: останавливается, ничего не играет дальше

        Естественное завершение трека не кроссфейдит само в себя (нет смысла
        сводить трек с самим собой на стыке one), но переход между РАЗНЫМИ
        треками в конце плейлиста (all/off) использует обычный кроссфейд.
        Возвращает текст ошибки декодирования, если он произошёл, иначе None.
        """
        if not self.playlist:
            return None

        if self.repeat_mode == "one":
            try:
                self.play_index(self.current_index, crossfade=False)
                return None
            except RuntimeError as e:
                return str(e)

        is_last_track = self.current_index == len(self.playlist) - 1
        if self.repeat_mode == "off" and is_last_track:
            # Дошли до конца плейлиста без повтора — останавливаемся, а не
            # зацикливаемся молча.
            self._stop_all_channels()
            self._paused = True
            self._playback_offset = self.current_track.duration_sec if self.current_track else 0.0
            return None

        return self.play_next()

    # ---------- Пауза ----------

    def toggle_pause(self):
        if self.current_track is None:
            return

        if self._paused:
            for ch in self._channels:
                ch.unpause()
            self._play_started_at = pygame.time.get_ticks()
            self._paused = False
        else:
            for ch in self._channels:
                ch.pause()
            self._playback_offset = self.get_position_sec()
            self._paused = True

    def is_paused(self) -> bool:
        return self._paused

    # ---------- Громкость ----------

    def set_volume(self, volume: float):
        """
        Устанавливает громкость воспроизведения (0.0 — тишина, 1.0 — максимум).
        Во время активного кроссфейда громкость каналов не трогается напрямую
        (её продолжает вести update() пропорционально прогрессу перехода) —
        новое значение self._volume подхватится этим же update() на
        следующем кадре автоматически.
        """
        self._volume = max(0.0, min(1.0, volume))
        if not self._transition_active:
            self._channels[self._active_channel_idx].set_volume(self._volume)

    def get_volume(self) -> float:
        return self._volume

    def is_track_finished(self) -> bool:
        """
        Проверяет, нужно ли сейчас перейти к следующему треку (для авто-
        перехода). Если кроссфейд включён — срабатывает ЗАРАНЕЕ, за
        crossfade_sec до конца трека, чтобы старый и новый треки успели
        свестись внахлёст (иначе кроссфейдить уже нечего — трек бы успел
        полностью замолчать). Без кроссфейда (crossfade_sec == 0) поведение
        как раньше — срабатывает только когда канал физически домолчал.
        """
        if self.current_track is None or self._paused:
            return False

        # Уже идёт переход (например, кроссфейд был запущен вручную кнопкой
        # "След. трек" незадолго до конца) — новый авто-переход не нужен.
        if self._transition_active:
            return False

        active_channel = self._channels[self._active_channel_idx]
        position = self.get_position_sec()

        if self.crossfade_sec > 0 and self.current_track.duration_sec > 0:
            time_remaining = self.current_track.duration_sec - position
            if 0 < time_remaining <= self.crossfade_sec and position > 0.5:
                return True

        return not active_channel.get_busy() and position > 0.5

    # ---------- Позиция воспроизведения ----------

    def get_position_sec(self) -> float:
        """Текущая позиция воспроизведения в секундах (для активного/текущего трека)."""
        if self.current_track is None:
            return 0.0

        if self._paused:
            return self._playback_offset

        elapsed_ms = pygame.time.get_ticks() - self._play_started_at
        return self._playback_offset + elapsed_ms / 1000.0

    def seek(self, position_sec: float):
        """Перемотка на указанную позицию (в секундах)."""
        if self.current_track is None:
            return

        position_sec = max(0.0, min(position_sec, self.current_track.duration_sec))

        # Перемотка прерывает любой активный кроссфейд — не пытаемся сводить
        # позицию внутри уже затухающего канала, это не имеет смысла.
        if self._transition_active and self._fading_out_channel_idx is not None:
            self._channels[self._fading_out_channel_idx].stop()
        self._transition_active = False
        self._fading_out_channel_idx = None
        self._fading_out_track = None

        active_channel = self._channels[self._active_channel_idx]
        active_channel.stop()

        # Вычисляем, с какого сэмпла начать (секунды * частота дискретизации)
        start_index = int(position_sec * self.current_track.sample_rate)
        
        # Отрезаем нужный кусок от сохраненного стерео-массива
        sliced_array = self.current_track.stereo_array[start_index:]
        
        # Делаем из обрезка новый звук (обязательно ascontiguousarray для Pygame)
        if len(sliced_array) > 0:
            sliced_sound = pygame.sndarray.make_sound(np.ascontiguousarray(sliced_array))
            active_channel.play(sliced_sound)
            active_channel.set_volume(self._volume)

        if self._paused:
            active_channel.pause()

        self._playback_offset = position_sec
        self._play_started_at = pygame.time.get_ticks()

    # ---------- Данные для визуализации ----------

    def get_fft_bins(self, num_bins: int = 32, window_size: int = 2048) -> np.ndarray:
        """
        Возвращает массив из num_bins значений амплитуды (0..1) для
        текущей позиции воспроизведения — то, что рисует визуализатор.
        """
        if self.current_track is None:
            return np.zeros(num_bins)

        position = self.get_position_sec()
        window = self.current_track.get_window(position, window_size)

        # Оконная функция сглаживает края окна, уменьшая "просачивание" спектра
        windowed = window * np.hanning(len(window))

        fft_result = np.abs(np.fft.rfft(windowed))

        # Переводим в логарифмическую шкалу частот (низкие частоты
        # занимают меньше бинов, высокие — больше), как в примере со скрина
        freq_bins = np.logspace(0, np.log10(len(fft_result) - 1), num_bins + 1).astype(int)
        freq_bins = np.clip(freq_bins, 0, len(fft_result) - 1)

        bars = np.zeros(num_bins)
        for i in range(num_bins):
            lo, hi = freq_bins[i], max(freq_bins[i + 1], freq_bins[i] + 1)
            bars[i] = fft_result[lo:hi].mean() if hi > lo else fft_result[lo]

        # Нормализация и лёгкая компрессия (log) для приятной амплитуды
        bars = np.log1p(bars) / 6.0
        bars = np.clip(bars, 0.0, 1.0)

        return bars