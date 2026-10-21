"""Изолированная установка и запуск Warcraft Survivors."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit

import requests

from config import Config
from updater.manifest import Manifest


class Cancelled(Exception):
    pass


def validate_manifest(data):
    manifest = Manifest.from_dict(data)
    if manifest.removed_files or not 3 <= len(manifest.files) <= 40:
        raise ValueError('Некорректный состав файлов Warcraft Survivors.')
    names = set()
    allowed = {'warcraft-survivors.exe', 'LICENSE-MIT', 'LICENSE-APACHE', 'UPSTREAM_REVISION.txt'}
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
    if not {'warcraft-survivors.exe', 'data/terrain.mpq', 'data/patch.mpq'} <= names:
        raise ValueError('В манифесте нет обязательных файлов режима.')
    if sum(entry.size for entry in manifest.files) > 16 * 1024**3:
        raise ValueError('Некорректный размер установки.')
    return manifest


class SurvivorsInstaller:
    def __init__(self, game_dir, progress=None, cancelled=None):
        self.parent = Path(game_dir).resolve()
        self.root = self.parent / 'WarcraftSurvivors'
        self.progress = progress or (lambda message, percent: None)
        self.cancelled = cancelled or (lambda: False)

    def _check(self):
        if self.cancelled():
            raise Cancelled('Установка отменена. Скачанные части сохранятся для продолжения.')

    def _safe(self, relative):
        target = self.root / relative
        # Запрещены в том числе Windows junction, ведущие из установки наружу.
        if self.root.is_symlink() or self.root.resolve() != self.parent / 'WarcraftSurvivors':
            raise ValueError('Папка WarcraftSurvivors не должна быть ссылкой на другой каталог.')
        if target.resolve() != self.root / relative:
            raise ValueError('В папке режима обнаружена ссылка. Выберите обычный каталог.')
        return target

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
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress('Проверка обновлений Warcraft Survivors…', -1)
        with requests.Session() as session:
            with session.get(Config.SURVIVORS_MANIFEST_URL, timeout=20) as response:
                response.raise_for_status()
                if len(response.content) > 128 * 1024:
                    raise ValueError('Слишком большой манифест режима.')
                manifest = validate_manifest(response.json())
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
        return self.root

    def _download(self, session, entry, done, total):
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
                                f'Загрузка {entry.path} · {(done + current) / 1024**3:.2f} / {total / 1024**3:.2f} ГиБ',
                                min(99, int((done + current) * 100 / total)),
                            )
        if current != entry.size:
            raise OSError('Загрузка прервалась. Нажмите «Войти и играть» для продолжения.')
        self.progress('Проверка загрузки ' + entry.path + '…', -1)
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
