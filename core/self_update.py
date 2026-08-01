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
    if not current_exe or sys.platform != "win32":
        return False

    current_exe = os.path.abspath(current_exe)
    new_exe_path = os.path.abspath(new_exe_path)
    exe_dir = os.path.dirname(current_exe)
    exe_name = os.path.basename(current_exe)
    expected_new = os.path.abspath(
        os.path.join(Config.TEMP_DIR, Config.LAUNCHER_EXE_NAME + ".new")
    )

    # Самообновление имеет право заменить ровно один известный файл. Любое
    # отличие пути считается ошибкой и не передаётся командному интерпретатору.
    if exe_name.lower() != Config.LAUNCHER_EXE_NAME.lower():
        return False
    if os.path.normcase(new_exe_path) != os.path.normcase(expected_new):
        return False
    if os.path.dirname(exe_dir) == exe_dir:
        return False
    if any(char in current_exe + new_exe_path for char in ('%', '!', '"', '\r', '\n')):
        return False

    bat_path = os.path.join(exe_dir, ".dreamworld_updater.bat")
    log_path = os.path.join(exe_dir, ".dreamworld_updater.log")

    bat_content = _build_updater_script(
        current_exe=current_exe,
        new_exe_path=new_exe_path,
        log_path=log_path,
        pid=os.getpid(),
    )

    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except Exception:
        return False

    # Сброс заставляет новый PyInstaller one-file процесс распаковать
    # собственный runtime, а не использовать удаляемый каталог старого процесса.
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_PYI_APPLICATION_HOME_DIR", None)
    env.pop("_MEIPASS2", None)

    import subprocess
    try:
        subprocess.Popen(
            ["cmd.exe", "/d", "/c", bat_path],
            cwd=exe_dir,
            env=env,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            ),
        )
    except Exception:
        return False
    return True


def _build_updater_script(current_exe: str, new_exe_path: str, log_path: str, pid: int) -> str:
    """Создать BAT без команд удаления и без доступа к файлам клиента."""
    return f"""@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "EXE={current_exe}"
set "NEW={new_exe_path}"
set "LOG={log_path}"
set "PYINSTALLER_RESET_ENVIRONMENT=1"
set "_PYI_APPLICATION_HOME_DIR="
set "_MEIPASS2="

echo [%date% %time%] Ожидание завершения PID {pid}.>"%LOG%"

:wait
tasklist /fi "pid eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)

echo [%date% %time%] Замена только Dreamworld.exe.>>"%LOG%"
move /y "%NEW%" "%EXE%" >>"%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ОШИБКА: замена не выполнена.>>"%LOG%"
    exit /b 1
)

echo [%date% %time%] Запуск обновлённого лаунчера.>>"%LOG%"
start "" "%EXE%"
if errorlevel 1 echo [%date% %time%] ОШИБКА: запуск не выполнен.>>"%LOG%"
endlocal
"""
