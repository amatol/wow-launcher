#!/usr/bin/env python3
"""Хранить три последних выпуска лаунчера и резервы этих версий."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit


RELEASE = re.compile(r'Dreamworld-(\d{8}(?:\d{2})?)\.(?:exe|app\.zip)')
ARCHIVED_MANIFEST = re.compile(r'launcher_manifest-(\d{8}(?:\d{2})?)\.json')
BACKUP = re.compile(r'launchers-\d{8}')
MANIFESTS = ('manifest.json', 'launcher_manifest.json', 'launcher_manifest_macos.json')


def release_date(version):
    version = str(version)
    if not re.fullmatch(r'\d{8}(?:\d{2})?', version):
        raise ValueError('Некорректная версия выпуска: ' + version)
    datetime.strptime(version[:8], '%Y%m%d')
    return version[:8]


def build_plan(public, backup_root, keep=3):
    if keep < 1:
        raise ValueError('Нужно сохранить хотя бы один выпуск')
    public, backup_root = Path(public).resolve(), Path(backup_root).resolve()
    releases = public / 'releases'
    if releases.is_symlink():
        raise ValueError('Каталог releases не должен быть symlink')
    candidates = []
    versions = set()
    for path in releases.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        match = RELEASE.fullmatch(path.name)
        if match:
            version = release_date(match[1])
            versions.add(version)
            candidates.append((path, version))
        elif (match := ARCHIVED_MANIFEST.fullmatch(path.name)):
            candidates.append((path, release_date(match[1])))
    retained = sorted(versions, reverse=True)[:keep]
    snapshots = {}
    for name in MANIFESTS:
        path = public / name
        content = path.read_bytes()
        snapshots[str(path)] = hashlib.sha256(content).hexdigest()
        manifest = json.loads(content)
        entries = list(manifest.get('launchers', {}).values()) if name == 'manifest.json' else [manifest]
        for entry in entries:
            filename = unquote(Path(urlsplit(entry['download_url']).path).name)
            match = RELEASE.fullmatch(filename)
            if not match or release_date(match[1]) not in retained:
                raise ValueError('Очистка затронет действующий манифест: ' + name)
            if not (releases / filename).is_file():
                raise ValueError('Отсутствует действующий файл: ' + filename)
    remove_files = [path for path, version in candidates if version not in retained]
    remove_backups = []
    if backup_root.exists():
        for path in sorted(backup_root.iterdir()):
            if not BACKUP.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
                continue
            # Дата имени резерва — день публикации следующего выпуска.
            # Срок хранения определяем по сохранённой версии, а не имени папки.
            versions_in_backup = set()
            for name in MANIFESTS[1:]:
                manifest = path / name
                if manifest.exists():
                    versions_in_backup.add(release_date(json.loads(manifest.read_text())['version']))
            if not versions_in_backup:
                raise ValueError('Не удалось определить версию резерва: ' + str(path))
            if not versions_in_backup.intersection(retained):
                remove_backups.append(path)
    total = sum(p.stat().st_size for p in remove_files)
    total += sum(p.stat().st_size for folder in remove_backups
                 for p in folder.rglob('*') if p.is_file() and not p.is_symlink())
    return {'retained_versions': retained, 'remove_files': [str(p) for p in remove_files],
            'remove_backups': [str(p) for p in remove_backups], 'bytes_to_remove': total,
            'manifest_snapshots': snapshots}


def apply_plan(plan):
    # Нельзя применять план, если параллельно уже опубликован другой выпуск.
    for name, digest in plan['manifest_snapshots'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Манифест изменился после подготовки очистки: ' + name)
    for name in plan['remove_files'] + plan['remove_backups']:
        if Path(name).is_symlink():
            raise RuntimeError('Цель очистки стала symlink: ' + name)
    for name in plan['remove_files']:
        Path(name).unlink()
    for name in plan['remove_backups']:
        shutil.rmtree(name)


def prune_releases(public, backup_root, keep=3):
    plan = build_plan(public, backup_root, keep)
    apply_plan(plan)
    return {k: v for k, v in plan.items() if k != 'manifest_snapshots'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, default=Path('/srv/dreamworld-launcher'))
    parser.add_argument('--backup-root', type=Path, default=Path('/var/backups/wowserver'))
    parser.add_argument('--keep', type=int, default=3)
    parser.add_argument('--apply', action='store_true', help='Удалить старые файлы; по умолчанию только показать план')
    args = parser.parse_args()
    plan = build_plan(args.public, args.backup_root, args.keep)
    if args.apply:
        apply_plan(plan)
    print(json.dumps({k: v for k, v in plan.items() if k != 'manifest_snapshots'},
                     ensure_ascii=False, indent=2))
