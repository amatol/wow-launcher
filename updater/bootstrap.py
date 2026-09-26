"""Первоначальная установка клиента из публичного архива Яндекс Диска."""
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path
from typing import Callable

import requests

from config import Config


ProgressCallback = Callable[[int, int, str], None]


def resolve_yandex_download(public_url: str) -> tuple[str, int]:
    """Получить временную прямую ссылку и известный Яндексу размер файла."""
    metadata = requests.get(
        "https://cloud-api.yandex.net/v1/disk/public/resources",
        params={"public_key": public_url},
        timeout=Config.HTTP_TIMEOUT,
    )
    metadata.raise_for_status()
    data = metadata.json()
    if data.get("type") != "file":
        raise ValueError("Ссылка Яндекс Диска должна указывать на один ZIP-файл")
    name = str(data.get("name", ""))
    if not name.lower().endswith(".zip"):
        raise ValueError("Базовый клиент должен быть ZIP-архивом")
    size = int(data.get("size", 0))
    if size <= 0:
        raise ValueError("Яндекс Диск не сообщил размер архива")

    response = requests.get(
        Config.YANDEX_DOWNLOAD_API_URL,
        params={"public_key": public_url},
        timeout=Config.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    href = response.json().get("href")
    if not isinstance(href, str) or not href.startswith("https://"):
        raise ValueError("Яндекс Диск не вернул ссылку для скачивания")
    return href, size


class BootstrapInstaller:
    """Докачать, проверить структуру и распаковать базовый клиент."""

    ARCHIVE_NAME = ".dreamworld_client.zip.part"
    SOURCE_NAME = ".dreamworld_client.source.json"
    STAGING_NAME = ".dreamworld_client_extract"
    INCOMPLETE_NAME = ".dreamworld_bootstrap_incomplete"

    def __init__(self, game_dir: str, progress_cb: ProgressCallback = None):
        self.game_dir = Path(game_dir).resolve()
        self.progress_cb = progress_cb or (lambda *args: None)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def install(self, public_url: str) -> tuple[bool, str]:
        archive = self.game_dir / self.ARCHIVE_NAME
        staging = self.game_dir / self.STAGING_NAME
        incomplete = self.game_dir / self.INCOMPLETE_NAME
        try:
            href, expected_size = resolve_yandex_download(public_url)
            self._prepare_archive(public_url, expected_size, archive)
            self._ensure_space(expected_size, archive)
            self._download_resumable(href, archive, expected_size)
            if self._cancel:
                return False, "Установка отменена. Загрузка сохранена для продолжения."
            self._extract(archive, staging)
            if self._cancel:
                shutil.rmtree(staging, ignore_errors=True)
                return False, "Установка отменена. Архив сохранён."
            source = self._find_client_root(staging)
            incomplete.touch()
            self._install_tree(source)
            if not self._has_client_layout(self.game_dir):
                raise ValueError("После распаковки не найдены Wow.exe и каталог Data")
            archive.unlink(missing_ok=True)
            (self.game_dir / self.SOURCE_NAME).unlink(missing_ok=True)
            shutil.rmtree(staging, ignore_errors=True)
            incomplete.unlink(missing_ok=True)
            return True, "Базовый клиент установлен. Проверка актуальности..."
        except Exception as error:
            shutil.rmtree(staging, ignore_errors=True)
            return False, f"Не удалось установить клиент: {error}"

    def _prepare_archive(self, public_url: str, expected_size: int, archive: Path):
        """Продолжать только загрузку из того же публичного источника."""
        source = self.game_dir / self.SOURCE_NAME
        identity = {"public_url": public_url, "size": expected_size}
        try:
            previous = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
        if previous != identity:
            # Старые версии не записывали источник .part: такой файл тоже
            # нельзя дополнять байтами нового архива, даже при равном размере.
            archive.unlink(missing_ok=True)
        temporary = source.with_suffix(".tmp")
        temporary.write_text(json.dumps(identity), encoding="utf-8")
        os.replace(temporary, source)

    def _ensure_space(self, expected_size: int, archive: Path):
        existing = archive.stat().st_size if archive.is_file() else 0
        required = max(0, expected_size - existing)
        free = shutil.disk_usage(self.game_dir).free
        if free < required:
            raise OSError(
                f"недостаточно места для архива: нужно ещё {required // (1024**3) + 1} ГиБ"
            )

    def _download_resumable(self, url: str, archive: Path, expected_size: int):
        current = archive.stat().st_size if archive.is_file() else 0
        if current > expected_size:
            archive.unlink()
            current = 0
        if current == expected_size:
            self.progress_cb(current, expected_size, "Архив уже скачан")
            return

        headers = {"Range": f"bytes={current}-"} if current else {}
        response = requests.get(url, headers=headers, stream=True, timeout=Config.HTTP_TIMEOUT)
        response.raise_for_status()
        if current and response.status_code != 206:
            current = 0
        mode = "ab" if current and response.status_code == 206 else "wb"
        with open(archive, mode) as output:
            for chunk in response.iter_content(chunk_size=Config.DOWNLOAD_CHUNK):
                if self._cancel:
                    return
                if chunk:
                    output.write(chunk)
                    current += len(chunk)
                    self.progress_cb(current, expected_size, "Скачивание базового клиента...")
        if current != expected_size:
            raise OSError(f"загружено {current} байт вместо {expected_size}")

    def _extract(self, archive: Path, staging: Path):
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            total = sum(member.file_size for member in members if not member.is_dir())
            free = shutil.disk_usage(self.game_dir).free
            if free < total:
                raise OSError(
                    f"недостаточно места для распаковки: требуется {total // (1024**3) + 1} ГиБ"
                )
            done = 0
            for member in members:
                if self._cancel:
                    return
                target = self._safe_member_path(staging, member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError(f"архив содержит символическую ссылку: {member.filename}")
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as src, open(target, "wb") as dst:
                    while True:
                        block = src.read(Config.DOWNLOAD_CHUNK)
                        if not block:
                            break
                        if self._cancel:
                            return
                        dst.write(block)
                        done += len(block)
                        self.progress_cb(done, total, "Распаковка базового клиента...")

    @staticmethod
    def _safe_member_path(root: Path, name: str) -> Path:
        normalized = name.replace("\\", "/")
        if not normalized or normalized.startswith("/"):
            raise ValueError(f"небезопасный путь в архиве: {name}")
        parts = normalized.rstrip("/").split("/")
        if any(part in ("", ".", "..") for part in parts) or ":" in parts[0]:
            raise ValueError(f"небезопасный путь в архиве: {name}")
        target = (root / Path(*parts)).resolve()
        if os.path.commonpath((str(root.resolve()), str(target))) != str(root.resolve()):
            raise ValueError(f"небезопасный путь в архиве: {name}")
        return target

    @classmethod
    def _find_client_root(cls, staging: Path) -> Path:
        if cls._has_client_layout(staging):
            return staging
        children = [path for path in staging.iterdir() if path.is_dir()]
        if len(children) == 1 and cls._has_client_layout(children[0]):
            return children[0]
        raise ValueError("в архиве не найдены Wow.exe и каталог Data")

    @staticmethod
    def _has_client_layout(path: Path) -> bool:
        names = {item.name.lower() for item in path.iterdir()} if path.is_dir() else set()
        return "wow.exe" in names and "data" in names and (path / next(
            item.name for item in path.iterdir() if item.name.lower() == "data"
        )).is_dir()

    def _install_tree(self, source: Path):
        for item in source.iterdir():
            if self._cancel:
                return
            if item.name.lower() == Config.LAUNCHER_EXE_NAME.lower():
                continue
            destination = self.game_dir / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)
