"""Автоматическая установка Microsoft corefonts в игровой Wine-префикс."""
import os
from pathlib import Path
import subprocess
import signal

FONT_FILES = (
    'andalemo.ttf', 'arial.ttf', 'arialbd.ttf', 'arialbi.ttf', 'ariali.ttf', 'ariblk.ttf',
    'comic.ttf', 'comicbd.ttf', 'cour.ttf', 'courbd.ttf', 'courbi.ttf', 'couri.ttf',
    'georgia.ttf', 'georgiab.ttf', 'georgiai.ttf', 'georgiaz.ttf', 'impact.ttf',
    'times.ttf', 'timesbd.ttf', 'timesbi.ttf', 'timesi.ttf',
    'trebuc.ttf', 'trebucbd.ttf', 'trebucbi.ttf', 'trebucit.ttf',
    'verdana.ttf', 'verdanab.ttf', 'verdanai.ttf', 'verdanaz.ttf', 'webdings.ttf',
)
FONT_MARKER = '.dreamworld-corefonts-v1'


def corefonts_ready(prefix):
    fonts = Path(prefix) / 'drive_c/windows/Fonts'
    for name in FONT_FILES:
        path = fonts / name
        if not path.is_file() or path.stat().st_size < 1024:
            return False
        with path.open('rb') as stream:
            if stream.read(4) not in (b'\x00\x01\x00\x00', b'OTTO'):
                return False
    return True


def prepare_corefonts(resources, game_dir, env, log):
    prefix = Path(env['WINEPREFIX'])
    marker = prefix / FONT_MARKER
    if marker.is_file() and corefonts_ready(prefix):
        return
    tools = resources / 'Wine/font-tools'
    if not (tools / 'winetricks').is_file() or not (tools / 'cabextract').is_file():
        raise RuntimeError('В бандле отсутствуют инструменты установки шрифтов. Обновите Dreamworld.app.')
    install_env = env.copy()
    install_env.update({
        'WINE': str(resources / 'Wine/bin/wine'),
        'WINE64': str(resources / 'Wine/bin/wine'),
        'WINESERVER': str(resources / 'Wine/bin/wineserver'),
        'PATH': str(tools) + os.pathsep + env.get('PATH', '/usr/bin:/bin'),
        'WINETRICKS_GUI': 'none',
        'WINETRICKS_LATEST_VERSION_CHECK': 'disabled',
        'W_CACHE': str(prefix / '.dreamworld-font-cache'),
        'WINEDLLOVERRIDES': 'winemenubuilder.exe,mshtml=d',
    })
    log.write(b'\nDreamworld: installing Microsoft corefonts via pinned Winetricks\n')
    log.flush()
    process = subprocess.Popen(['/bin/sh', str(tools / 'winetricks'), '--unattended',
                                 '--optout', '--force', 'corefonts'],
                                env=install_env, cwd=game_dir, stdout=log, stderr=log,
                                start_new_session=True)
    try:
        returncode = process.wait(timeout=600)
    except subprocess.TimeoutExpired as error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise RuntimeError('Установка шрифтов превысила время ожидания. См. .dreamworld-wine.log.') from error
    if returncode or not corefonts_ready(prefix):
        raise RuntimeError('Не удалось установить Microsoft corefonts. Проверьте интернет и повторите запуск. См. .dreamworld-wine.log.')
    marker.write_text('Microsoft corefonts (Winetricks)\n', encoding='ascii')
