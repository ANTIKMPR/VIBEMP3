"""
crash_guard.py — защита от «тихих» вылетов при запуске.

Как подключить: положи файл рядом с run.py и добавь ПЕРВОЙ строкой в run.py:

    import crash_guard

Что делает:
  1. Переводит stdout/stderr в UTF-8 — на русской Windows по умолчанию cp1251,
     и символы вроде ✓ / ➜ роняют print() с UnicodeEncodeError.
  2. Любая необработанная ошибка (в том числе в потоках) пишется в
     %LOCALAPPDATA%\\VIBEMP3\\crash.log, а при вылете основного потока
     показывается окошко с текстом ошибки.
"""

import os
import platform
import sys
import threading
import traceback

APP_NAME = "VIBEMP3"


def _fix_streams():
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, APP_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "crash.log")


def _header() -> str:
    return (
        f"Python {sys.version}\n"
        f"Platform: {platform.platform()}\n"
        f"Executable: {sys.executable}\n"
        f"Frozen: {getattr(sys, 'frozen', False)}\n"
        f"Args: {sys.argv}\n"
        + "-" * 60 + "\n"
    )


def _write_log(text: str, append: bool = False):
    try:
        with open(_log_path(), "a" if append else "w", encoding="utf-8") as f:
            f.write(_header() + text + "\n")
    except Exception:
        pass


def _show_box(text: str):
    if os.name != "nt":
        return
    try:
        import ctypes
        msg = f"{text[-1400:]}\n\nПолный текст: {_log_path()}"
        ctypes.windll.user32.MessageBoxW(0, msg, f"{APP_NAME} - ошибка", 0x10)
    except Exception:
        pass


def _main_hook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        return
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    _write_log(text)
    _show_box(text)
    try:
        sys.__excepthook__(exc_type, exc, tb)
    except Exception:
        pass


def _thread_hook(args):
    text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    _write_log(f"[поток {getattr(args.thread, 'name', '?')}]\n{text}", append=True)


_fix_streams()
sys.excepthook = _main_hook
threading.excepthook = _thread_hook
