"""
Парсинг манифеста обновлений.
Манифест — JSON с описанием файлов и версий.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from config import Config


@dataclass
class FileEntry:
    path: str          # относительный путь внутри папки клиента
    size: int
    sha256: str
    http_url: Optional[str] = None
    torrent_url: Optional[str] = None


@dataclass
class Manifest:
    version: str
    files: List[FileEntry] = field(default_factory=list)
    removed_files: List[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        if not isinstance(data, dict):
            raise ValueError("Манифест должен быть JSON-объектом")
        version = str(data.get("version", "")).strip()
        if not version.isdigit() or len(version) != 8:
            raise ValueError("Версия манифеста должна иметь формат YYYYMMDD")
        files = []
        for f in data.get("files", []):
            path = _validate_relative_path(f["path"])
            size = int(f.get("size", 0))
            if size < 0:
                raise ValueError(f"Отрицательный размер файла: {path}")
            sha256 = str(f.get("sha256", "")).lower()
            if sha256 and not re.fullmatch(r"[0-9a-f]{64}", sha256):
                raise ValueError(f"Некорректный SHA-256: {path}")
            files.append(FileEntry(
                path=path,
                size=size,
                sha256=sha256,
                http_url=f.get("http_url"),
                torrent_url=f.get("torrent_url"),
            ))
        removed_files = [_validate_relative_path(path) for path in data.get("removed_files", [])]
        if len(removed_files) != len(set(removed_files)):
            raise ValueError("Манифест содержит повторяющиеся пути удаления")
        managed_paths = {entry.path for entry in files}
        if managed_paths.intersection(removed_files):
            raise ValueError("Файл нельзя одновременно обновлять и удалять")
        return cls(
            version=version,
            files=files,
            removed_files=removed_files,
            raw=data,
        )

    @classmethod
    def fetch(cls, url: str = None) -> "Manifest":
        url = url or Config.MANIFEST_URL
        resp = requests.get(url, timeout=Config.HTTP_TIMEOUT)
        resp.raise_for_status()
        return cls.from_dict(resp.json())

    @classmethod
    def load_local(cls, path: str) -> "Manifest":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def filter_needed(manifest: Manifest, current_version: Optional[str], game_dir: str) -> List[FileEntry]:
    """
    Вернуть список файлов, которые нужно скачать/обновить.
    Всегда проверяет существующие файлы по размеру и SHA-256.
    """
    return compute_needed_files(manifest, game_dir)


def compute_needed_files(manifest: Manifest, game_dir: str) -> List[FileEntry]:
    """
    Точечная проверка: для каждого файла из манифеста проверить размер и SHA-256
    на диске. Вернуть только те, которые отсутствуют или отличаются.
    """
    needed = []
    for entry in manifest.files:
        local_path = os.path.join(game_dir, entry.path)
        if not os.path.isfile(local_path):
            needed.append(entry)
            continue
        local_size = os.path.getsize(local_path)
        if entry.size and local_size != entry.size:
            needed.append(entry)
            continue
        if entry.sha256:
            local_hash = _sha256_file(local_path)
            if local_hash.lower() != entry.sha256.lower():
                needed.append(entry)
    return needed


def compute_existing_removed_files(manifest: Manifest, game_dir: str) -> List[str]:
    """Вернуть явно перечисленные устаревшие файлы, которые ещё есть у клиента."""
    return [
        path for path in manifest.removed_files
        if os.path.isfile(os.path.join(game_dir, path))
    ]


def remove_obsolete_files(manifest: Manifest, game_dir: str) -> int:
    """Удалить только явно перечисленные файлы и ставшие пустыми каталоги."""
    game_dir = os.path.abspath(game_dir)
    parents = set()
    removed = 0
    for relative in manifest.removed_files:
        path = os.path.abspath(os.path.join(game_dir, relative))
        if os.path.commonpath((game_dir, path)) != game_dir:
            raise ValueError(f"Небезопасный путь удаления: {relative}")
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
            parents.add(os.path.dirname(path))

    for directory in sorted(parents, key=len, reverse=True):
        while directory != game_dir:
            try:
                os.rmdir(directory)
            except OSError:
                break
            directory = os.path.dirname(directory)
    return removed


def _sha256_file(path: str, chunk: int = 65536) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _validate_relative_path(path: str) -> str:
    """Не позволить серверному манифесту писать вне папки клиента."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Пустой путь в манифесте")
    normalized = path.replace("\\", "/")
    drive, _ = os.path.splitdrive(normalized)
    parts = normalized.split("/")
    if drive or re.match(r"^[A-Za-z]:", normalized) or normalized.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Небезопасный путь в манифесте: {path}")
    return "/".join(parts)
