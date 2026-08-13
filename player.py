"""
Минималистичный MP3-плеер с реалтайм визуализатором.

Запуск:
    python player.py /путь/к/папке/с/mp3

Если папка не указана — берётся ./tracks (создай её и положи mp3 внутрь).

Требует установленный ffmpeg в системе (нужен pydub для декодирования mp3).
"""

import sys
import os
import pygame

from audio_engine import AudioEngine
from visualizer import Visualizer
import ui


WINDOW_WIDTH = 720
WINDOW_HEIGHT = 480
FPS = 60


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "./tracks"

    if not os.path.isdir(folder):
        print(f"Папка не найдена: {folder}")
        print("Создай папку с mp3-файлами и передай путь к ней первым аргументом:")
        print("    python player.py /путь/к/папке")
        sys.exit(1)

    pygame.init()
    pygame.display.set_caption("MP3 Player")
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Arial", 16)
    font_small = pygame.font.SysFont("Arial", 13)
    font_title = pygame.font.SysFont("Arial", 20, bold=True)

    engine = AudioEngine()
    engine.load_folder(folder)

    if not engine.has_tracks():
        print(f"В папке {folder} не найдено mp3-файлов.")
        sys.exit(1)

    engine.play_index(0)

    # --- Разметка UI ---
    viz_rect = pygame.Rect(30, 30, WINDOW_WIDTH - 60, 200)
    visualizer = Visualizer(viz_rect, num_bars=48)

    progress_bar = ui.ProgressBar(pygame.Rect(30, 250, WINDOW_WIDTH - 60, 8))

    button_y = 280
    btn_prev = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 - 90, button_y, 50, 40), "<<")
    btn_play = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 - 25, button_y, 50, 40), "II")
    btn_next = ui.Button(pygame.Rect(WINDOW_WIDTH // 2 + 40, button_y, 50, 40), ">>")

    track_list_rect = pygame.Rect(30, 340, WINDOW_WIDTH - 60, 120)
    playlist_titles = [
        os.path.splitext(os.path.basename(p))[0] for p in engine.playlist
    ]

    dragging_progress = False
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    engine.toggle_pause()
                elif event.key == pygame.K_RIGHT:
                    engine.play_next()
                elif event.key == pygame.K_LEFT:
                    engine.play_prev()
                elif event.key == pygame.K_ESCAPE:
                    running = False

            if btn_play.is_clicked(mouse_pos, event):
                engine.toggle_pause()
            if btn_next.is_clicked(mouse_pos, event):
                engine.play_next()
            if btn_prev.is_clicked(mouse_pos, event):
                engine.play_prev()

            if progress_bar.is_clicked(mouse_pos, event):
                dragging_progress = True

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging_progress and engine.current_track:
                    ratio = progress_bar.get_ratio_from_click(mouse_pos[0])
                    engine.seek(ratio * engine.current_track.duration_sec)
                dragging_progress = False

        # Авто-переход к следующему треку по завершении
        if engine.is_track_finished():
            engine.play_next()

        # --- Обновление данных визуализации ---
        if not engine.is_paused():
            fft_bins = engine.get_fft_bins(num_bins=48)
        else:
            fft_bins = visualizer.values * 0.9  # плавное затухание на паузе
        visualizer.update(fft_bins)

        # --- Отрисовка ---
        screen.fill(ui.BG_COLOR)

        visualizer.draw(screen)

        progress_ratio = 0.0
        if engine.current_track and engine.current_track.duration_sec > 0:
            progress_ratio = engine.get_position_sec() / engine.current_track.duration_sec
        progress_bar.draw(screen, progress_ratio)

        # Время
        pos_text = ui.format_time(engine.get_position_sec())
        dur_text = ui.format_time(engine.current_track.duration_sec if engine.current_track else 0)
        time_surf = font_small.render(f"{pos_text} / {dur_text}", True, ui.TEXT_DIM)
        screen.blit(time_surf, (30, 262))

        # Название трека
        title = engine.current_track.title if engine.current_track else "—"
        title_surf = font_title.render(title, True, ui.TEXT_COLOR)
        screen.blit(title_surf, (30, 300))

        # Кнопки
        btn_play.label = "II" if not engine.is_paused() else "▶"
        for btn in (btn_prev, btn_play, btn_next):
            btn.handle_hover(mouse_pos)
            btn.draw(screen, font)

        # Список треков
        ui.draw_track_list(screen, font_small, playlist_titles, engine.current_index, track_list_rect)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
