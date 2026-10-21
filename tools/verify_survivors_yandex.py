"""Реальная проверка первой установки с Яндекса без учётных данных игроков."""
import hashlib
import json
from pathlib import Path
import sys
import time

import requests

from config import Config
from core.survivors import SurvivorsInstaller, validate_manifest


def main():
    parent = Path(sys.argv[1]).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    last = [0]

    def progress(message, percent):
        if time.monotonic() - last[0] > 15 or percent < 0:
            print(message, flush=True)
            last[0] = time.monotonic()

    installer = SurvivorsInstaller(parent, progress)
    if installer.root.exists():
        raise RuntimeError('Проверке нужна новая пустая папка')
    original_download = installer._download
    downloads = []

    def download(session, entry, done, total, label=None):
        downloads.append(entry.path)
        return original_download(session, entry, done, total, label)

    installer._download = download
    root = installer.install()
    response = requests.get(Config.SURVIVORS_MANIFEST_URL, timeout=30)
    response.raise_for_status()
    manifest = validate_manifest(response.json())
    verified = []
    for entry in manifest.files:
        path = root / entry.path
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if path.stat().st_size != entry.size or digest != entry.sha256:
            raise RuntimeError('Не совпал файл: ' + entry.path)
        verified.append(entry.path)
    if downloads != ['.downloads/survivors-client.zip']:
        raise RuntimeError('Проверка должна установить все файлы из архива: ' + repr(downloads))
    if (root / 'survivors.log').exists() or (root / 'profiles').exists():
        raise RuntimeError('Посторонние данные из архива попали в установку')
    installer.install()
    if len(downloads) != 1:
        raise RuntimeError('Повторный запуск скачал архив заново')
    report = {'result': 'PASS', 'archive_public_url': Config.SURVIVORS_ARCHIVE_PUBLIC_URL,
              'archive_sha256': Config.SURVIVORS_ARCHIVE_SHA256, 'verified': verified,
              'downloads': downloads, 'repeat_install_downloads': 0}
    Path('survivors-yandex-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('YANDEX_FIRST_INSTALL: PASS', flush=True)


if __name__ == '__main__':
    main()
