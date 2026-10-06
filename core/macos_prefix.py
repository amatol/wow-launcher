"""Однократная пересборка бутылки закрытого macOS-теста при смене Wine."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess

RUNTIME_ID = 'winecx-26.3.0-v1'
PREFIX_NAME = '.dreamworld-wine'
RUNTIME_MARKER = '.dreamworld-runtime'


@contextmanager
def prefix_lock(game_dir):
    # На macOS flock снимается системой даже при аварийном завершении лаунчера.
    import fcntl
    path = Path(game_dir).resolve() / '.dreamworld-wine.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Другой лаунчер уже подготавливает игру. Дождитесь его завершения.') from error
        yield
    finally:
        os.close(fd)


def ensure_runtime_prefix(resources, game_dir, env, log):
    """Удалить только прежний префикс Dreamworld; ссылки наружу не обходить."""
    prefix = Path(game_dir).resolve() / PREFIX_NAME
    if prefix.is_symlink() or Path(env['WINEPREFIX']) != prefix:
        raise RuntimeError('Небезопасный путь бутылки Wine. Пересоздание отменено.')
    if prefix.exists() and not prefix.is_dir():
        raise RuntimeError('Вместо папки бутылки Wine найден файл. Пересоздание отменено.')
    bundled_id = resources / 'Wine/dreamworld-runtime-id'
    if not bundled_id.is_file() or bundled_id.read_text().strip() != RUNTIME_ID:
        raise RuntimeError('Версия встроенного WineCX не совпадает. Скачайте Dreamworld.app заново.')
    marker = prefix / RUNTIME_MARKER
    if marker.is_file() and not marker.is_symlink() and marker.read_text().strip() == RUNTIME_ID:
        return
    if prefix.exists():
        # -w только ждёт блокировку сервера, не запускает и не убивает его.
        # Блокировка не зависит от версии протокола старого Wine.
        try:
            result = subprocess.run([str(resources / 'Wine/bin/wineserver'), '-w'],
                                    env=env, stdout=log, stderr=log, timeout=3)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('Закройте WoW и старый Wine перед созданием новой бутылки.') from error
        if result.returncode:
            raise RuntimeError('Не удалось проверить старую бутылку Wine. См. .dreamworld-wine.log.')
        log.write(b'\nDreamworld: replacing old .dreamworld-wine with ' + RUNTIME_ID.encode() + b'\n')
        log.flush()
        shutil.rmtree(prefix)
    prefix.mkdir(exist_ok=True)
    # Идентификатор поколения ставится до установки зависимостей: её сбой
    # можно повторить без очередного сброса уже созданной новой бутылки.
    marker.write_text(RUNTIME_ID + '\n', encoding='ascii')
