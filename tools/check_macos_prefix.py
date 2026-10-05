#!/usr/bin/env python3
"""Проверка зависимостей упакованного Wine на настоящем Mac без клиента WoW."""
from pathlib import Path
import sys
import tempfile
import subprocess
from core.macos_setup import prepare_wine_prefix, wine_environment, native_runtime_ready
import core.macos_setup as setup

original_run = setup.run_wine_setup

def traced_run(wine, args, *rest, **kwargs):
    print('Prefix setup start:', args, flush=True)
    result = original_run(wine, args, *rest, **kwargs)
    print('Prefix setup done:', args[0], flush=True)
    return result

setup.run_wine_setup = traced_run

resources = Path(sys.argv[1]).resolve() / 'Contents/Resources'
with tempfile.TemporaryDirectory(prefix='dreamworld-prefix-check-') as directory:
    env = wine_environment(resources, directory)
    try:
        with open(Path(directory) / '.dreamworld-wine.log', 'ab') as log:
            prepare_wine_prefix(resources, directory, env, log)
            assert native_runtime_ready(env['WINEPREFIX'])
            prepare_wine_prefix(resources, directory, env, log)
        print('Wine prefix: Mono + native VC++ x86/x64 OK', flush=True)
    except Exception:
        print((Path(directory) / '.dreamworld-wine.log').read_text(errors='replace')[-16000:])
        raise
    finally:
        env.pop('ROSETTA_X87_PATH', None)
        subprocess.run([str(resources / 'Wine/bin/wineserver'), '-k'], env=env, timeout=30)
