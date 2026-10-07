#!/bin/bash
# Отдельный Homebrew x86_64 для Wine; нативный Homebrew лаунчера не меняется.
set -euo pipefail
test "$(uname -s)" = Darwin
test "$(uname -m)" = arm64
if ! arch -x86_64 /usr/bin/true; then
    sudo /usr/sbin/softwareupdate --install-rosetta --agree-to-license
fi
if [ ! -x /usr/local/bin/brew ]; then
    # Та же ревизия установщика с поддержкой Intel, что в GitHub runner-images.
    installer="${RUNNER_TEMP:?}/homebrew-winecx-install.sh"
    curl -fL --retry 3 --max-time 180 \
      https://raw.githubusercontent.com/Homebrew/install/0f5b7666a65fc2d1a2615549f02771353c250f9a/install.sh \
      -o "$installer"
    NONINTERACTIVE=1 arch -x86_64 /bin/bash "$installer"
fi
# Все зависимости и готовые бутылки перечислены в lock-файле.
# Свежие формулы и сборка пакетов из исходников здесь не используются.
python tools/install_winecx_bottles.py
# Компиляторы выполняются нативно; MinGW всё равно создаёт PE i386/x86_64.
# На поддерживаемом Apple Silicon требуем bottles без сборки из исходников.
HOMEBREW_NO_AUTO_UPDATE=1 arch -arm64 /opt/homebrew/bin/brew install --force-bottle mingw-w64 ccache
for compiler in ccache i686-w64-mingw32-gcc x86_64-w64-mingw32-gcc; do
    lipo "/opt/homebrew/bin/$compiler" -verify_arch arm64
done
