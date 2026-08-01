"""
HTTP/FTP обновление.
Скачивает файлы из манифеста и заменяет их в папке клиента.
"""
import os
import shutil
import hashlib
import tempfile
from typing import Callable, List

import requests

from config import Config
from updater.manifest import FileEntry, Manifest

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
        tmp_name = hashlib.sha256(entry.path.encode("utf-8")).hexdigest() + ".part"
        tmp_path = os.path.join(tmp_dir, tmp_name)

        self.progress_cb(0, 0, 0, 0, f"Скачивание {entry.path} ...")

        try:
            resp = requests.get(url, stream=True, timeout=Config.HTTP_TIMEOUT)
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", entry.size or 0))
            downloaded = 0
            h = hashlib.sha256()

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=Config.DOWNLOAD_CHUNK):
                    if self._cancel:
                        return False
                    if chunk:
                        f.write(chunk)
                        h.update(chunk)
                        downloaded += len(chunk)
                        self.progress_cb(0, 0, downloaded, total, f"Скачивание {entry.path}: {downloaded}/{total}")

            if entry.size and downloaded != entry.size:
                os.remove(tmp_path)
                self.progress_cb(0, 0, 0, 0, f"[!] Размер не совпадает: {entry.path}")
                return False
            if entry.sha256 and h.hexdigest().lower() != entry.sha256.lower():
                os.remove(tmp_path)
                self.progress_cb(0, 0, 0, 0, f"[!] Хэш не совпадает: {entry.path}")
                return False

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            os.replace(tmp_path, dest_path)
            self.progress_cb(0, 0, downloaded, total, f"OK: {entry.path}")
            return True

        except Exception as e:
            self.progress_cb(0, 0, 0, 0, f"[!] Ошибка скачивания {entry.path}: {e}")
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
            return False

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
