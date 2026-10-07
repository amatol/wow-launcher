#!/bin/bash
# Сборка Wine x86_64 на macos-latest через Rosetta и Homebrew /usr/local.
set -euo pipefail
python tools/test_winecx_arpl.py
test "$(uname -m)" = x86_64
test "$(brew --prefix)" = /usr/local
export MACOSX_DEPLOYMENT_TARGET=14.0
export PATH="$(brew --prefix bison)/bin:$PATH"
export PKG_CONFIG_PATH="$(brew --prefix freetype)/lib/pkgconfig:$(brew --prefix gnutls)/lib/pkgconfig"
export CPPFLAGS="-I$(brew --prefix freetype)/include -I$(brew --prefix gnutls)/include -I$(brew --prefix molten-vk)/include"
export LDFLAGS="-L$(brew --prefix freetype)/lib -L$(brew --prefix gnutls)/lib -L$(brew --prefix molten-vk)/lib"
export CFLAGS="-O2"
export CROSSCFLAGS="-O2"
export CC="ccache clang -arch x86_64"
export CXX="ccache clang++ -arch x86_64"
export i386_CC="ccache i686-w64-mingw32-gcc"
export x86_64_CC="ccache x86_64-w64-mingw32-gcc"
mkdir -p build/winecx-source-tree build/winecx-objects build/winecx/ThirdParty
python - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
lock = json.loads(Path('tools/winecx-lock.json').read_text())
for key in ('source', 'mono'):
    entry = lock[key]
    path = Path('build') / ('winecx-' + key)
    subprocess.run(['curl', '-fL', '--retry', '3', '--max-time', '180', entry['url'], '-o', str(path)], check=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise RuntimeError('SHA-256: ' + key)
PY
tar -xf build/winecx-source -C build/winecx-source-tree sources/wine
source_dir="$PWD/build/winecx-source-tree/sources/wine"
patch --batch --fuzz=0 -d "$source_dir" -p1 < tools/patches/winecx-arpl.patch
runtime_dir="$PWD/build/winecx/Wine"
(cd build/winecx-objects && "$source_dir/configure" \
  --prefix="$runtime_dir" --enable-archs=i386,x86_64 --with-mingw=yes \
  --disable-tests --without-x --without-gstreamer --with-vulkan \
  --without-sdl --without-cups --without-dbus --without-sane \
  --without-pcap --without-usb --without-krb5 --without-netapi \
  --without-gphoto --with-freetype --with-gnutls)
python - <<'PY'
from pathlib import Path
header = Path('build/winecx-objects/include/config.h').read_text()
assert '#define SONAME_LIBVULKAN ' in header, 'CrossOver requires MoltenVK'
PY
# dlopen должен искать библиотеки в переносимом бандле, а не в Cellar CI.
python tools/bundle_winecx_libraries.py prepare build/winecx-objects/include/config.h
# Проверить проблемные графические части до полной сборки.
make -s -C build/winecx-objects dlls/win32u/vulkan.o dlls/winemac.drv/opengl.o
make -s -C build/winecx-objects -j"$(sysctl -n hw.ncpu)"
make -s -C build/winecx-objects install
python tools/bundle_winecx_libraries.py bundle "$runtime_dir"
lipo -verify_arch x86_64 "$runtime_dir/bin/wine" "$runtime_dir/bin/wineserver"
mkdir -p "$runtime_dir/share/wine/mono"
cp build/winecx-mono "$runtime_dir/share/wine/mono/wine-mono-10.4.1-x86.msi"
cp "$source_dir/COPYING.LIB" build/winecx/ThirdParty/Wine-COPYING.LIB
cp tools/winecx-lock.json tools/winecx-SOURCES.txt tools/patches/winecx-arpl.patch build/winecx/ThirdParty/
brew info --json=v2 --installed > build/winecx/ThirdParty/homebrew-dependencies.json
python - <<'PY'
import json
from pathlib import Path
lock = json.loads(Path('tools/winecx-lock.json').read_text())
Path('build/winecx/Wine/dreamworld-runtime-id').write_text(lock['runtime_id'] + '\n')
PY
i686-w64-mingw32-gcc -O2 -mfpmath=387 tools/winecx_probe.c -o build/winecx-probe.exe -ld3d9 -lgdi32
tar -czf build/winecx-runtime.tar.gz -C build/winecx Wine ThirdParty
