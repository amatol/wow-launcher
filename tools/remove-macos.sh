#!/bin/bash
# Удаление компонентов Dreamworld для macOS из явно указанной папки клиента.
set -euo pipefail
if [[ $# != 1 || ! -d "$1" ]]; then
  echo 'Закройте игру и лаунчер. Использование: bash remove-macos.sh /путь/к/клиенту' >&2
  exit 1
fi
cd -- "$1"
if [[ ! -f Wow.exe && ! -f wow.exe && ! -f WoW.exe ]] || [[ ! -d Data ]]; then
  echo 'Не найдены Wow.exe и Data; очистка отменена.' >&2
  exit 1
fi
# Перед удалением runtime убеждаемся, что Wine этого клиента завершён.
if [[ -d .dreamworld-wine && ! -L .dreamworld-wine ]]; then
  if command -v lsof >/dev/null && lsof +D "$PWD/.dreamworld-wine" 2>/dev/null | sed -n '2p' | grep -q .; then
    echo 'Wine ещё использует эту папку. Закройте игру и лаунчер и повторите.' >&2
    exit 1
  fi
fi
for name in Dreamworld.app Dreamworld.app.old Dreamworld.app.zip Dreamworld-mac.zip \
  .dreamworld-wine .dreamworld-wine.log .dreamworld-wine.lock .dreamworld-launchers.json; do
  # Без завершающего /: symlink удаляется сам, его цель не затрагивается.
  rm -rf -- "$name"
done
for name in .dreamworld-app-* .dreamworld-launchers-*; do
  if [[ "$name" =~ ^\.dreamworld-(app|launchers)-[a-z0-9_]{8}$ ]]; then
    rm -rf -- "$name"
  fi
done
echo 'Компоненты macOS удалены. Игровые файлы, WTF, аддоны и Dreamworld.exe сохранены.'
