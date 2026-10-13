"""Миграция после прекращения поддержки macOS; второй лаунчер не скачивается."""
from pathlib import Path
import re
import shutil


# Только служебные объекты Dreamworld в корне выбранного клиента.
RETIRED_NAMES = (
    'Dreamworld.app', 'Dreamworld.app.old', 'Dreamworld.app.zip',
    'Dreamworld-mac.zip', '.dreamworld-wine', '.dreamworld-wine.log',
    '.dreamworld-wine.lock', '.dreamworld-launchers.json',
)
STAGING = re.compile(r'\.dreamworld-(?:app|launchers)-[a-z0-9_]{8}')


class UpdateCancelled(RuntimeError):
    """Обновление отменено пользователем."""


def retired_paths(game_dir):
    root = Path(game_dir)
    if not root.is_dir():
        return []
    return [p for p in root.iterdir()
            if p.name in RETIRED_NAMES or STAGING.fullmatch(p.name)]


def cleanup_retired_macos(game_dir, cancel_check=None):
    """Удалить только компоненты Mac, не переходя по ссылкам в другие папки."""
    removed = 0
    for path in retired_paths(game_dir):
        if cancel_check and cancel_check():
            raise UpdateCancelled('Обновление отменено.')
        # shutil.rmtree не обходит symlink и Windows junction (Python >= 3.8).
        if path.is_symlink() or not path.is_dir():
            path.unlink()
        else:
            shutil.rmtree(path)
        removed += 1
    return removed


def companion_needed(raw, game_dir):
    """Совместимое имя для проверки: осталось ли что-нибудь от macOS."""
    return bool(retired_paths(game_dir))


def sync_companion(raw, game_dir, progress_cb=None, cancel_check=None):
    """Старая точка обновления теперь только очищает снятую платформу."""
    if cancel_check and cancel_check():
        raise UpdateCancelled('Обновление отменено.')
    if progress_cb and retired_paths(game_dir):
        progress_cb(0, 0, 'Удаление устаревших компонентов macOS…')
    cleanup_retired_macos(game_dir, cancel_check)
