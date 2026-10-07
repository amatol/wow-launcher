#!/usr/bin/env python3
"""Собрать переносимый cabextract и добавить закреплённый Winetricks."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request


def build():
    lock_path = Path('tools/font-tools-lock.json')
    lock = json.loads(lock_path.read_text())
    destination = Path('build/font-tools').resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dreamworld-font-tools-') as directory:
        root = Path(directory)
        for name, entry in lock.items():
            archive = root / name
            with urllib.request.urlopen(entry['url'], timeout=60) as response:
                data = response.read(4 * 1024 * 1024 + 1)
            if hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise RuntimeError('Контрольная сумма не совпала: ' + name)
            archive.write_bytes(data)
        shutil.copy2(root / 'winetricks', destination / 'winetricks')
        subprocess.run(['tar', '-xf', str(root / 'cabextract'), '-C', str(root)], check=True)
        source = root / ('cabextract-' + lock['cabextract']['version'])
        subprocess.run([str(source / 'configure'), '--without-external-libmspack'], cwd=source, check=True)
        subprocess.run(['make', '-j2'], cwd=source, check=True)
        shutil.copy2(source / 'cabextract', destination / 'cabextract')
        # Исходники и лицензия сохраняются рядом с утилитой для воспроизводимости.
        shutil.copy2(root / 'cabextract', destination / 'cabextract-source.tar.gz')
        shutil.copy2(source / 'COPYING', destination / 'cabextract-COPYING')
    shutil.copy2(lock_path, destination / lock_path.name)


if __name__ == '__main__':
    build()
