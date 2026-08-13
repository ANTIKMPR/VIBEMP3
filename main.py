"""
VIBEMP3 — главный модуль приложения.

Открывает окно с плеером и визуализатором. Музыка добавляется
через кнопки в интерфейсе (диалоги выбора файлов/папки), без
консольных аргументов.

Обычно этот файл не запускают напрямую — используй run.py,
который сначала проверит, что все зависимости установлены.
Но напрямую (`python main.py`) он тоже работает.
"""

import os
import sys
import pygame

from audio_engine import AudioEngine
from visualizer import Visualizer
from settings import Settings, THEMES as THEME_PALETTES, get_windows_system_theme
from settings_panel import SettingsPanel
from theme_transition import ThemeTransition
import logo_theme
import app_font
import button_icons
import ui


APP_NAME = "VIBEMP3"

WINDOW_WIDTH = 760
WINDOW_HEIGHT = 712
FPS = 60

# Ресурсы (логотип, иконка, шрифт, themes/, settings.json) должны лежать
# рядом с исполняемым файлом — что при обычном запуске (`python main.py`
# / run.bat), что после сборки в один exe через PyInstaller.
#
# Наивный os.path.dirname(__file__) ломается в PyInstaller-однофайловой
# сборке: на время исполнения PyInstaller распаковывает всё во временную
# папку (sys._MEIPASS) и __file__ указывает именно туда, а не туда, где
# реально лежит exe рядом с папкой resources/. Поэтому:
#   - если приложение запущено как PyInstaller-сборка (проверяем через
#     sys.frozen, стандартный флаг, который PyInstaller выставляет сам),
#     берём папку, где лежит сам .exe (sys.executable);
#   - иначе (обычный запуск python-скриптом) — как раньше, папка со
#     скриптом main.py.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOGO_PATH = os.path.join(BASE_DIR, "resources", "logo", "BigLogo.png")
ICON_PATH = os.path.join(BASE_DIR, "resources", "logo", "icon.ico")

# Логотип занимает ~3/5 ширины окна, высота считается из его реальных
# пропорций (исходник 2000x330), чтобы не искажать картинку.
LOGO_WIDTH = int(WINDOW_WIDTH * 0.6)
LOGO_SOURCE_ASPECT = 330 / 2000
LOGO_HEIGHT = int(LOGO_WIDTH * LOGO_SOURCE_ASPECT)


def pick_symbol_font(size: int) -> pygame.font.Font:
    """
    Ищет системный шрифт, который реально умеет рисовать ▶ и ⏸
    (обычные текстовые шрифты вроде Arial часто не содержат эти глифы
    и рисуют пустой "квадратик" вместо символа).

    Пробует по очереди несколько шрифтов, доступных на Windows/macOS/Linux,
    и проверяет через metrics(), что символ действительно поддерживается.
    Если ни один не подошёл — возвращает Arial как раньше (тогда в draw()
    сработает ASCII-фолбэк на "> " / "||").
    """
    candidates = [
        "segoeuisymbol",  # Windows — самый надёжный вариант для символов
        "segoeuiemoji",   # Windows — emoji-версии тех же символов
        "applesymbols",   # macOS
        "notosanssymbols",  # Linux (Noto)
        "dejavusans",     # Linux — часто есть базовые символы
    ]

    for name in candidates:
        try:
            f = pygame.font.SysFont(name, size)
            metrics = f.metrics("▶⏸")
            # metrics() возвращает None для символа, которого нет в шрифте
            if metrics and all(m is not None for m in metrics):
                return f
        except Exception:
            continue

    return pygame.font.SysFont("Arial", size)


def load_app_icon():
    """
    Загружает .ico для иконки приложения. Возвращает Surface или None,
    если файл не найден/битый — тогда просто останется иконка по умолчанию.

    Пробуем сначала через Pillow: встроенный ICO-декодер pygame (SDL_image)
    умеет читать не все варианты .ico (некоторые внутренние BMP-кодировки
    ICO-контейнера ему не по зубам — "Unsupported ICO bitmap format"),
    а Pillow справляется почти всегда. Если Pillow недоступна — пробуем
    напрямую через pygame как запасной вариант.
    """
    try:
        from PIL import Image
        img = Image.open(ICON_PATH).convert("RGBA")
        return pygame.image.frombuffer(img.tobytes(), img.size, "RGBA")
    except ImportError:
        pass  # Pillow не установлена — попробуем через pygame напрямую
    except Exception as e:
        print(f"[VIBEMP3] Pillow не смогла прочитать иконку ({ICON_PATH}): {e}")

    try:
        return pygame.image.load(ICON_PATH)
    except Exception as e:
        print(f"[VIBEMP3] Не удалось загрузить иконку приложения ({ICON_PATH}): {e}")
        return None


def load_logo(theme: str = "dark"):
    """
    Загружает и масштабирует логотип под LOGO_WIDTH x LOGO_HEIGHT.
    Для светлой темы автоматически берётся (и при необходимости генерируется)
    инвертированная по яркости версия — см. logo_theme.py.
    Возвращает Surface или None, если файла нет — тогда рисуется текстовый
    фолбэк "VIBEMP3" вместо картинки.
    """
    path = logo_theme.get_logo_path_for_theme(LOGO_PATH, theme)
    try:
        raw = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(raw, (LOGO_WIDTH, LOGO_HEIGHT))
    except Exception as e:
        print(f"[VIBEMP3] Не удалось загрузить логотип ({path}): {e}")
        return None


def pick_folder() -> str | None:
    """Открывает системный диалог выбора папки. Возвращает путь или None, если отменено."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)  # чтобы диалог не прятался за окно плеера
    folder = filedialog.askdirectory(title="Выбери папку с mp3-файлами")
    root.destroy()
    return folder or None


def pick_files() -> list[str]:
    """Открывает системный диалог выбора одного или нескольких mp3-файлов."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    files = filedialog.askopenfilenames(
        title="Выбери mp3-файлы",
        filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")],
    )
    root.destroy()
    return list(files)


def main():
    pygame.init()

    # Иконку приложения нужно ставить ДО set_mode() — иначе на некоторых
    # системах (особенно Windows) она не применится к уже созданному окну.
    icon_surface = load_app_icon()
    if icon_surface is not None:
        pygame.display.set_icon(icon_surface)

    pygame.display.set_caption(APP_NAME)
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    font = app_font.get_font(BASE_DIR, 16)
    font_small = app_font.get_font(BASE_DIR, 13)
    font_title = app_font.get_font(BASE_DIR, 20, bold=True)
    font_logo_fallback = app_font.get_font(BASE_DIR, 30, bold=True)  # если BigLogo.png не найден
    font_transport = pick_symbol_font(20)  # для ▶/⏸ — кастомный шрифт их не содержит, нужен системный

    engine = AudioEngine()
    toast = ui.Toast()

    settings = Settings(BASE_DIR)
    settings.load()
    engine.set_volume(settings.volume)  # восстанавливаем громкость, которую пользователь поставил в прошлый раз
    engine.repeat_mode = settings.repeat_mode  # восстанавливаем режим повтора
    engine.set_crossfade_sec(settings.crossfade_sec)  # применяем сохранённое время кроссфейда

    settings_panel = SettingsPanel()
    theme_transition = ThemeTransition()

    # Логотип грузим после set_mode (convert_alpha() требует созданный дисплей)
    # и после загрузки settings — под сохранённую тему сразу подставляется
    # правильная (тёмная/светлая) версия картинки.
    logo_surface = load_logo(settings.effective_theme())
    logo_theme_loaded = settings.effective_theme()

    # Если тема настроена как "system" — приложение периодически проверяет
    # реестр Windows и подхватывает смену темы даже без открытия настроек.
    last_checked_system_theme = get_windows_system_theme()
    system_theme_check_interval_ms = 3000
    last_system_theme_check_at = pygame.time.get_ticks()

    # Восстанавливаем плейлист из последней запомненной папки, если она ещё существует
    if settings.last_folder and os.path.isdir(settings.last_folder):
        engine.load_folder(settings.last_folder)

    # --- Разметка UI (сверху вниз) ---

    logo_x, logo_y = 30, 16
    logo_bottom = logo_y + LOGO_HEIGHT

    # Панель инструментов — под логотипом. Кнопка настроек (⚙) — крайняя справа,
    # "Очистить" сдвинута левее неё.
    toolbar_y = logo_bottom + 14
    btn_settings = ui.Button(pygame.Rect(WINDOW_WIDTH - 30 - 40, toolbar_y, 40, 32), "⚙", small=True)
    btn_clear = ui.Button(pygame.Rect(WINDOW_WIDTH - 30 - 40 - 10 - 90, toolbar_y, 90, 32), "Очистить", small=True)
    btn_add_folder = ui.Button(pygame.Rect(30, toolbar_y, 130, 32), "+ Папка", small=True)
    btn_add_files = ui.Button(pygame.Rect(170, toolbar_y, 130, 32), "+ Файлы", small=True)
    toolbar_bottom = toolbar_y + 32

    viz_rect = pygame.Rect(30, toolbar_bottom + 20, WINDOW_WIDTH - 60, 190)
    visualizer = Visualizer(viz_rect, num_bars=48)

    progress_bar = ui.ProgressBar(pygame.Rect(30, viz_rect.bottom + 20, WINDOW_WIDTH - 60, 8))
    time_y = progress_bar.rect.bottom + 4
    title_y = time_y + 30

    button_y = title_y + 38
    btn_prev = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 - 90, button_y, 50, 40), "<<")
    btn_play = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 - 25, button_y, 50, 40), "▶")
    btn_next = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 + 40, button_y, 50, 40), ">>")
    # Кнопка повтора — компактная, сразу справа от "След. трек". Текст на ней
    # отражает режим: пусто/REP при off, REP при all, REP1 при one (см. ниже,
    # обновляется в цикле отрисовки через settings.t не завязано — это иконка,
    # а не переводимый текст, поэтому короткие ASCII-метки одинаковы для RU/EN).
    btn_repeat = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 + 100, button_y + 4, 34, 32), "REP", small=True)
    button_bottom = button_y + 40

    TRANSPORT_ICON_SIZE = 22

    def refresh_transport_icons(effective_theme: str):
        """Перезагружает PNG-иконки транспортных кнопок под указанную тему.
        Если файла нет — icon остаётся None, и Button.draw() откатится на текст."""
        btn_prev.icon = button_icons.get_icon(BASE_DIR, "prev", effective_theme, TRANSPORT_ICON_SIZE)
        btn_next.icon = button_icons.get_icon(BASE_DIR, "next", effective_theme, TRANSPORT_ICON_SIZE)
        btn_play.icon = button_icons.get_icon(BASE_DIR, "play", effective_theme, TRANSPORT_ICON_SIZE)
        btn_pause_icon = button_icons.get_icon(BASE_DIR, "pause", effective_theme, TRANSPORT_ICON_SIZE)
        return btn_pause_icon

    pause_icon = refresh_transport_icons(settings.effective_theme())
    icons_theme_loaded = settings.effective_theme()

    SETTINGS_ICON_SIZE = 20  # с запасом внутри кнопки 40x32

    def refresh_settings_icon(effective_theme: str):
        btn_settings.icon = button_icons.get_settings_icon(BASE_DIR, effective_theme, SETTINGS_ICON_SIZE)

    refresh_settings_icon(settings.effective_theme())

    # Список треков — снизу, но с местом под слайдер громкости под ним
    volume_row_height = 30
    volume_margin_top = 15
    volume_margin_bottom = 20

    track_list_y = button_bottom + 20
    track_list_height = (
        WINDOW_HEIGHT - track_list_y - volume_margin_top - volume_row_height - volume_margin_bottom
    )
    track_list_rect = pygame.Rect(30, track_list_y, WINDOW_WIDTH - 60, track_list_height)
    track_list = ui.TrackList(track_list_rect)

    # Слайдер громкости — самая нижняя строка окна
    volume_row_y = track_list_rect.bottom + volume_margin_top
    volume_label_reserved = 90
    volume_percent_reserved = 46
    volume_gap = 12

    volume_slider_x = 30 + volume_label_reserved + volume_gap
    volume_slider_width = (
        (WINDOW_WIDTH - 60) - volume_label_reserved - volume_gap * 2 - volume_percent_reserved
    )
    volume_slider = ui.VolumeSlider(
        pygame.Rect(volume_slider_x, volume_row_y + volume_row_height // 2 - 4, volume_slider_width, 8)
    )
    volume_percent_x = volume_slider.rect.right + volume_gap
    volume_text_y = volume_row_y + (volume_row_height - 16) // 2

    dragging_progress = False
    dragging_volume = False
    running = True

    def playlist_titles():
        return [os.path.splitext(os.path.basename(p))[0] for p in engine.playlist]

    def try_play_index(index: int):
        """Пытается запустить трек по индексу, показывая тост при ошибке декодирования."""
        try:
            engine.play_index(index)
        except RuntimeError as e:
            toast.show(str(e), is_error=True)

    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            # Пока открыта панель настроек — она перехватывает все события,
            # плеер под ней не реагирует на клики/клавиши (кроме QUIT выше).
            if settings_panel.is_open:
                old_effective_theme = settings.effective_theme()
                old_palette_snapshot = dict(settings.palette())
                settings_panel.handle_event(mouse_pos, event, settings)
                new_effective_theme = settings.effective_theme()
                if new_effective_theme != old_effective_theme:
                    theme_transition.start(old_palette_snapshot, THEME_PALETTES[new_effective_theme])
                    if new_effective_theme != logo_theme_loaded:
                        logo_surface = load_logo(new_effective_theme)
                        logo_theme_loaded = new_effective_theme
                    if new_effective_theme != icons_theme_loaded:
                        pause_icon = refresh_transport_icons(new_effective_theme)
                        icons_theme_loaded = new_effective_theme
                        refresh_settings_icon(new_effective_theme)
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    engine.toggle_pause()
                elif event.key == pygame.K_RIGHT:
                    err = engine.play_next()
                    if err:
                        toast.show(err, is_error=True)
                elif event.key == pygame.K_LEFT:
                    err = engine.play_prev()
                    if err:
                        toast.show(err, is_error=True)
                elif event.key == pygame.K_UP:
                    engine.set_volume(engine.get_volume() + 0.05)
                elif event.key == pygame.K_DOWN:
                    engine.set_volume(engine.get_volume() - 0.05)
                elif event.key == pygame.K_ESCAPE:
                    running = False

            elif event.type == pygame.MOUSEWHEEL:
                if track_list_rect.collidepoint(mouse_pos):
                    track_list.scroll(-event.y, len(engine.playlist))
                elif volume_slider.hit_rect().collidepoint(mouse_pos):
                    engine.set_volume(engine.get_volume() + event.y * 0.05)

            # --- Кнопки панели инструментов ---
            if btn_add_folder.is_clicked(mouse_pos, event):
                folder = pick_folder()
                if folder:
                    added = engine.add_folder(folder)
                    settings.set_last_folder(folder)
                    if added > 0:
                        toast.show(settings.t("added_tracks", n=added))
                        if engine.current_index == -1:
                            try_play_index(0)
                    else:
                        toast.show(settings.t("no_new_tracks"), is_error=True)

            if btn_add_files.is_clicked(mouse_pos, event):
                files = pick_files()
                if files:
                    added = engine.add_files(files)
                    if added > 0:
                        toast.show(settings.t("added_tracks", n=added))
                        if engine.current_index == -1:
                            try_play_index(0)
                    else:
                        toast.show(settings.t("files_already_added"), is_error=True)

            if btn_clear.is_clicked(mouse_pos, event):
                if engine.has_tracks():
                    engine.clear_playlist()
                    settings.set_last_folder(None)
                    visualizer.values[:] = 0
                    toast.show(settings.t("playlist_cleared"))

            if btn_settings.is_clicked(mouse_pos, event) and not settings_panel.is_visible:
                settings_panel.open(WINDOW_WIDTH, WINDOW_HEIGHT, BASE_DIR)

            # --- Транспортные кнопки ---
            if btn_play.is_clicked(mouse_pos, event):
                if engine.current_track is None and engine.has_tracks():
                    try_play_index(0)
                else:
                    engine.toggle_pause()

            if btn_next.is_clicked(mouse_pos, event):
                err = engine.play_next()
                if err:
                    toast.show(err, is_error=True)

            if btn_prev.is_clicked(mouse_pos, event):
                err = engine.play_prev()
                if err:
                    toast.show(err, is_error=True)

            if btn_repeat.is_clicked(mouse_pos, event):
                engine.cycle_repeat_mode()

            # --- Прогресс-бар ---
            if progress_bar.is_clicked(mouse_pos, event):
                dragging_progress = True

            # --- Слайдер громкости ---
            if volume_slider.is_clicked(mouse_pos, event):
                dragging_volume = True
                engine.set_volume(volume_slider.get_ratio_from_x(mouse_pos[0]))

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging_progress and engine.current_track:
                    ratio = progress_bar.get_ratio_from_click(mouse_pos[0])
                    engine.seek(ratio * engine.current_track.duration_sec)
                dragging_progress = False
                dragging_volume = False

            # --- Клик по списку треков ---
            action = track_list.handle_click(mouse_pos, event)
            if action:
                kind, idx = action
                if kind == "play":
                    try_play_index(idx)
                elif kind == "remove":
                    engine.remove_index(idx)

        # Живое перетаскивание слайдера громкости (обновляется каждый кадр, пока зажата кнопка)
        if dragging_volume:
            engine.set_volume(volume_slider.get_ratio_from_x(mouse_pos[0]))

        # Запоминаем текущую громкость в настройках — синхронизация раз за кадр
        # (дёшево, а изменить её можно из нескольких мест: слайдер, колёсико,
        # клавиши вверх/вниз — так не нужно дублировать set_volume в каждом из них)
        if settings.volume != engine.get_volume():
            settings.set_volume(engine.get_volume())
        if settings.repeat_mode != engine.repeat_mode:
            settings.set_repeat_mode(engine.repeat_mode)
        # Кроссфейд — обратное направление: значение меняется в панели
        # настроек (settings.crossfade_sec), а engine должен его подхватить.
        if engine.crossfade_sec != settings.crossfade_sec:
            engine.set_crossfade_sec(settings.crossfade_sec)

        settings_panel.update_drag(mouse_pos, settings)

        # Если тема настроена как "system" — периодически (не каждый кадр, чтобы
        # не дёргать реестр зря) проверяем, не сменилась ли тема Windows.
        if settings.theme == "system":
            now_ms = pygame.time.get_ticks()
            if now_ms - last_system_theme_check_at >= system_theme_check_interval_ms:
                last_system_theme_check_at = now_ms
                current_system_theme = get_windows_system_theme()
                if current_system_theme != last_checked_system_theme:
                    old_palette_snapshot = dict(settings.palette())
                    last_checked_system_theme = current_system_theme
                    theme_transition.start(old_palette_snapshot, THEME_PALETTES[current_system_theme])
                    if current_system_theme != logo_theme_loaded:
                        logo_surface = load_logo(current_system_theme)
                        logo_theme_loaded = current_system_theme
                    if current_system_theme != icons_theme_loaded:
                        pause_icon = refresh_transport_icons(current_system_theme)
                        icons_theme_loaded = current_system_theme
                        refresh_settings_icon(current_system_theme)

        # Продвигаем активный кроссфейд (если идёт) — обновляет громкости
        # затухающего/нарастающего каналов кадр за кадром.
        engine.update()

        # Авто-переход по завершении трека — учитывает repeat_mode
        # (повтор одного трека / всего плейлиста / остановка на последнем)
        if engine.is_track_finished():
            err = engine.advance_on_track_end()
            if err:
                toast.show(err, is_error=True)

        # Держим список треков проскроленным так, чтобы текущий трек был виден
        if engine.current_index >= 0:
            track_list.ensure_visible(engine.current_index, len(engine.playlist))

        # --- Обновление данных визуализации ---
        if engine.current_track and not engine.is_paused():
            fft_bins = engine.get_fft_bins(num_bins=48)
        else:
            fft_bins = visualizer.values * 0.9  # плавное затухание на паузе/без трека
        visualizer.update(fft_bins)

        # --- Отрисовка ---
        # Во время анимации перехода темы палитра плавно интерполируется между
        # старыми и новыми цветами; вне анимации это просто settings.palette().
        palette = theme_transition.get_palette(settings.palette())
        screen.fill(palette["bg"])

        # Логотип (или текстовый фолбэк, если файл не найден)
        if logo_surface is not None:
            screen.blit(logo_surface, (logo_x, logo_y))
        else:
            fallback_surf = font_logo_fallback.render(APP_NAME, True, palette["text"])
            screen.blit(fallback_surf, (logo_x, logo_y + LOGO_HEIGHT // 2 - fallback_surf.get_height() // 2))

        btn_add_folder.label = settings.t("add_folder")
        btn_add_files.label = settings.t("add_files")
        btn_clear.label = settings.t("clear")
        btn_add_folder.handle_hover(mouse_pos)
        btn_add_files.handle_hover(mouse_pos)
        btn_clear.handle_hover(mouse_pos)
        btn_settings.handle_hover(mouse_pos)
        btn_add_folder.draw(screen, font_small, palette)
        btn_add_files.draw(screen, font_small, palette)
        btn_clear.draw(screen, font_small, palette)
        btn_settings.draw(screen, font_transport, palette)

        visualizer.set_theme_colors(palette["text"], palette.get("viz_wave", palette["accent"]))
        visualizer.draw(screen)

        progress_ratio = 0.0
        if engine.current_track and engine.current_track.duration_sec > 0:
            progress_ratio = engine.get_position_sec() / engine.current_track.duration_sec
        progress_bar.draw(screen, progress_ratio, palette)

        pos_text = ui.format_time(engine.get_position_sec())
        dur_text = ui.format_time(engine.current_track.duration_sec if engine.current_track else 0)
        time_surf = font_small.render(f"{pos_text} / {dur_text}", True, palette["text_dim"])
        screen.blit(time_surf, (30, time_y))

        title = engine.current_track.title if engine.current_track else settings.t("no_track")
        title_surf = font_title.render(title, True, palette["text"])
        # Обрезаем заголовок, если он шире окна, чтобы не вылезал за край
        max_title_width = WINDOW_WIDTH - 60
        if title_surf.get_width() > max_title_width:
            while title and font_title.size(title + "…")[0] > max_title_width:
                title = title[:-1]
            title_surf = font_title.render(title + "…", True, palette["text"])
        screen.blit(title_surf, (30, title_y))

        is_playing = bool(engine.current_track and not engine.is_paused())
        btn_play.label = "⏸" if is_playing else "▶"
        btn_play.icon = pause_icon if is_playing else button_icons.get_icon(BASE_DIR, "play", icons_theme_loaded, TRANSPORT_ICON_SIZE)
        btn_prev.handle_hover(mouse_pos)
        btn_play.handle_hover(mouse_pos)
        btn_next.handle_hover(mouse_pos)
        btn_repeat.handle_hover(mouse_pos)
        btn_prev.draw(screen, font_transport, palette)
        btn_play.draw(screen, font_transport, palette)
        btn_next.draw(screen, font_transport, palette)

        # Кнопка повтора: подпись отражает режим (REP выкл/включен, REP1 для
        # повтора одного трека), а активный (не "off") режим подсвечивается
        # акцентным цветом текста, чтобы было видно с первого взгляда.
        if engine.repeat_mode == "one":
            btn_repeat.label = "REP1"
        else:
            btn_repeat.label = "REP"
        repeat_active = engine.repeat_mode != "off"
        btn_repeat.draw(screen, font_small, palette)
        if repeat_active and not btn_repeat.hovered:
            # Button.draw уже нарисовала фон/текст обычным цветом — поверх
            # рисуем тонкую акцентную рамку, чтобы показать "включено", не
            # трогая саму реализацию Button (которая не знает про repeat_mode).
            pygame.draw.rect(screen, palette["accent"], btn_repeat.rect, width=2, border_radius=6)

        track_list.draw(
            screen, font_small, playlist_titles(), engine.current_index, mouse_pos,
            palette, settings.t("playlist_empty"),
        )

        # Слайдер громкости
        volume_label_surf = font_small.render(settings.t("volume"), True, palette["text_dim"])
        screen.blit(volume_label_surf, (30, volume_text_y))
        volume_slider.draw(screen, engine.get_volume(), palette)
        volume_percent_surf = font_small.render(f"{round(engine.get_volume() * 100)}%", True, palette["text_dim"])
        screen.blit(volume_percent_surf, (volume_percent_x, volume_text_y))

        toast.draw(screen, font_small, WINDOW_WIDTH, WINDOW_HEIGHT, palette)

        # Панель настроек рисуется последней — поверх всего остального в кадре.
        # Ей передаётся "чистый" снимок текущего кадра плеера (для параллакс-фона):
        # снимок берём именно сейчас, пока screen ещё не перезаписан оверлеем панели.
        if settings_panel.is_visible:
            player_snapshot = screen.copy()
            settings_panel.draw(screen, mouse_pos, settings, palette, background_snapshot=player_snapshot)

        pygame.display.flip()
        clock.tick(FPS)

    settings.save()
    pygame.quit()


if __name__ == "__main__":
    main()
