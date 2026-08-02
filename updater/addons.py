"""Обновление аддонов из опубликованных каталогов."""
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable, List, Optional

import requests

from config import Config


@dataclass
class AddonFile:
    path: str
    download_url: str
    sha256: str
    size: int


@dataclass
class AddonEntry:
    name: str
    version: str
    description: str = ""
    files: List[AddonFile] = field(default_factory=list)
    size: int = 0


ProgressCallback = Callable[[int, int, str], None]
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and "\\" not in value
        and path.as_posix() == value
        and not path.is_absolute()
        and ".." not in path.parts
        and all(":" not in part for part in path.parts)
    )


def _validate_entry(entry: AddonEntry) -> AddonEntry:
    if not _SAFE_NAME.fullmatch(entry.name):
        raise ValueError("invalid addon name")
    if not entry.version or not entry.files:
        raise ValueError("addon version and files are required")
    seen = set()
    for item in entry.files:
        if not _safe_relative_path(item.path) or item.path in seen:
            raise ValueError("invalid or duplicate addon file path")
        if not item.download_url or item.size < 0:
            raise ValueError("addon file URL and non-negative size are required")
        if not re.fullmatch(r"[0-9a-f]{64}", item.sha256):
            raise ValueError("addon file sha256 must contain 64 lowercase hex characters")
        seen.add(item.path)
    entry.size = sum(item.size for item in entry.files)
    return entry


def fetch_addons_manifest(url: str = None) -> Optional[List[AddonEntry]]:
    """Скачать и распарсить манифест аддонов."""
    url = url or Config.ADDONS_MANIFEST_URL
    try:
        resp = requests.get(url, timeout=Config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            if isinstance(data, dict) and "addons" in data:
                data = data["addons"]
            else:
                return None
        result = []
        for addon in data:
            files = [AddonFile(
                path=str(item.get("path", "")),
                download_url=str(item.get("download_url", "")),
                sha256=str(item.get("sha256", "")).lower(),
                size=int(item.get("size", -1)),
            ) for item in addon.get("files", [])]
            result.append(_validate_entry(AddonEntry(
                name=str(addon.get("name", "")),
                version=str(addon.get("version", "")),
                description=str(addon.get("description", "")),
                files=files,
            )))
        return result
    except Exception:
        return None


def load_addons_state() -> dict:
    if os.path.isfile(Config.ADDONS_STATE_FILE):
        try:
            with open(Config.ADDONS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_addons_state(state: dict):
    state_dir = os.path.dirname(Config.ADDONS_STATE_FILE)
    os.makedirs(state_dir, exist_ok=True)
    tmp_path = Config.ADDONS_STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, Config.ADDONS_STATE_FILE)


def get_installed_version(name: str) -> Optional[str]:
    return load_addons_state().get(name)


def is_addon_installed(name: str) -> bool:
    return os.path.isdir(os.path.join(Config.ADDONS_DIR, name))


def needs_update(entry: AddonEntry) -> bool:
    installed = get_installed_version(entry.name)
    return not installed or not is_addon_installed(entry.name) or installed != entry.version


def install_addon(entry: AddonEntry, progress_cb: ProgressCallback = None) -> bool:
    """Скачать проверенные файлы каталога и атомарно установить аддон."""
    tmp_dir = tempfile.mkdtemp(prefix="dreamworld_addon_")
    staged_path = os.path.join(tmp_dir, entry.name)
    try:
        downloaded_total = 0
        for item in entry.files:
            target = os.path.join(staged_path, *PurePosixPath(item.path).parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            progress_cb and progress_cb(downloaded_total, entry.size, f"Скачивание {entry.name}...")
            resp = requests.get(item.download_url, stream=True, timeout=Config.HTTP_TIMEOUT)
            resp.raise_for_status()
            downloaded = 0
            digest = hashlib.sha256()
            with open(target, "wb") as output:
                for chunk in resp.iter_content(chunk_size=Config.DOWNLOAD_CHUNK):
                    if chunk:
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        progress_cb and progress_cb(downloaded_total + downloaded, entry.size, f"Скачивание {entry.name}...")
            if downloaded != item.size or digest.hexdigest() != item.sha256:
                return False
            downloaded_total += downloaded

        progress_cb and progress_cb(0, 0, f"Установка {entry.name}...")
        os.makedirs(Config.ADDONS_DIR, exist_ok=True)
        addon_path = os.path.join(Config.ADDONS_DIR, entry.name)
        backup_path = os.path.join(tmp_dir, "previous")
        if os.path.isdir(addon_path):
            os.replace(addon_path, backup_path)
        try:
            os.replace(staged_path, addon_path)
        except Exception:
            if os.path.isdir(backup_path) and not os.path.exists(addon_path):
                os.replace(backup_path, addon_path)
            raise

        state = load_addons_state()
        state[entry.name] = entry.version
        save_addons_state(state)
        progress_cb and progress_cb(0, 0, f"OK: {entry.name}")
        return True
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def uninstall_addon(name: str):
    addon_path = os.path.join(Config.ADDONS_DIR, name)
    if os.path.isdir(addon_path):
        shutil.rmtree(addon_path, ignore_errors=True)
    state = load_addons_state()
    state.pop(name, None)
    save_addons_state(state)


def install_selected(addons: List[AddonEntry], progress_cb: ProgressCallback = None) -> tuple:
    total = len(addons)
    success = 0
    for i, addon in enumerate(addons):
        progress_cb and progress_cb(i, total, f"({i+1}/{total}) {addon.name}")
        if install_addon(addon, lambda d, t, msg: progress_cb and progress_cb(i, total, msg)):
            success += 1
    return (success == total, success)
