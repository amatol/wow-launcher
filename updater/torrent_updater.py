"""
BitTorrent фолбэк-обновление через libtorrent.
Качает торренты для файлов из манифеста, у которых есть torrent_url.
"""
import os
import shutil
import tempfile
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
        self._tmp_dir = None

        if not HAS_LIBTORRENT:
            raise RuntimeError(
                "libtorrent не установлен. Установите: pip install libtorrent-rasterbar"
            )

        self.session = lt.session()
        self.session.listen_on(Config.TORRENT_PORT, Config.TORRENT_PORT + 10)

    def cancel(self):
        self._cancel = True

    def _get_tmp_dir(self) -> str:
        if self._tmp_dir is None:
            self._tmp_dir = tempfile.mkdtemp(prefix="dreamworld_torrent_")
        return self._tmp_dir

    def cleanup(self):
        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            try:
                shutil.rmtree(self._tmp_dir)
            except Exception:
                pass
            self._tmp_dir = None

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
        tmp_dir = self._get_tmp_dir()
        total = len(files)
        success = 0

        for i, entry in enumerate(files):
            if self._cancel:
                break
            self.progress_cb(i, total, 0, entry.size, f"({i+1}/{total}) torrent {entry.path}")

            if self.download_file(entry, tmp_dir):
                downloaded = self._find_downloaded(entry, tmp_dir)
                if downloaded:
                    dest = os.path.join(self.game_dir, entry.path)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(downloaded, dest)
                    success += 1

        self.cleanup()
        return (success == total and not self._cancel, success)

    def _find_downloaded(self, entry: FileEntry, tmp_dir: str) -> Optional[str]:
        """Найти скачанный файл во временной папке по имени из пути."""
        filename = os.path.basename(entry.path)
        candidate = os.path.join(tmp_dir, filename)
        if os.path.isfile(candidate):
            return candidate
        for root, _dirs, files in os.walk(tmp_dir):
            for f in files:
                if f == filename:
                    return os.path.join(root, f)
        return None
