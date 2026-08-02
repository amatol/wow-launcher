"""
Обновление аддонов.
Манифест аддонов — JSON со списком:
[{ "name", "version", "description", "download_url", "sha256", "size" }]
"""
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import requests

from config import Config


@dataclass
class AddonEntry:
    name: str
    version: str
    description: str = ""
    download_url: str = ""
    sha256: str = ""
    size: int = 0


ProgressCallback = Callable[[int, int, str], None]

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _validate_entry(entry: AddonEntry) -> AddonEntry:
    if not _SAFE_NAME.fullmatch(entry.name):
        raise ValueError("invalid addon name")
    if not entry.version or not entry.download_url:
        raise ValueError("addon version and download_url are required")
    if entry.size <= 0:
        raise ValueError("addon size must be positive")
    if not re.fullmatch(r"[0-9a-f]{64}", entry.sha256):
        raise ValueError("addon sha256 must contain 64 lowercase hex characters")
    return entry


def _validated_zip_members(zf: zipfile.ZipFile, addon_name: str) -> List[zipfile.ZipInfo]:
    """Accept only relative members below the declared top-level addon folder."""
    members = zf.infolist()
    prefix = addon_name + "/"
    if not members:
        raise ValueError("empty addon archive")
    for member in members:
        normalized = member.filename.replace("\\", "/")
        parts = normalized.split("/")
        if (
            normalized.startswith("/")
            or not normalized.startswith(prefix)
            or ".." in parts
            or any(":" in part for part in parts)
        ):
            raise ValueError("unsafe addon archive path")
    return members


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
        return [_validate_entry(AddonEntry(
            name=str(a.get("name", "")),
            version=str(a.get("version", "")),
            description=str(a.get("description", "")),
            download_url=str(a.get("download_url", "")),
            sha256=str(a.get("sha256", "")).lower(),
            size=int(a.get("size", 0)),
        )) for a in data]
    except Exception:
        return None


def load_addons_state() -> dict:
    """Загрузить состояние установленных аддонов {name: version}."""
    if os.path.isfile(Config.ADDONS_STATE_FILE):
        try:
            with open(Config.ADDONS_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_addons_state(state: dict):
    """Сохранить состояние установленных аддонов."""
    state_dir = os.path.dirname(Config.ADDONS_STATE_FILE)
    os.makedirs(state_dir, exist_ok=True)
    tmp_path = Config.ADDONS_STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, Config.ADDONS_STATE_FILE)


def get_installed_version(name: str) -> Optional[str]:
    """Вернуть установленную версию аддона или None."""
    return load_addons_state().get(name)


def is_addon_installed(name: str) -> bool:
    """Проверить, установлен ли аддон (папка существует)."""
    return os.path.isdir(os.path.join(Config.ADDONS_DIR, name))


def needs_update(entry: AddonEntry) -> bool:
    """Проверить, нужно ли обновить/установить аддон."""
    installed = get_installed_version(entry.name)
    if not installed or not is_addon_installed(entry.name):
        return True
    return installed != entry.version


def install_addon(entry: AddonEntry, progress_cb: ProgressCallback = None) -> bool:
    """
    Скачать, проверить хэш, распаковать в AddOns.
    ZIP-архив должен содержать папку аддона на верхнем уровне.
    """
    if not entry.download_url:
        return False

    tmp_dir = tempfile.mkdtemp(prefix="dreamworld_addon_")

    try:
        progress_cb and progress_cb(0, entry.size, f"Скачивание {entry.name}...")
        resp = requests.get(entry.download_url, stream=True, timeout=Config.HTTP_TIMEOUT)
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", entry.size or 0))
        downloaded = 0
        h = hashlib.sha256()
        zip_path = os.path.join(tmp_dir, entry.name + ".zip")

        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=Config.DOWNLOAD_CHUNK):
                if chunk:
                    f.write(chunk)
                    h.update(chunk)
                    downloaded += len(chunk)
                    progress_cb and progress_cb(downloaded, total, f"Скачивание {entry.name}...")

        if entry.size and downloaded != entry.size:
            return False
        if entry.sha256 and h.hexdigest().lower() != entry.sha256.lower():
            return False

        progress_cb and progress_cb(0, 0, f"Установка {entry.name}...")

        # Проверить архив и распаковать сначала во временный каталог.
        os.makedirs(Config.ADDONS_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = _validated_zip_members(zf, entry.name)
            extract_dir = os.path.join(tmp_dir, "extracted")
            zf.extractall(extract_dir, members)

        staged_path = os.path.join(extract_dir, entry.name)
        addon_path = os.path.join(Config.ADDONS_DIR, entry.name)
        backup_path = os.path.join(tmp_dir, "previous")
        if not os.path.isdir(staged_path):
            return False
        if os.path.isdir(addon_path):
            os.replace(addon_path, backup_path)
        try:
            os.replace(staged_path, addon_path)
        except Exception:
            if os.path.isdir(backup_path) and not os.path.exists(addon_path):
                os.replace(backup_path, addon_path)
            raise

        # Обновить состояние
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
    """Удалить аддон."""
    addon_path = os.path.join(Config.ADDONS_DIR, name)
    if os.path.isdir(addon_path):
        shutil.rmtree(addon_path, ignore_errors=True)
    state = load_addons_state()
    state.pop(name, None)
    save_addons_state(state)


def install_selected(addons: List[AddonEntry], progress_cb: ProgressCallback = None) -> tuple:
    """
    Установить/обновить выбранные аддоны.
    Возвращает (успех, кол-во).
    """
    total = len(addons)
    success = 0
    for i, addon in enumerate(addons):
        progress_cb and progress_cb(i, total, f"({i+1}/{total}) {addon.name}")
        if install_addon(addon, lambda d, t, msg: progress_cb and progress_cb(i, total, msg)):
            success += 1
    return (success == total, success)
