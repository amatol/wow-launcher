"""
BitTorrent фолбэк-обновление через libtorrent.
Качает торренты для файлов из манифеста, у которых есть torrent_url.
"""
import os
import time
from typing import Callable, List, Optional

from config import Config
from updater.manifest import FileEntry, Manifest

ProgressCallback = Callable[[int, int, int, int, str], None]

try:
    import libtorrent as lt
    HAS_LIBTORRENT = True
except ImportError:
    HAS_LIBTORRENT = False


class TorrentUpdater:
    def __init__(self, game_dir: str, manifest: Manifest, progress_cb: ProgressCallback = None):
        self.game_dir = game_dir
        self.manifest = manifest
        self.progress_cb = progress_cb or (lambda *a: None)
        self._cancel = False

        if not HAS_LIBTORRENT:
            raise RuntimeError(
                "libtorrent не установлен. Установите: pip install libtorrent-rasterbar"
            )

        self.session = lt.session()
        self.session.listen_on(Config.TORRENT_PORT, Config.TORRENT_PORT + 10)

    def cancel(self):
        self._cancel = True

    def _add_torrent(self, torrent_url: str, save_path: str):
        """Добавить торрент по URL .torrent-файла."""
        import requests
        resp = requests.get(torrent_url, timeout=Config.HTTP_TIMEOUT)
        resp.raise_for_status()
        info = lt.torrent_info(lt.bdecode(resp.content))
        params = {
            "save_path": save_path,
            "storage_mode": lt.storage_mode_t.storage_mode_sparse,
        }
        handle = self.session.add_torrent(info, save_path)
        return handle

    def download_file(self, entry: FileEntry, save_dir: str) -> bool:
        if not entry.torrent_url:
            self.progress_cb(0, 0, 0, 0, f"[!] Нет torrent URL для {entry.path}")
            return False

        self.progress_cb(0, 0, 0, 0, f"Torrent: {entry.path}")

        try:
            handle = self._add_torrent(entry.torrent_url, save_dir)
        except Exception as e:
            self.progress_cb(0, 0, 0, 0, f"[!] Не удалось добавить торрент {entry.path}: {e}")
            return False

        handle.set_sequential_download(True)

        start = time.time()
        while not handle.is_seed():
            if self._cancel:
                self.session.remove_torrent(handle)
                return False

            s = handle.status()
            progress = s.progress * 100
            dl_rate = s.download_rate / 1024
            self.progress_cb(
                0, 0,
                int(s.total_wanted_done),
                int(s.total_wanted),
                f"Torrent {entry.path}: {progress:.1f}% | {dl_rate:.0f} KB/s",
            )

            if time.time() - start > Config.TORRENT_TIMEOUT:
                self.progress_cb(0, 0, 0, 0, f"[!] Таймаут торрента: {entry.path}")
                self.session.remove_torrent(handle)
                return False

            time.sleep(1)

        self.session.remove_torrent(handle)
        self.progress_cb(0, 0, 0, 0, f"OK (torrent): {entry.path}")
        return True

    def apply_all(self, files: List[FileEntry]) -> tuple:
        Config.ensure_temp_dir()
        total = len(files)
        success = 0

        for i, entry in enumerate(files):
            if self._cancel:
                break
            self.progress_cb(i, total, 0, entry.size, f"({i+1}/{total}) torrent {entry.path}")

            # Качаем во временную папку, потом перемещаем
            if self.download_file(entry, Config.TEMP_DIR):
                # libtorrent сохраняет под именем из торрента — найдём скачанный файл
                downloaded = self._find_downloaded(entry)
                if downloaded:
                    dest = os.path.join(self.game_dir, entry.path)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    import shutil
                    shutil.move(downloaded, dest)
                    success += 1

        return (success == total and not self._cancel, success)

    def _find_downloaded(self, entry: FileEntry) -> Optional[str]:
        """Найти скачанный файл во временной папке по имени из пути."""
        filename = os.path.basename(entry.path)
        candidate = os.path.join(Config.TEMP_DIR, filename)
        if os.path.isfile(candidate):
            return candidate
        # Поиск рекурсивно
        for root, _dirs, files in os.walk(Config.TEMP_DIR):
            for f in files:
                if f == filename:
                    return os.path.join(root, f)
        return None
