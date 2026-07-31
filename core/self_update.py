"""
Самообновление лаунчера.

Схема:
1. Фоновый поток качает launcher_manifest.json
2. Сравнивает version с Config.LAUNCHER_VERSION
3. Если новее — сигнал в GUI, пользователю показывается диалог
4. При согласии — качается Dreamworld.exe.new
5. Создаётся .bat скрипт, который:
   - ждёт завершения текущего процесса
   - заменяет Dreamworld.exe -> Dreamworld.exe.new
   - удаляет .new и .bat
   - перезапускает Dreamworld.exe
6. Текущий процесс завершается
"""
import hashlib
import os
import sys
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
    """Сравнить версии в формате YYYYMMDD. Возвращает -1/0/1."""
    n1 = int(v1) if v1.isdigit() else 0
    n2 = int(v2) if v2.isdigit() else 0
    if n1 > n2:
        return 1
    if n1 < n2:
        return -1
    return 0


def download_update(manifest: dict, progress_cb: ProgressCallback = None) -> Tuple[bool, str]:
    """
    Скачать новый .exe во временную папку.
    Возвращает (успех, путь_к_скачанному_файлу).
    """
    download_url = manifest.get("download_url")
    if not download_url:
        return False, ""

    expected_sha256 = manifest.get("sha256", "")
    expected_size = manifest.get("size", 0)

    Config.ensure_temp_dir()
    tmp_path = os.path.join(Config.TEMP_DIR, Config.LAUNCHER_EXE_NAME + ".new")

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

        # Проверка хэша
        if expected_size and downloaded != expected_size:
            os.remove(tmp_path)
            return False, ""
        if expected_sha256 and h.hexdigest().lower() != expected_sha256.lower():
            os.remove(tmp_path)
            return False, ""

        return True, tmp_path

    except Exception:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)
        return False, ""


def apply_update(new_exe_path: str) -> bool:
    """
    Создать bat-скрипт для замены .exe и перезапуска.
    Запускает bat и возвращает True (текущий процесс должен завершиться).
    """
    if not os.path.isfile(new_exe_path):
        return False

    current_exe = sys.executable if getattr(sys, "frozen", False) else None
    if not current_exe:
        return False

    exe_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)
    bat_path = os.path.join(exe_dir, ".dreamworld_updater.bat")

    # bat-скрипт: ждёт завершения процесса, заменяет .exe, перезапускает
    bat_content = f"""@echo off
chcp 65001 >nul 2>&1
set "EXE={exe_dir}\\{exe_name}"
set "NEW={new_exe_path}"

:wait
tasklist /fi "pid eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)

copy /y "%NEW%" "%EXE%" >nul 2>&1
del /f /q "%NEW%" >nul 2>&1
start "" "%EXE%"
del /f /q "%bat_path%" >nul 2>&1
"""

    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except Exception:
        return False

    # Запустить bat в отдельном процессе
    import subprocess
    subprocess.Popen(
        ["cmd", "/c", bat_path],
        cwd=exe_dir,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    return True
