"""
Самообновление лаунчера.

Схема (rename-then-replace, без bat-скрипта):
1. Фоновый поток качает launcher_manifest.json
2. Сравнивает version с Config.LAUNCHER_VERSION
3. Если новее — сигнал в GUI, пользователю показывается диалог
4. При согласии — качается Dreamworld.exe.new в %TEMP%
5. Проверяется SHA-256 и размер
6. Текущий Dreamworld.exe переименовывается в Dreamworld.exe.old
7. Новый файл ставится на место Dreamworld.exe
8. Лаунчер перезапускается
9. При следующем запуске .old удаляется (cleanup_self_update_files)
"""
import hashlib
import os
import sys
import tempfile
from typing import Callable, Optional, Tuple

import requests

from config import Config

ProgressCallback = Callable[[int, int, str], None]


def fetch_launcher_manifest(url: str = None) -> Optional[dict]:
    """
    Скачать манифест обновлений лаунчера.
    Возвращает dict или None при ошибке/недоступности.
    """
    url = url or Config.LAUNCHER_MANIFEST_URL
    try:
        resp = requests.get(url, timeout=Config.HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def is_update_available(manifest: dict) -> bool:
    """Сравнить версию манифеста с текущей версией лаунчера."""
    if not manifest:
        return False
    remote_version = manifest.get("version", "")
    if not remote_version:
        return False
    return _compare_versions(remote_version, Config.LAUNCHER_VERSION) > 0


def _compare_versions(v1: str, v2: str) -> int:
    """Сравнить числовые версии YYYYMMDD. Возвращает -1/0/1.

    Десятизначные версии прежней схемы также принимаются, чтобы выпущенный
    лаунчер 2026080101 смог перейти на первый восьмизначный релиз 20260802.
    """
    def normalize(version: str) -> int:
        if not version.isdigit() or len(version) not in (8, 10):
            return 0
        return int(version[:8])

    n1 = normalize(v1)
    n2 = normalize(v2)
    if n1 > n2:
        return 1
    if n1 < n2:
        return -1
    return 0


def download_update(manifest: dict, progress_cb: ProgressCallback = None) -> Tuple[bool, str]:
    """
    Скачать новый .exe во временную папку (системный %TEMP%).
    Возвращает (успех, путь_к_скачанному_файлу).
    """
    download_url = manifest.get("download_url")
    if not download_url:
        return False, ""

    expected_sha256 = manifest.get("sha256", "")
    expected_size = manifest.get("size", 0)

    tmp_dir = tempfile.mkdtemp(prefix="dreamworld_update_")
    tmp_path = os.path.join(tmp_dir, Config.LAUNCHER_EXE_NAME + ".new")

    try:
        resp = requests.get(download_url, stream=True, timeout=Config.HTTP_TIMEOUT)
        resp.raise_for_status()

        total = int(resp.headers.get("Content-Length", expected_size or 0))
        downloaded = 0
        h = hashlib.sha256()

        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=Config.DOWNLOAD_CHUNK):
                if chunk:
                    f.write(chunk)
                    h.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total, "Downloading launcher update...")

        if expected_size and downloaded != expected_size:
            _cleanup_dir(tmp_dir)
            return False, ""
        if expected_sha256 and h.hexdigest().lower() != expected_sha256.lower():
            _cleanup_dir(tmp_dir)
            return False, ""

        return True, tmp_path

    except Exception:
        _cleanup_dir(tmp_dir)
        return False, ""


def apply_update(new_exe_path: str) -> bool:
    """
    Rename-then-replace: переименовать текущий .exe в .old,
    поставить новый на его место, перезапустить.
    .old будет удалён при следующем запуске (cleanup_self_update_files).
    """
    if not os.path.isfile(new_exe_path):
        return False

    current_exe = sys.executable if getattr(sys, "frozen", False) else None
    if not current_exe or sys.platform != "win32":
        return False

    current_exe = os.path.abspath(current_exe)
    new_exe_path = os.path.abspath(new_exe_path)
    exe_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)

    if exe_name.lower() != Config.LAUNCHER_EXE_NAME.lower():
        return False

    old_path = current_exe + ".old"

    try:
        # Удалить прошлый .old, если остался
        if os.path.isfile(old_path):
            os.remove(old_path)

        # Переименовать текущий .exe в .old
        os.rename(current_exe, old_path)

        # Поставить новый на место (попытка move, fallback — copy+remove)
        _move_exe(new_exe_path, current_exe)

    except Exception:
        # Попытаться откатить
        if os.path.isfile(old_path) and not os.path.isfile(current_exe):
            try:
                os.rename(old_path, current_exe)
            except Exception:
                pass
        return False

    # Очистить временную папку (не критично, если не выйдет — почистит при следующем запуске)
    tmp_dir = os.path.dirname(new_exe_path)
    _cleanup_dir(tmp_dir)

    # Перезапустить
    import subprocess
    try:
        subprocess.Popen(
            [current_exe],
            cwd=exe_dir,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            ),
        )
    except Exception:
        return False

    return True


def cleanup_self_update_files():
    """
    Удалить мусор от прошлых обновлений: .old, .new, .dreamworld_updater.bat,
    .dreamworld_updater.log, старую папку .launcher_tmp.
    """
    game_dir = Config.GAME_DIR
    exe_name = Config.LAUNCHER_EXE_NAME

    patterns = [
        exe_name + ".old",
        ".dreamworld_updater.bat",
        ".dreamworld_updater.log",
    ]

    for name in patterns:
        path = os.path.join(game_dir, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass

    # Старая папка .launcher_tmp (если осталась от прежних версий)
    old_tmp = os.path.join(game_dir, ".launcher_tmp")
    if os.path.isdir(old_tmp):
        try:
            import shutil
            shutil.rmtree(old_tmp)
        except Exception:
            pass

    # Забытые .new в системном temp
    try:
        tmp_root = tempfile.gettempdir()
        for entry in os.listdir(tmp_root):
            if entry.startswith("dreamworld_update_") or entry.startswith("dreamworld_"):
                full = os.path.join(tmp_root, entry)
                try:
                    if os.path.isdir(full):
                        import shutil
                        shutil.rmtree(full)
                    elif os.path.isfile(full):
                        os.remove(full)
                except Exception:
                    pass
    except Exception:
        pass


def _cleanup_dir(dir_path: str):
    """Удалить временную папку и всё её содержимое."""
    try:
        import shutil
        shutil.rmtree(dir_path)
    except Exception:
        pass


def _move_exe(src: str, dst: str):
    """Переместить .exe. Сначала пытается move, затем copy+remove.
    Если remove не выходит (файл залочен антивирусом) — не считается ошибкой,
    т.к. файл уже скопирован на нужное место."""
    import shutil
    try:
        shutil.move(src, dst)
    except Exception:
        shutil.copy2(src, dst)
        try:
            os.remove(src)
        except Exception:
            pass
