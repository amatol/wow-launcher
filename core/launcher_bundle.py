"""Установка второй версии лаунчера рядом с клиентом, без изменения префикса."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import zipfile

from updater.net_utils import download_with_retries


class UpdateCancelled(RuntimeError):
    """Отмена до переключения установленной версии."""


def check_cancelled(cancel_check):
    if cancel_check and cancel_check():
        raise UpdateCancelled("Обновление отменено.")


def extract_app(archive, destination, cancel_check=None):
    """Распаковать только Dreamworld.app, сохранив права и внутренние symlink."""
    root = Path(destination).resolve()
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        links = []
        seen = set()
        for item in members:
            check_cancelled(cancel_check)
            path = PurePosixPath(item.filename)
            if (not path.parts or path.parts[0] != "Dreamworld.app" or
                    path.is_absolute() or ".." in path.parts or "\\" in item.filename):
                raise ValueError("Недопустимый путь в архиве macOS")
            if str(path) in seen:
                raise ValueError("Повторяющийся путь в архиве")
            seen.add(str(path))
            target = root.joinpath(*path.parts)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = source.read(item).decode("utf-8")
                resolved = (target.parent / link).resolve()
                app = root / "Dreamworld.app"
                if not resolved.is_relative_to(app):
                    raise ValueError("Ссылка выходит за пределы Dreamworld.app")
                links.append((target, link))
                continue
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(item) as incoming, target.open("wb") as outgoing:
                    while chunk := incoming.read(1024 * 1024):
                        check_cancelled(cancel_check)
                        outgoing.write(chunk)
                target.chmod((mode & 0o777) or 0o644)
        # Ссылки создаём последними: файлы не могут записываться через них.
        for target, link in links:
            check_cancelled(cancel_check)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(link)
    binary = root / "Dreamworld.app/Contents/MacOS/Dreamworld"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("Архив не содержит исполняемый Dreamworld.app")
    return root / "Dreamworld.app"


def install_app(archive, game_dir, cancel_check=None):
    """Атомарно заменить бандл; при ошибке вернуть прежнюю версию."""
    game_dir = Path(game_dir)
    with tempfile.TemporaryDirectory(prefix=".dreamworld-app-", dir=game_dir) as staging:
        app = extract_app(archive, staging, cancel_check)
        check_cancelled(cancel_check)
        target = game_dir / "Dreamworld.app"
        old = game_dir / "Dreamworld.app.old"
        if old.exists():
            shutil.rmtree(old)
        if target.exists():
            target.rename(old)
        try:
            app.rename(target)
        except Exception:
            if old.exists() and not target.exists():
                old.rename(target)
            raise
        if old.exists():
            shutil.rmtree(old)
    return target


def _companion(raw):
    platform = "windows" if sys.platform == "darwin" else "macos"
    return platform, raw.get("launchers", {}).get(platform)


def companion_needed(raw, game_dir):
    platform, entry = _companion(raw)
    if not entry:
        return False
    target = Path(game_dir) / ("Dreamworld.exe" if platform == "windows" else "Dreamworld.app")
    state = Path(game_dir) / ".dreamworld-launchers.json"
    try:
        installed = json.loads(state.read_text())
        if not target.exists() or installed.get(platform) != entry["sha256"]:
            return True
        if platform == "windows":
            return hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]
        return not (target / "Contents/MacOS/Dreamworld").is_file()
    except (OSError, ValueError, KeyError):
        return True


def sync_companion(raw, game_dir, progress_cb=None, cancel_check=None):
    check_cancelled(cancel_check)
    platform, entry = _companion(raw)
    if not entry or not companion_needed(raw, game_dir):
        return
    if (not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))) or
            not isinstance(entry.get("size"), int) or entry["size"] <= 0 or
            not str(entry.get("download_url", "")).startswith("https://")):
        raise ValueError("Некорректные метаданные второго лаунчера")
    with tempfile.TemporaryDirectory(prefix=".dreamworld-launchers-", dir=game_dir) as staging:
        archive = Path(staging) / "download"
        name = "Windows" if platform == "windows" else "macOS"
        def progress(done, total, message):
            if progress_cb:
                progress_cb(done, total, f"Лаунчер {name}: {message}")
        progress(0, entry["size"], "скачивание")
        ok, error = download_with_retries(entry["download_url"], str(archive),
                                         entry["size"], entry["sha256"], max_retries=3,
                                         progress_cb=progress, cancel_check=cancel_check)
        check_cancelled(cancel_check)
        if not ok:
            raise RuntimeError("Не удалось загрузить второй лаунчер: " + str(error))
        progress(0, 0, "установка")
        check_cancelled(cancel_check)
        if platform == "macos":
            install_app(archive, game_dir, cancel_check)
        else:
            os.replace(archive, Path(game_dir) / "Dreamworld.exe")
        state_path = Path(game_dir) / ".dreamworld-launchers.json"
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        state[platform] = entry["sha256"]
        temporary = Path(staging) / "state.json"
        temporary.write_text(json.dumps(state), encoding="utf-8")
        os.replace(temporary, state_path)
