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
mkdir -p "$resources/Patching"
cp -R build/wowsilicon/Sources/WoWSiliconSwift/Resources/Patching/rosettax87 "$resources/Patching/"
mkdir -p "$resources/ThirdParty"
cp build/wowsilicon/LICENSE "$resources/ThirdParty/WoWSilicon-LICENSE"
cp build/wowsilicon/Packaging/WineRuntime/*json "$resources/ThirdParty/"
printf '%s\n' "WoWSilicon https://github.com/WoWSilicon/WoWSilicon revision $upstream_revision" > "$resources/ThirdParty/SOURCES.txt"
# Windows должен устанавливать бандл без прав на создание symlink.
# Материализуем ссылки ДО подписи, чтобы ресурсная подпись оставалась валидной.
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
PYCODE
# Подпись ad-hoc для тестовой версии. Developer ID и нотариализация пока отсутствуют.
codesign --force --deep --sign - dist/Dreamworld.app
codesign --verify --deep --strict dist/Dreamworld.app
file dist/Dreamworld.app/Contents/MacOS/Dreamworld
QT_QPA_PLATFORM=offscreen dist/Dreamworld.app/Contents/MacOS/Dreamworld --smoke-test
(cd dist && ditto -c -k --norsrc --noextattr --keepParent Dreamworld.app Dreamworld.app.zip)
