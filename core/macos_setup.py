"""Подготовка настроек и зависимостей отдельного игрового Wine-префикса."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.request

import certifi
from core.macos_prefix import ensure_runtime_prefix


DEFAULT_SETTINGS = {'gxResolution': '1280x800', 'gxWindow': '1', 'gxMaximize': '0'}
VC_HASHES = {
    'x86': '0c09f2611660441084ce0df425c51c11e147e6447963c3690f97e0b25c55ed64',
    'x64': 'cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b',
}
VC_BASE = 'https://download.visualstudio.microsoft.com/download/pr/bd1c8d9d-ba95-4eee-bc6e-df1fcc876373/'
VC_OVERRIDES = 'msvcp140,msvcp140_1,msvcp140_2,msvcp140_atomic_wait,msvcp140_codecvt_ids,vcruntime140,vcruntime140_1,concrt140,vcomp140=n,b'


def prepare_game_config(game_dir):
    """Добавить только отсутствующие SET, не перекодируя существующий файл."""
    config = Path(game_dir) / 'WTF/Config.wtf'
    original = config.read_bytes() if config.exists() else b''
    # UTF-16 с BOM встречается в пользовательских редакторах; прочие кодировки
    # сохраняем побайтно: ключи и добавляемые значения состоят из ASCII.
    encoding = 'utf-16' if original.startswith((b'\xff\xfe', b'\xfe\xff')) else 'latin-1'
    text = original.decode(encoding)
    if original.startswith(b'\xef\xbb\xbf'):
        text = original[3:].decode(encoding)
    missing = {key: value for key, value in DEFAULT_SETTINGS.items()
               if not re.search(r'^\s*SET\s+' + key + r'\s+"', text, re.I | re.M)}
    if not missing:
        return
    newline = '\r\n' if '\r\n' in text else '\n'
    extra = (newline if text and not text.endswith(('\n', '\r')) else '')
    extra += ''.join(f'SET {key} "{value}"{newline}' for key, value in missing.items())
    if encoding == 'utf-16':
        # Сохранять порядок байтов и исходный BOM.
        codec = 'utf-16-le' if original.startswith(b'\xff\xfe') else 'utf-16-be'
        updated = original + extra.encode(codec)
    else:
        updated = original + extra.encode('ascii')
    config.parent.mkdir(parents=True, exist_ok=True)
    backup = config.with_name('Config.wtf.before-dreamworld-macos')
    if config.exists() and not backup.exists():
        # x исключает перезапись прежнего резерва даже при втором лаунчере.
        with backup.open('xb') as stream:
            stream.write(original)
    with tempfile.NamedTemporaryFile(dir=config.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(updated)
    try:
        if config.exists():
            shutil.copymode(config, temporary)
        os.replace(temporary, config)
    finally:
        temporary.unlink(missing_ok=True)


def wine_environment(resources, game_dir):
    env = os.environ.copy()
    for key in ('WINEARCH', 'ROSETTA_X87_PATH', 'X87_SIDECAR_PATH',
                'WINEDLLPATH', 'WINELOADER', 'WINESERVER', 'WINEESYNC', 'WINEMSYNC',
                'DYLD_INSERT_LIBRARIES', 'DYLD_FALLBACK_LIBRARY_PATH',
                'CX_ROOT', 'CX_BOTTLE', 'CX_BOTTLE_PATH', 'CX_APPLEGPTK_LIBD3DSHARED_PATH',
                'CX_LIBVULKAN', 'CX_ACTIVE_GRAPHICS_BACKEND', 'WINE_D3D_CONFIG'):
        env.pop(key, None)
    env['WINEPREFIX'] = str(Path(game_dir).resolve() / '.dreamworld-wine')
    external = resources / 'Wine/lib/external'
    env['DYLD_LIBRARY_PATH'] = str(external)
    env['PATH'] = str(resources / 'Wine/bin') + os.pathsep + env.get('PATH', '/usr/bin:/bin')
    env['WINEDATADIR'] = str(resources / 'Wine/share/wine')
    env['WINE_LARGE_ADDRESS_AWARE'] = '1'
    env['WINEDEBUG'] = '-all,err+all'
    env['WINEDLLOVERRIDES'] = 'd3d9=b;' + VC_OVERRIDES
    return env


def runtime_files(prefix):
    windows = Path(prefix) / 'drive_c/windows'
    return [windows / directory / name for directory, names in (
        ('syswow64', ('msvcp140.dll', 'vcruntime140.dll')),
        ('system32', ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')),
    ) for name in names]


def native_runtime_ready(prefix):
    # Wine тоже создаёт DLL с этими именами. Наличие файла само по себе
    # не доказывает установку Microsoft runtime.
    for path in runtime_files(prefix):
        if not path.is_file():
            return False
        with path.open('rb') as stream:
            header = stream.read(128)
        if not header.startswith(b'MZ') or b'Wine builtin DLL' in header:
            return False
    return True


def run_wine_setup(wine, args, env, game_dir, log, timeout=300):
    log.write(('\nDreamworld setup: ' + ' '.join(args) + '\n').encode('utf-8'))
    log.flush()
    try:
        result = subprocess.run([str(wine), *args], cwd=game_dir, env=env,
                                stdout=log, stderr=log, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Подготовка Wine превысила время ожидания. См. .dreamworld-wine.log.') from error
    if result.returncode not in (0, 3010):
        raise RuntimeError(f'Подготовка Wine завершилась с кодом {result.returncode}. См. .dreamworld-wine.log.')



def backup_builtin_vc_files(prefix):
    """MSI не заменяет Wine DLL с более высоким номером версии (Wine #57518)."""
    backup_root = Path(prefix) / '.dreamworld-vc-builtin-backup'
    moved = []
    names = ('msvcp140', 'msvcp140_2', 'vcruntime140_1')
    for directory in ('syswow64', 'system32'):
        for name in names:
            if name == 'vcruntime140_1' and directory != 'system32':
                continue
            source = Path(prefix) / 'drive_c/windows' / directory / (name + '.dll')
            if not source.is_file():
                continue
            with source.open('rb') as stream:
                if b'Wine builtin DLL' not in stream.read(128):
                    continue
            backup = backup_root / directory / source.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(source, backup)
            moved.append((source, backup))
    try:
        for source, backup in moved:
            source.unlink()
    except Exception:
        restore_missing_builtins(moved)
        raise
    return moved


def restore_missing_builtins(moved):
    # При сбое сохраняем уже установленные Microsoft DLL, возвращаем только
    # ещё отсутствующие файлы. Резерв остаётся внутри локального префикса.
    for source, backup in moved:
        if not source.exists():
            shutil.copy2(backup, source)


def prepare_wine_prefix(resources, game_dir, env, log):
    """Установить VC++ один раз; повторить проверку DLL при каждом запуске."""
    ensure_runtime_prefix(resources, game_dir, env, log)
    prefix = Path(env['WINEPREFIX'])
    marker = prefix / '.dreamworld-vcredist-v1'
    mono = resources / 'Wine/share/wine/mono/wine-mono-10.4.1-x86.msi'
    mono_dir = prefix / 'drive_c/windows/mono/mono-2.0'
    if marker.is_file() and native_runtime_ready(prefix) and mono_dir.is_dir():
        return
    wine = resources / 'Wine/bin/wine'
    install_env = env.copy()
    # Не наследовать перехватчик прежнего Wine и в служебных процессах.
    install_env.pop('ROSETTA_X87_PATH', None)
    install_env['__COMPAT_LAYER'] = 'RunAsInvoker'
    install_env['WINEDLLOVERRIDES'] = 'd3d9=b;' + VC_OVERRIDES + ';winemenubuilder.exe,mscoree,mshtml=d'
    boot_env = install_env.copy()
    boot_env['WINEDLLOVERRIDES'] = 'd3d9=b;winemenubuilder.exe,mshtml=d'
    if not mono.is_file():
        raise RuntimeError('В бандле отсутствует Wine Mono. Скачайте Dreamworld.app заново.')
    run_wine_setup(wine, ['wineboot', '--init'], boot_env, game_dir, log)
    if not mono_dir.is_dir():
        run_wine_setup(wine, ['msiexec', '/i', str(mono), '/qn', '/norestart'],
                       install_env, game_dir, log)
    if not mono_dir.is_dir():
        raise RuntimeError('Wine Mono не установлен. См. .dreamworld-wine.log.')
    if marker.is_file() and native_runtime_ready(prefix):
        return
    moved = backup_builtin_vc_files(prefix)
    try:
        # Не поставляем префикс или чужие DLL: официальные установщики Microsoft
        # загружаются на машине игрока, фиксируются URL и SHA-256.
        with tempfile.TemporaryDirectory(prefix='dreamworld-vcredist-') as directory:
            for arch, digest in VC_HASHES.items():
                installer = Path(directory) / f'vc_redist.{arch}.exe'
                url = VC_BASE + digest.upper() + f'/VC_redist.{arch}.exe'
                try:
                    with urllib.request.urlopen(url, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as response, installer.open('wb') as stream:
                        size = 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > 40 * 1024 * 1024:
                                raise RuntimeError('Слишком большой установщик Visual C++.')
                            stream.write(chunk)
                except OSError as error:
                    raise RuntimeError('Не удалось скачать Visual C++ с сайта Microsoft. Проверьте интернет и повторите запуск.') from error
                if hashlib.sha256(installer.read_bytes()).hexdigest() != digest:
                    raise RuntimeError('Контрольная сумма Visual C++ не совпала. Установщик не запущен.')
                run_wine_setup(wine, [str(installer), '/install', '/quiet', '/norestart', '/log',
                                      'Z:' + str(prefix / f'vc-redist-{arch}.log').replace('/', '\\')],
                               install_env, game_dir, log)
        deadline = time.monotonic() + 20
        while not native_runtime_ready(prefix) and time.monotonic() < deadline:
            time.sleep(0.5)
        if not native_runtime_ready(prefix):
            raise RuntimeError('После установки не найдены библиотеки Microsoft Visual C++. См. .dreamworld-wine.log.')
    except Exception:
        restore_missing_builtins(moved)
        raise
    marker.write_text('Microsoft Visual C++ x86/x64\n' + '\n'.join(VC_HASHES.values()) + '\n', encoding='ascii')
