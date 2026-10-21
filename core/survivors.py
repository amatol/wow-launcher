"""Изолированная установка и запуск Warcraft Survivors."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import stat
import zipfile
from urllib.parse import urlsplit

import requests

from config import Config
from updater.manifest import Manifest, FileEntry
from updater.bootstrap import resolve_yandex_download


class Cancelled(Exception):
    pass


def validate_manifest(data):
    manifest = Manifest.from_dict(data)
    if manifest.removed_files or not 3 <= len(manifest.files) <= 40:
        raise ValueError('Некорректный состав файлов Warcraft Survivors.')
    names = set()
    allowed = {'warcraft-survivors.exe', 'VCRUNTIME140.dll', 'LICENSE-MIT', 'LICENSE-APACHE', 'UPSTREAM_REVISION.txt'}
    base = urlsplit(Config.SURVIVORS_BASE_URL)
    for entry in manifest.files:
        if entry.path not in allowed and not re.fullmatch(r'Data/[A-Za-z0-9_.-]+\.[Mm][Pp][Qq]', entry.path):
            raise ValueError('Манифест содержит посторонний файл.')
        if entry.path.casefold() in names or not entry.sha256 or not 0 < entry.size < 8 * 1024**3:
            raise ValueError('Некорректные размер, хэш или путь файла.')
        names.add(entry.path.casefold())
        url = urlsplit(entry.http_url or '')
        if (url.scheme != 'https' or url.netloc != base.netloc
                or not url.path.startswith(base.path.rstrip('/') + '/')
                or url.username or url.password or url.query or url.fragment):
            raise ValueError('Недопустимый источник файлов Warcraft Survivors.')
    if not {'warcraft-survivors.exe', 'vcruntime140.dll', 'data/terrain.mpq', 'data/patch.mpq'} <= names:
        raise ValueError('В манифесте нет обязательных файлов режима.')
    if sum(entry.size for entry in manifest.files) > 16 * 1024**3:
        raise ValueError('Некорректный размер установки.')
    return manifest


class SurvivorsInstaller:
    def __init__(self, game_dir, progress=None, cancelled=None):
        self.parent = Path(game_dir).resolve()
        self.root = self.parent / 'Survivors'
        self.progress = progress or (lambda message, percent: None)
        self.cancelled = cancelled or (lambda: False)

    def _check(self):
        if self.cancelled():
            raise Cancelled('Установка отменена. Скачанные части сохранятся для продолжения.')

    def _safe(self, relative):
        target = self.root / relative
        # Запрещены в том числе Windows junction, ведущие из установки наружу.
        if self.root.is_symlink() or self.root.resolve() != self.parent / 'Survivors':
            raise ValueError('Папка Survivors не должна быть ссылкой на другой каталог.')
        if target.resolve() != self.root / relative:
            raise ValueError('В папке режима обнаружена ссылка. Выберите обычный каталог.')
        return target

    def _migrate_legacy_directory(self):
        """Перенести всю прежнюю установку, включая профили и недокачанные части."""
        legacy = self.parent / 'WarcraftSurvivors'
        if legacy.is_symlink() or legacy.resolve() != self.parent / 'WarcraftSurvivors':
            raise ValueError('Прежняя папка WarcraftSurvivors не должна быть ссылкой на другой каталог.')
        if not legacy.exists():
            return
        if not legacy.is_dir():
            raise ValueError('Путь WarcraftSurvivors занят файлом. Освободите имя папки и повторите запуск.')
        if self.root.exists():
            if not self.root.is_dir() or any(self.root.iterdir()):
                raise ValueError('Найдены обе папки: Survivors и WarcraftSurvivors. Обратитесь к администратору для переноса без потери данных.')
            self.root.rmdir()  # Только пустая папка; чужие файлы не заменяем.
        self._check()
        self.progress('Перенос скачанных файлов в папку Survivors…', -1)
        try:
            legacy.rename(self.root)
        except OSError:
            raise OSError('Не удалось перенести папку режима. Закройте игру и прежний лаунчер, затем повторите запуск.') from None

    def _digest(self, path):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(4 * 1024**2):
                self._check()
                digest.update(block)
        return digest.hexdigest()

    def install(self):
        self._check()
        self._safe('Data')
        self._migrate_legacy_directory()
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress('Проверка обновлений Warcraft Survivors…', -1)
        with requests.Session() as session:
            with session.get(Config.SURVIVORS_MANIFEST_URL, timeout=20) as response:
                response.raise_for_status()
                if len(response.content) > 128 * 1024:
                    raise ValueError('Слишком большой манифест режима.')
                manifest = validate_manifest(response.json())
            if self._needs_bootstrap(manifest):
                self._bootstrap(session, manifest)
            needed = []
            for entry in manifest.files:
                self._check()
                path = self._safe(entry.path)
                self.progress('Проверка ' + entry.path + '…', -1)
                if (not path.is_file() or path.stat().st_size != entry.size
                        or self._digest(path) != entry.sha256):
                    needed.append(entry)
            additional = 0
            for entry in needed:
                partial = self._safe('.downloads/' + entry.sha256 + '.part')
                present = partial.stat().st_size if partial.is_file() else 0
                additional += entry.size - present if present <= entry.size else entry.size
            if needed and shutil.disk_usage(self.root).free < additional + 128 * 1024**2:
                raise OSError('Недостаточно свободного места для установки Warcraft Survivors.')
            total = sum(entry.size for entry in needed)
            done = 0
            for entry in needed:
                self._check()
                self._download(session, entry, done, total)
                done += entry.size
            self._check()
            state = self._safe('.version.new')
            state.write_text(manifest.version, encoding='ascii')
            os.replace(state, self._safe('.version'))
            self._safe('.downloads/survivors-client.zip').unlink(missing_ok=True)
        return self.root

    def _needs_bootstrap(self, manifest):
        # После отмены распаковки используем уже скачанный архив повторно.
        if (self._safe('.downloads/survivors-client.zip').is_file()
                or self._safe('.downloads/' + Config.SURVIVORS_ARCHIVE_SHA256 + '.part').is_file()):
            return True
        # Уже начатую пофайловую установку продолжаем без большого архива.
        return not any(
            self._safe(entry.path).is_file()
            or self._safe('.downloads/' + entry.sha256 + '.part').is_file()
            for entry in manifest.files
        )

    def _bootstrap(self, session, manifest):
        archive = self._safe('.downloads/survivors-client.zip')
        size, digest = Config.SURVIVORS_ARCHIVE_SIZE, Config.SURVIVORS_ARCHIVE_SHA256
        partial = self._safe('.downloads/' + digest + '.part')
        present = partial.stat().st_size if partial.is_file() else 0
        archive_ready = archive.is_file() and archive.stat().st_size == size and self._digest(archive) == digest
        required = sum(entry.size for entry in manifest.files)
        if not archive_ready:
            required += size - present if present <= size else size
        if shutil.disk_usage(self.root).free < required + 128 * 1024**2:
            raise OSError('Недостаточно места для архива и распаковки Warcraft Survivors.')
        if not archive_ready:
            self._check()
            self.progress('Получение ссылки Яндекс Диска…', -1)
            href, remote_size = resolve_yandex_download(Config.SURVIVORS_ARCHIVE_PUBLIC_URL)
            if remote_size != size:
                raise ValueError('Архив Survivors на Яндекс Диске изменился. Обратитесь к администратору.')
            try:
                self._download(session, FileEntry('.downloads/survivors-client.zip', size, digest, href),
                               0, size, label='клиента с Яндекс Диска')
            except requests.RequestException:
                raise OSError('Не удалось скачать архив с Яндекс Диска. Повторите запуск для продолжения.') from None
        self._extract_archive(archive, manifest)

    def _extract_archive(self, archive, manifest):
        # Устанавливаем только управляемые файлы; чужие профили и лаунчеры
        # из архива никогда не попадают в установку игрока.
        entries = {entry.path.casefold(): entry for entry in manifest.files}
        with zipfile.ZipFile(archive) as source:
            selected = {}
            for member in source.infolist():
                self._check()
                name = member.filename.replace('\\', '/')
                parts = name.rstrip('/').split('/')
                if (name.startswith('/') or any(part in ('', '.', '..') or ':' in part for part in parts)
                        or stat.S_ISLNK(member.external_attr >> 16)):
                    raise ValueError('В архиве Survivors обнаружен небезопасный путь.')
                if parts[0].casefold() == 'survivors':
                    parts = parts[1:]
                key = '/'.join(parts).casefold()
                if member.is_dir() or key not in entries:
                    continue
                if key in selected or member.file_size > 8 * 1024**3:
                    raise ValueError('Некорректный состав архива Survivors.')
                selected[key] = member
            if not {'data/terrain.mpq', 'data/patch.mpq'} <= selected.keys():
                raise ValueError('В архиве не найдены данные Warcraft Survivors.')
            for key, member in selected.items():
                self._check()
                entry = entries[key]
                # Устаревшие файлы архива заменятся актуальными с сервера.
                if member.file_size != entry.size:
                    continue
                target = self._safe(entry.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = self._safe('.downloads/' + entry.sha256 + '.extract')
                temporary.parent.mkdir(exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                self.progress('Распаковка ' + entry.path + '…', -1)
                try:
                    with source.open(member) as src, temporary.open('wb') as dst:
                        while block := src.read(1024 * 1024):
                            self._check()
                            written += len(block)
                            if written > entry.size:
                                raise ValueError('Превышен размер файла в архиве.')
                            digest.update(block)
                            dst.write(block)
                    if written == entry.size and digest.hexdigest() == entry.sha256:
                        self._check()
                        os.replace(temporary, target)
                finally:
                    temporary.unlink(missing_ok=True)

    def _download(self, session, entry, done, total, label=None):
        label = label or entry.path
        target = self._safe(entry.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        parts = self._safe('.downloads')
        parts.mkdir(exist_ok=True)
        partial = self._safe('.downloads/' + entry.sha256 + '.part')
        if partial.exists() and partial.stat().st_size > entry.size:
            partial.unlink()
        current = partial.stat().st_size if partial.is_file() else 0
        if current < entry.size:
            headers = {'Range': f'bytes={current}-', 'Accept-Encoding': 'identity'} if current else {'Accept-Encoding': 'identity'}
            with session.get(entry.http_url, headers=headers, stream=True, timeout=(15, 20)) as response:
                response.raise_for_status()
                if response.status_code == 206:
                    expected = f'bytes {current}-{entry.size - 1}/{entry.size}'
                    if response.headers.get('Content-Range') != expected:
                        raise ValueError('Сервер вернул неверный диапазон файла.')
                elif response.status_code == 200:
                    current = 0
                else:
                    raise ValueError('Неожиданный ответ сервера загрузки.')
                with partial.open('ab' if current else 'wb') as stream:
                    for block in response.iter_content(256 * 1024):
                        self._check()
                        if block:
                            current += len(block)
                            if current > entry.size:
                                raise ValueError('Сервер превысил заявленный размер файла.')
                            stream.write(block)
                            self.progress(
                                f'Загрузка {label} · {(done + current) / 1024**3:.2f} / {total / 1024**3:.2f} ГиБ',
                                min(99, int((done + current) * 100 / total)),
                            )
        if current != entry.size:
            raise OSError('Загрузка прервалась. Нажмите «Войти и играть» для продолжения.')
        self.progress('Проверка загрузки ' + label + '…', -1)
        if self._digest(partial) != entry.sha256:
            partial.unlink()
            raise ValueError('Контрольная сумма файла не совпала. Повторите загрузку.')
        self._check()
        os.replace(partial, target)


def launch_survivors(root, username):
    root = Path(root).resolve()
    environment = os.environ.copy()
    # Настройки разработчика/логин другого WoW не должны влиять на отдельный режим.
    for name in list(environment):
        if name.startswith(('WOW_', 'BENILLA_')):
            environment.pop(name)
    environment['WOW_DATA'] = str(root / 'Data')
    profile = hashlib.sha256(username.encode('utf-8')).hexdigest()[:24]
    environment['BENILLA_HOME'] = str(root / 'profiles' / profile)
    log_path = root / 'survivors.log'
    with log_path.open('wb') as log:
        return subprocess.Popen(
            [str(root / 'warcraft-survivors.exe')], cwd=str(root), env=environment,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
