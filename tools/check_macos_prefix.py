#!/usr/bin/env python3
"""Проверка зависимостей упакованного Wine на настоящем Mac без клиента WoW."""
from pathlib import Path
import sys
import tempfile
import subprocess
import os
from core.macos_setup import prepare_wine_prefix, wine_environment, native_runtime_ready
import core.macos_setup as setup
from core.macos_prefix import RUNTIME_ID, RUNTIME_MARKER, prefix_lock

original_run = setup.run_wine_setup

def traced_run(wine, args, *rest, **kwargs):
    print('Prefix setup start:', args, flush=True)
    result = original_run(wine, args, *rest, **kwargs)
    print('Prefix setup done:', args[0], flush=True)
    return result

setup.run_wine_setup = traced_run

resources = Path(sys.argv[1]).resolve() / 'Contents/Resources'
graphics = subprocess.run([str(Path(sys.argv[3]).resolve())], check=False)
if graphics.returncode not in (0, 77):
    raise RuntimeError('Независимая проверка CGL завершилась ошибкой')
with tempfile.TemporaryDirectory(prefix='dreamworld-prefix-check-') as directory:
    env = wine_environment(resources, directory)
    prefix = Path(env['WINEPREFIX'])
    prefix.mkdir()
    (prefix / 'old-runtime-sentinel').write_text('old Wine')
    try:
        with prefix_lock(directory), open(Path(directory) / '.dreamworld-wine.log', 'ab') as log:
            prepare_wine_prefix(resources, directory, env, log)
            assert not (prefix / 'old-runtime-sentinel').exists()
            assert (prefix / RUNTIME_MARKER).read_text().strip() == RUNTIME_ID
            assert native_runtime_ready(env['WINEPREFIX'])
            prepare_wine_prefix(resources, directory, env, log)
            probe = subprocess.run([str(resources / 'Wine/bin/wine'),
                                    str(Path(sys.argv[2]).resolve())], env=env, cwd=directory,
                                   stdout=log, stderr=log, timeout=90)
            log.flush()
            output = (Path(directory) / '.dreamworld-wine.log').read_text(errors='replace')
            assert '32-bit x87 OK' in output, '32-bit x87 probe failed'
            if probe.returncode:
                if not (os.environ.get('GITHUB_ACTIONS') == 'true' and
                        graphics.returncode == 77 and probe.returncode == 12):
                    raise RuntimeError(f'Direct3D probe failed: {probe.returncode}')
                print('::warning::D3D9 NOT VERIFIED: native macOS CGL has no accelerated renderer on this CI host', flush=True)
            else:
                print('WineCX Direct3D 9 device + Present PASS', flush=True)
        print((Path(directory) / '.dreamworld-wine.log').read_text(errors='replace')[-6000:])
        print('WineCX prefix: migration + Mono + native VC++ + x87 OK', flush=True)
    except Exception:
        print((Path(directory) / '.dreamworld-wine.log').read_text(errors='replace')[-16000:])
        for path in (Path(env['WINEPREFIX'])).glob('vc-redist-*.log'):
            print(path.name, path.read_text(errors='replace')[-12000:])
        from core.macos_setup import runtime_files
        for path in runtime_files(env['WINEPREFIX']):
            print(path.name, path.parent.name, path.stat().st_size if path.exists() else 'missing',
                  path.read_bytes()[:96] if path.exists() else '')
        raise
    finally:
        env.pop('ROSETTA_X87_PATH', None)
        subprocess.run([str(resources / 'Wine/bin/wineserver'), '-k'], env=env, timeout=30)
