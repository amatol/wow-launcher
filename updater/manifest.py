"""
Парсинг манифеста обновлений.
Манифест — JSON с описанием файлов и версий.
"""
import json
import os
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
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        files = []
        for f in data.get("files", []):
            files.append(FileEntry(
                path=f["path"],
                size=f.get("size", 0),
                sha256=f.get("sha256", ""),
                http_url=f.get("http_url"),
                torrent_url=f.get("torrent_url"),
            ))
        return cls(
            version=data.get("version", "0"),
            files=files,
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


def filter_needed(manifest: Manifest, current_version: Optional[str]) -> List[FileEntry]:
    """
    Вернуть список файлов, которые нужно скачать/обновить.
    Если текущая версия отличается — качаем всё.
    Если версии совпадают — ничего не нужно.
    """
    if current_version is None or current_version != manifest.version:
        return list(manifest.files)
    return []


def compute_needed_files(manifest: Manifest, game_dir: str) -> List[FileEntry]:
    """
    Точечная проверка: для каждого файла из манифеста проверить размер/хэш
    на диске. Вернуть только те, которые отличаются.
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
