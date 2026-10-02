"""
Проверка версии клиента и запуск Dreamworld (WoW).
"""
import os
import subprocess
import sys

from config import Config


def check_wow_executable() -> bool:
    """Проверить, что игровой Wow.exe существует в папке."""
    exe = Config.detect_wow_exe()
    return exe is not None


def launch_wow(exe_path: str = None) -> bool:
    """Запустить игровой Wow.exe."""
    exe = exe_path or Config.WOW_EXE
    if not exe:
        exe = Config.detect_wow_exe()
    if not exe or not os.path.isfile(exe):
        return False

    if sys.platform == "win32":
        os.startfile(exe)
    elif sys.platform == "darwin":
        from core.macos import launch_wow_macos
        launch_wow_macos(exe, Config.GAME_DIR)
    else:
        subprocess.Popen([exe], cwd=Config.GAME_DIR)
    return True


def get_current_version() -> str:
    """Вернуть текущую сохранённую версию патча."""
    return Config.get_current_version() or "неизвестно"


def set_current_version(version: str):
    Config.set_current_version(version)
