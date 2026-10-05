"""Тестовый запуск WoW через встроенный Wine на Apple Silicon."""
from pathlib import Path
import subprocess

from config import app_bundle_path
from core.macos_setup import prepare_game_config, wine_environment, prepare_wine_prefix


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
    prepare_game_config(game_dir)
    env = wine_environment(resources, game_dir)
    # Wine сам создаёт префикс при первом запуске. Журнал остаётся рядом с игрой.
    with open(Path(game_dir) / ".dreamworld-wine.log", "ab") as log:
        prepare_wine_prefix(resources, game_dir, env, log)
        process = subprocess.Popen([str(wine), str(Path(executable).resolve()), "-d3d9"],
                                   cwd=game_dir, env=env, stdout=log, stderr=log)
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return
    if code != 0:
        raise RuntimeError("Wine завершился с ошибкой. Проверьте Rosetta 2 и журнал .dreamworld-wine.log в папке клиента.")
