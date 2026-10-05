#!/usr/bin/env python3
"""Проверка зависимостей упакованного Wine на настоящем Mac без клиента WoW."""
from pathlib import Path
import sys
import tempfile
import subprocess
from core.macos_setup import prepare_wine_prefix, wine_environment, native_runtime_ready

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
        subprocess.run([str(resources / 'Wine/bin/wineserver'), '-k'], env=env, timeout=30)
