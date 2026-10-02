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
import os
import sys
import tempfile
import time
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

    from updater.net_utils import download_with_retries

    ok, err = download_with_retries(
        url=download_url,
        dest_path=tmp_path,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        progress_cb=lambda d, t, msg: progress_cb and progress_cb(d, t, msg),
        max_retries=3,
    )

    if not ok:
        _cleanup_dir(tmp_dir)
        return False, ""

    return True, tmp_path


def apply_update(new_exe_path: str) -> bool:
    """
    Rename-then-replace: переименовать текущий .exe в .old,
    поставить новый на его место, перезапустить.
    .old будет удалён при следующем запуске (cleanup_self_update_files).
    """
    if sys.platform == "darwin":
        return _apply_macos_update(new_exe_path)

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

    # Новый процесс сначала ждёт завершения старого. Это не даёт
    # двум GUI одновременно работать с файлами и временными каталогами.
    import subprocess
    try:
        subprocess.Popen(
            [current_exe, "--self-update-parent-pid", str(os.getpid())],
            cwd=exe_dir,
            env=_clean_pyinstaller_environment(),
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            ),
        )
    except Exception:
        return False

    return True


def _clean_pyinstaller_environment() -> dict:
    """Заставить новый one-file EXE распаковать собственный runtime."""
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env.pop("_PYI_APPLICATION_HOME_DIR", None)
    env.pop("_MEIPASS2", None)
    return env


def wait_for_update_parent(argv=None, timeout_ms: int = 0xFFFFFFFF) -> bool:
    """Обработать внутренний аргумент перезапуска до создания QApplication.

    Возвращает True, если аргумент был найден и удалён из argv.
    """
    argv = sys.argv if argv is None else argv
    flag = "--self-update-parent-pid"
    if flag not in argv:
        return False

    index = argv.index(flag)
    try:
        pid = int(argv[index + 1])
        if pid <= 0:
            raise ValueError
    except (IndexError, TypeError, ValueError):
        del argv[index:index + 2]
        return True

    del argv[index:index + 2]
    if sys.platform == "win32":
        _wait_for_windows_process(pid, timeout_ms)
    elif sys.platform == "darwin":
        deadline = time.monotonic() + min(timeout_ms / 1000, 60)
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
    return True


def _wait_for_windows_process(pid: int, timeout_ms: int) -> None:
    """Дождаться PID без опроса tasklist и всплывающего cmd-окна."""
    import ctypes

    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return
    try:
        ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_ms)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


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

    # Забытые .new в системном temp. Не трогать общий префикс
    # dreamworld_: его используют другие операции и другой экземпляр лаунчера.
    try:
        tmp_root = tempfile.gettempdir()
        for entry in os.listdir(tmp_root):
            if entry.startswith("dreamworld_update_"):
                full = os.path.join(tmp_root, entry)
                try:
                    # Активная загрузка не должна быть удалена параллельным запуском.
                    if time.time() - os.path.getmtime(full) < 24 * 60 * 60:
                        continue
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


def _apply_macos_update(archive):
    from config import app_bundle_path
    from core.launcher_bundle import install_app
    import subprocess
    if not getattr(sys, "frozen", False) or not app_bundle_path():
        return False
    try:
        app = install_app(archive, Config.GAME_DIR)
        subprocess.Popen([str(app / "Contents/MacOS/Dreamworld"),
                          "--self-update-parent-pid", str(os.getpid())],
                         cwd=Config.GAME_DIR, env=_clean_pyinstaller_environment())
        _cleanup_dir(os.path.dirname(archive))
        return True
    except Exception:
        return False
