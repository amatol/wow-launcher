#!/bin/bash
# Воспроизводимая тестовая сборка с встроенным Wine; выполнять на Apple Silicon.
set -euo pipefail
mkdir -p build
# Исходники WineCX и Mono закреплены URL и SHA-256 в одном lock-файле.
test -f build/winecx/Wine/dreamworld-runtime-id
python - <<'PY'
from PIL import Image
Image.open('assets/launcher_icon.png').save('build/dreamworld.icns', format='ICNS')
PY
pyinstaller Dreamworld-macos.spec --noconfirm
resources=dist/Dreamworld.app/Contents/Resources
cp -R build/winecx/Wine "$resources/Wine"
cp -R build/winecx/ThirdParty "$resources/ThirdParty"
cp tools/build_winecx.sh tools/install_winecx_dependencies.sh tools/install_winecx_bottles.py tools/bundle_winecx_libraries.py "$resources/ThirdParty/"
# Проверки не должны случайно воспользоваться исходным путём установки Wine.
mv build/winecx build/winecx-input
# Внешние библиотеки Wine без symlink: Windows установит .app без привилегий.
# Qt остаётся внутри one-file EXE и распаковывается самим PyInstaller на Mac.
python - <<'PYCODE'
from pathlib import Path
import shutil
root = Path('dist/Dreamworld.app').resolve()
for path in sorted(root.rglob('*'), key=lambda p: len(p.parts), reverse=True):
    if path.is_symlink():
        target = path.resolve(strict=True)
        if not target.is_relative_to(root):
            raise RuntimeError('Внешняя ссылка в бандле: ' + str(path))
        path.unlink()
        if target.is_dir():
            shutil.copytree(target, path)
        else:
            shutil.copy2(target, path)
assert not any(path.is_symlink() for path in root.rglob('*'))
PYCODE
# Подпись ad-hoc для тестовой версии. Developer ID и нотариализация пока отсутствуют.
# Свежесобранные Mach-O внутри Resources тоже подписываем после переноса dylib.
python - <<'PY'
from pathlib import Path
import subprocess
for path in Path('dist/Dreamworld.app/Contents/Resources/Wine').rglob('*'):
    if path.is_file():
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
            subprocess.run(['codesign', '--force', '--sign', '-', str(path)], check=True)
PY
codesign --force --deep --sign - dist/Dreamworld.app
codesign --verify --deep --strict dist/Dreamworld.app
file dist/Dreamworld.app/Contents/MacOS/Dreamworld
QT_QPA_PLATFORM=offscreen dist/Dreamworld.app/Contents/MacOS/Dreamworld --smoke-test
# Настоящий чистый префикс на Apple Silicon: Mono, native VC++ и повторный запуск.
# Проверяем CGL отдельно под той же Rosetta, что и Wine.
clang -arch x86_64 tools/macos_gl_probe.c -framework OpenGL -o build/macos-gl-probe
PYTHONPATH=. python tools/check_macos_prefix.py dist/Dreamworld.app build/winecx-probe.exe build/macos-gl-probe
(cd dist && ditto -c -k --norsrc --noextattr --keepParent Dreamworld.app Dreamworld.app.zip)
# Проверяем именно способ распаковки, используемый самообновлением macOS.
PYTHONPATH=. python - <<'PY'
from core.launcher_bundle import extract_app
extract_app('dist/Dreamworld.app.zip', 'build/roundtrip')
PY
codesign --verify --deep --strict build/roundtrip/Dreamworld.app
QT_QPA_PLATFORM=offscreen build/roundtrip/Dreamworld.app/Contents/MacOS/Dreamworld --smoke-test
