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
arch -x86_64 /bin/bash -c '
    set -euo pipefail
    export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
    test "$(uname -m)" = x86_64
    test "$(brew --prefix)" = /usr/local
    brew install bison mingw-w64 pkgconf freetype gnutls molten-vk ccache
'
