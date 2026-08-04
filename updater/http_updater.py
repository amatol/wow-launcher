"""
HTTP/FTP обновление.
Скачивает файлы из манифеста и заменяет их в папке клиента.
"""
import os
import shutil
import tempfile
from typing import Callable, List

from config import Config
from updater.manifest import FileEntry, Manifest
from updater.net_utils import download_with_retries

# Тип callback-функции прогресса: (текущий_файл, всего_файлов, байтов_скачано, байтов_всего, сообщение)
ProgressCallback = Callable[[int, int, int, int, str], None]


class HTTPUpdater:
    def __init__(self, game_dir: str, manifest: Manifest, progress_cb: ProgressCallback = None):
        self.game_dir = game_dir
        self.manifest = manifest
        self.progress_cb = progress_cb or (lambda *a: None)
        self._cancel = False
        self._tmp_dir = None

    def cancel(self):
        self._cancel = True

    def _get_tmp_dir(self) -> str:
        if self._tmp_dir is None:
            self._tmp_dir = tempfile.mkdtemp(prefix="dreamworld_dl_")
        return self._tmp_dir

    def cleanup(self):
        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            try:
                shutil.rmtree(self._tmp_dir)
            except Exception:
                pass
            self._tmp_dir = None

    def download_file(self, entry: FileEntry, dest_path: str) -> bool:
        """Скачать один файл во временную локацию, проверить хэш, переместить."""
        url = entry.http_url
        if not url:
            self.progress_cb(0, 0, 0, 0, f"[!] Нет HTTP URL для {entry.path}")
            return False

        tmp_dir = self._get_tmp_dir()
        tmp_name = entry.path.replace("/", "_").replace("\\", "_") + ".part"
        tmp_path = os.path.join(tmp_dir, tmp_name)

        self.progress_cb(0, 0, 0, entry.size or 0, f"Скачивание {entry.path} ...")

        ok, err = download_with_retries(
            url=url,
            dest_path=tmp_path,
            expected_size=entry.size,
            expected_sha256=entry.sha256,
            progress_cb=lambda d, t, msg: self.progress_cb(0, 0, d, t, f"{entry.path}: {msg}"),
            cancel_check=lambda: self._cancel,
        )

        if not ok:
            if self._cancel:
                self.progress_cb(0, 0, 0, 0, f"Отменено: {entry.path}")
            else:
                self.progress_cb(0, 0, 0, 0, f"[!] {entry.path}: {err}")
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        os.replace(tmp_path, dest_path)
        self.progress_cb(0, 0, entry.size or 0, entry.size or 0, f"OK: {entry.path}")
        return True

    def apply_all(self, files: List[FileEntry]) -> tuple:
        """Скачать и применить все файлы. Возвращает (успех, кол-во)."""
        total = len(files)
        success_count = 0
        for i, entry in enumerate(files):
            if self._cancel:
                break
            dest = os.path.join(self.game_dir, entry.path)
            self.progress_cb(i, total, 0, entry.size, f"({i+1}/{total}) {entry.path}")

            # Бэкап существующего файла (на случай отката)
            backup_path = None
            if os.path.isfile(dest):
                backup_path = dest + ".bak"
                shutil.copy2(dest, backup_path)

            if self.download_file(entry, dest):
                success_count += 1
                if backup_path and os.path.isfile(backup_path):
                    os.remove(backup_path)
            else:
                if backup_path and os.path.isfile(backup_path):
                    shutil.move(backup_path, dest)

        self.cleanup()
        return (success_count == total and not self._cancel, success_count)
