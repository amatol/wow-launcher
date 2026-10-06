#!/usr/bin/env python3
"""Собрать dlopen/linked зависимости Wine и убрать привязку к Homebrew CI."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

MANIFEST = Path('build/winecx-dlopen.json')


def is_external(name):
    return name.startswith(('/usr/local/', '/opt/homebrew/'))


def prepare(header):
    libraries = []
    brew = Path(subprocess.check_output(['brew', '--prefix'], text=True).strip())
    def replace(match):
        name = match[2]
        if is_external(name):
            libraries.append(name)
            return match[1] + Path(name).name + '"'
        if name.endswith('.dylib') and '/' not in name:
            candidates = [brew / 'lib' / name, *sorted((brew / 'opt').glob('*/lib/' + name))]
            found = next((p for p in candidates if p.is_file()), None)
            if found:
                libraries.append(str(found))
            else:
                print('System/optional dlopen dependency:', name)
        return match[0]
    header.write_text(re.sub(r'(#define SONAME_\w+ ")([^"]+)"', replace, header.read_text()))
    MANIFEST.write_text(json.dumps(libraries))


def bundle(runtime):
    external = runtime / 'lib/external'
    external.mkdir(parents=True, exist_ok=True)
    notices = runtime.parent / 'ThirdParty/dependencies'
    notices.mkdir(parents=True, exist_ok=True)
    copied = {}
    queue = []

    def copy_library(name):
        source = Path(name)
        target = external / source.name
        if source.name not in copied:
            copied[source.name] = str(source.resolve())
            shutil.copy2(source, target)
            target.chmod(0o755)
            subprocess.run(['install_name_tool', '-id', '@rpath/' + target.name, str(target)], check=True)
            queue.append(target)
            # Сохраняем оригинальные уведомления из Cellar-пакета библиотеки.
            resolved = source.resolve()
            if 'Cellar' in resolved.parts:
                i = resolved.parts.index('Cellar')
                package = Path(*resolved.parts[:i + 3])
                dest = notices / resolved.parts[i + 1]
                for item in package.rglob('*'):
                    if item.is_file() and any(word in item.name.lower() for word in ('license', 'copying', 'copyright')):
                        output = dest / item.relative_to(package)
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, output)
        elif copied[source.name] != str(source.resolve()):
            raise RuntimeError('Конфликт имён библиотек: ' + name)
        return target

    for name in json.loads(MANIFEST.read_text()):
        copy_library(name)
    for path in runtime.rglob('*'):
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:
                magic = stream.read(4)
            if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
                queue.append(path)
    done = set()
    while queue:
        path = queue.pop()
        if path in done:
            continue
        done.add(path)
        output = subprocess.check_output(['otool', '-L', str(path)], text=True)
        for line in output.splitlines()[1:]:
            name = line.strip().split(' (')[0]
            if not is_external(name):
                continue
            target = copy_library(name)
            replacement = '@loader_path/' + os.path.relpath(target, path.parent)
            subprocess.run(['install_name_tool', '-change', name, replacement, str(path)], check=True)
    (runtime.parent / 'ThirdParty/bundled-libraries.json').write_text(json.dumps(copied, indent=2) + '\n')


if __name__ == '__main__':
    {'prepare': prepare, 'bundle': bundle}[sys.argv[1]](Path(sys.argv[2]).resolve())
