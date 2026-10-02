#!/usr/bin/env python3
"""Опубликовать обе сборки и общий клиентский манифест последним."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import os
import urllib.request

from core.launcher_bundle import extract_app
from config import Config


def metadata(path, url, version):
    content = path.read_bytes()
    return {'version': version, 'download_url': url, 'size': len(content),
            'sha256': hashlib.sha256(content).hexdigest(),
            'changelog': 'Тестовая версия macOS для Apple Silicon; лаунчеры Windows и Mac рядом с клиентом.'}


def atomic_json(path, data):
    temporary = path.with_name('.' + path.name + '.new')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('windows', type=Path)
    parser.add_argument('macos', type=Path)
    parser.add_argument('--public', type=Path, default=Path('/srv/dreamworld-launcher'))
    parser.add_argument('--client', type=Path, default=Path('/opt/azerothcore/client'))
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    version = datetime.now(ZoneInfo('Europe/Moscow')).strftime('%Y%m%d')
    if Config.LAUNCHER_VERSION != version:
        parser.error('Нужно пересобрать лаунчеры с сегодняшней датой публикации')
    public = args.public
    previous = json.loads((public / 'manifest.json').read_text())
    old_launcher = json.loads((public / 'launcher_manifest.json').read_text())
    if old_launcher['version'] == version:
        parser.error('Сегодняшний лаунчер уже опубликован')
    if args.windows.read_bytes()[:2] != b'MZ':
        parser.error('Windows-артефакт не является EXE')
    with tempfile.TemporaryDirectory() as temp:
        extract_app(args.macos, temp)
    args.backup.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name in ('manifest.json', 'launcher_manifest.json', 'launcher_manifest_macos.json', 'Dreamworld.exe', 'Dreamworld.app.zip'):
        if (public / name).is_file():
            shutil.copy2(public / name, args.backup / name)
    for name in ('Dreamworld.exe', 'Dreamworld.app'):
        source = args.client / name
        if source.is_dir():
            shutil.copytree(source, args.backup / ('client-' + name), symlinks=True)
        elif source.is_file():
            shutil.copy2(source, args.backup / ('client-' + name))
    releases = public / 'releases'
    releases.mkdir(exist_ok=True)
    launchers = {}
    for platform, source, filename in (
        ('windows', args.windows, f'Dreamworld-{version}.exe'),
        ('macos', args.macos, f'Dreamworld-{version}.app.zip'),
    ):
        release = releases / filename
        if release.exists():
            raise RuntimeError('Релизный файл уже существует: ' + str(release))
        shutil.copy2(source, release)
        entry = metadata(release, Config.UPDATE_BASE_URL + '/releases/' + filename, version)
        # Проверка полной публичной копии до объявления обновления.
        with urllib.request.urlopen(entry['download_url'], timeout=180) as response:
            digest = hashlib.sha256()
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        if size != entry['size'] or digest.hexdigest() != entry['sha256']:
            raise RuntimeError('HTTPS-копия не совпадает: ' + filename)
        launchers[platform] = entry
    for source, name in ((args.windows, 'Dreamworld.exe'), (args.macos, 'Dreamworld.app.zip')):
        temporary = public / ('.' + name + '.new')
        shutil.copy2(source, temporary)
        os.replace(temporary, public / name)
    # Эталонный клиент также содержит обе версии рядом с Wow.exe.
    from core.launcher_bundle import install_app
    install_app(args.macos, args.client)
    temporary = args.client / '.Dreamworld.exe.new'
    shutil.copy2(args.windows, temporary)
    os.replace(temporary, args.client / 'Dreamworld.exe')
    atomic_json(public / 'launcher_manifest.json', {**launchers['windows'], 'launchers': launchers})
    atomic_json(public / 'launcher_manifest_macos.json', {**launchers['macos'], 'launchers': launchers})
    previous['version'] = version
    previous['launchers'] = launchers
    atomic_json(public / 'manifest.json', previous)
    print(json.dumps({'version': version, 'launchers': launchers}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
