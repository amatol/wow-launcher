"""Тестовый запуск WoW через встроенный Wine на Apple Silicon."""
import os
from pathlib import Path
import subprocess
import sys

from config import app_bundle_path


def launch_wow_macos(executable, game_dir):
    bundle = app_bundle_path()
    if not bundle:
        raise RuntimeError("Запуск Wine доступен из собранного Dreamworld.app.")
    resources = Path(bundle) / "Contents/Resources"
    runtime = resources / "Wine"
    wine = runtime / "bin/wine"
    rosetta = resources / "Patching/rosettax87/rosettax87"
    if not wine.is_file() or not rosetta.is_file():
        raise RuntimeError("В бандле отсутствует Wine или RosettaX87. Скачайте Dreamworld.app заново.")
    # Не наследовать чужой префикс и win32: встроенный runtime использует WoW64.
    env = os.environ.copy()
    env.pop("WINEARCH", None)
    env.pop("X87_SIDECAR_PATH", None)
    env["WINEPREFIX"] = str(Path(game_dir).resolve() / ".dreamworld-wine")
    env["ROSETTA_X87_PATH"] = str(rosetta)
    env["DYLD_LIBRARY_PATH"] = str(runtime / "lib/external")
    env["WINE_LARGE_ADDRESS_AWARE"] = "1"
    env["WINEDEBUG"] = "-all"
    env["WINEDLLOVERRIDES"] = "d3d9=b"
    # Wine сам создаёт префикс при первом запуске. Журнал остаётся рядом с игрой.
    with open(Path(game_dir) / ".dreamworld-wine.log", "ab") as log:
        process = subprocess.Popen([str(wine), str(Path(executable).resolve()), "-d3d9"],
                                   cwd=game_dir, env=env, stdout=log, stderr=log)
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return
    if code != 0:
        raise RuntimeError("Wine завершился с ошибкой. Проверьте Rosetta 2 и журнал .dreamworld-wine.log в папке клиента.")
