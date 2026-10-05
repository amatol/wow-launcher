#!/bin/bash
# Воспроизводимая тестовая сборка с встроенным Wine; выполнять на Apple Silicon.
set -euo pipefail
upstream_revision=2d383ffa0e01faa4a768c2bacb2c635c6c0c2e0e
mkdir -p build
if [ ! -d build/wowsilicon ]; then
    git clone https://github.com/WoWSilicon/WoWSilicon.git build/wowsilicon
fi
git -C build/wowsilicon checkout "$upstream_revision"
if [ ! -d build/wine-runtime ]; then
    build/wowsilicon/tools/wine-runtime/restore.sh --repository WoWSilicon/WoWSilicon --runtime "$PWD/build/wine-runtime"
fi
build/wowsilicon/tools/wine-runtime/validate.sh --runtime "$PWD/build/wine-runtime"
python - <<'PY'
from PIL import Image
Image.open('assets/launcher_icon.png').save('build/dreamworld.icns', format='ICNS')
PY
pyinstaller Dreamworld-macos.spec --noconfirm
resources=dist/Dreamworld.app/Contents/Resources
cp -R build/wine-runtime "$resources/Wine"
# Версия и SHA-256 из appwiz.cpl закреплённого Wine 11.13.
mkdir -p "$resources/Wine/share/wine/mono"
curl --fail --location --retry 3 \
  https://github.com/wine-mono/wine-mono/releases/download/wine-mono-11.2.0/wine-mono-11.2.0-x86.msi \
  -o "$resources/Wine/share/wine/mono/wine-mono-11.2.0-x86.msi"
MONO_FILE="$resources/Wine/share/wine/mono/wine-mono-11.2.0-x86.msi" python - <<'MONO'
import hashlib, os
from pathlib import Path
assert hashlib.sha256(Path(os.environ['MONO_FILE']).read_bytes()).hexdigest() == 'b4525679e7da30d4658ceb85739cbc55c771791054abbb4b3152fe96ded0b897'
MONO
mkdir -p "$resources/Patching"
cp -R build/wowsilicon/Sources/WoWSiliconSwift/Resources/Patching/rosettax87 "$resources/Patching/"
mkdir -p "$resources/ThirdParty"
cp build/wowsilicon/LICENSE "$resources/ThirdParty/WoWSilicon-LICENSE"
cp build/wowsilicon/Packaging/WineRuntime/*json "$resources/ThirdParty/"
printf '%s\n' "WoWSilicon https://github.com/WoWSilicon/WoWSilicon revision $upstream_revision" > "$resources/ThirdParty/SOURCES.txt"
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
codesign --force --deep --sign - dist/Dreamworld.app
codesign --verify --deep --strict dist/Dreamworld.app
file dist/Dreamworld.app/Contents/MacOS/Dreamworld
QT_QPA_PLATFORM=offscreen dist/Dreamworld.app/Contents/MacOS/Dreamworld --smoke-test
# Настоящий чистый префикс на Apple Silicon: Mono, native VC++ и повторный запуск.
PYTHONPATH=. python tools/check_macos_prefix.py dist/Dreamworld.app
(cd dist && ditto -c -k --norsrc --noextattr --keepParent Dreamworld.app Dreamworld.app.zip)
# Проверяем именно способ распаковки, используемый самообновлением macOS.
PYTHONPATH=. python - <<'PY'
from core.launcher_bundle import extract_app
extract_app('dist/Dreamworld.app.zip', 'build/roundtrip')
PY
codesign --verify --deep --strict build/roundtrip/Dreamworld.app
QT_QPA_PLATFORM=offscreen build/roundtrip/Dreamworld.app/Contents/MacOS/Dreamworld --smoke-test
